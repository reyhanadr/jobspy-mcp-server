"""
Utility parser untuk portal JobStreet (SEEK v5 REST API).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, List, Any
from jobspy.model import Location, Compensation, CompensationInterval, JobType, Country
from .constant import COUNTRY_CONFIG


COUNTRY_CODE_TO_NAME = {
    "ID": "Indonesia",
    "MY": "Malaysia",
    "SG": "Singapore",
    "PH": "Philippines",
}


def resolve_country_code(location: str | None, country: Country | str | None) -> str:
    """
    Tentukan pasar negara JobStreet (ID, MY, SG, PH) dari location atau country.
    Default ke 'ID' (Indonesia) jika country tidak relevan (misal default 'USA').
    """
    candidates = []
    if location:
        candidates.append(str(location).lower())
    if country:
        if isinstance(country, Country):
            # Abaikan default Country.USA agar pencarian default lari ke Indonesia
            if country != Country.USA:
                candidates.extend([n.lower() for n in country.value[0].split(",")])
        else:
            c_str = str(country).lower().strip()
            if c_str not in ("usa", "us", "united states"):
                candidates.append(c_str)

    combined = " | ".join(candidates)
    if any(k in combined for k in ("singapore", "singapura", " sg")):
        return "SG"
    if any(k in combined for k in ("malaysia", "kuala lumpur", "selangor", "penang", "johor", " my")):
        return "MY"
    if any(k in combined for k in ("philippines", "manila", "makati", "cebu", "taguig", " ph")):
        return "PH"
    return "ID"


def clean_where_location(location: str | None) -> Optional[str]:
    """
    Bersihkan parameter 'where' untuk SEEK API.
    Jika location bernilai 'remote' atau hanya nama negara umum, kembalikan None
    agar pencarian tidak gagal mencocokkan nama kota.
    """
    if not location:
        return None
    loc_clean = location.strip()
    low = loc_clean.lower()
    if low in (
        "remote",
        "work from home",
        "wfh",
        "anywhere",
        "indonesia",
        "malaysia",
        "singapore",
        "philippines",
        "id",
        "my",
        "sg",
        "ph",
    ):
        return None
    return loc_clean


def parse_date(raw_date: str | int | float | None) -> Optional[date]:
    """
    Parse ISO date string, epoch milliseconds, atau date string lainnya ke date object.
    """
    if not raw_date:
        return None

    if isinstance(raw_date, (int, float)):
        try:
            if raw_date > 1e11:
                return datetime.fromtimestamp(raw_date / 1000.0).date()
            return datetime.fromtimestamp(raw_date).date()
        except Exception:
            return None

    if isinstance(raw_date, str):
        try:
            clean_str = raw_date.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str).date()
        except Exception:
            pass

        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_date)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except Exception:
                pass

    return None


def parse_location(
    loc_data: list | dict | str | None,
    default_country: str = "Indonesia",
) -> Optional[Location]:
    """
    Parse field 'locations' (list of dicts di SEEK v5) atau dict/str ke model Location.
    """
    if not loc_data:
        return None

    if isinstance(loc_data, list):
        if not loc_data:
            return None
        return parse_location(loc_data[0], default_country=default_country)

    if isinstance(loc_data, str):
        parts = [p.strip() for p in loc_data.split(",") if p.strip()]
        return Location(
            city=parts[0] if parts else None,
            state=parts[1] if len(parts) > 1 else None,
            country=default_country,
        )

    if isinstance(loc_data, dict):
        country_code = loc_data.get("countryCode")
        country_name = COUNTRY_CODE_TO_NAME.get(country_code, default_country)

        city = loc_data.get("city")
        state = loc_data.get("state")
        label = loc_data.get("label") or loc_data.get("name")

        if not city and label:
            parts = [p.strip() for p in str(label).split(",") if p.strip()]
            city = parts[0] if parts else None
            if not state and len(parts) > 1:
                state = parts[1]

        if not state and isinstance(loc_data.get("seoHierarchy"), list):
            seo = loc_data["seoHierarchy"]
            if len(seo) > 1 and isinstance(seo[1], dict):
                state = seo[1].get("contextualName")

        return Location(
            city=city,
            state=state,
            country=country_name,
        )

    return None


def _parse_numeric_token(token: str, multiplier_hint: str = "") -> Optional[float]:
    """
    Konversi string angka gaji seperti '10.000.000', '10,000,000', '8.5', '12jt', '5k' ke float.
    """
    t = token.strip().lower()
    if not t:
        return None

    mult = 1.0
    if any(m in t for m in ("juta", "jt", "million", "mil")) or any(
        m in multiplier_hint for m in ("juta", "jt", "million")
    ):
        mult = 1_000_000.0
        t = re.sub(r"[a-z]+", "", t).strip()
    elif t.endswith("k"):
        mult = 1_000.0
        t = t[:-1].strip()

    # Jika menggunakan pemisah ribuan titik/koma berulang (misal 10.000.000 atau 10,000,000)
    if re.match(r"^\d{1,3}(\.\d{3})+$", t):
        t = t.replace(".", "")
    elif re.match(r"^\d{1,3}(,\d{3})+$", t):
        t = t.replace(",", "")
    else:
        # Desimal (misal 8,5 juta -> 8.5)
        if "," in t and "." not in t:
            parts = t.split(",")
            if len(parts[-1]) == 3 and mult == 1.0:
                t = t.replace(",", "")
            else:
                t = t.replace(",", ".")
        else:
            t = t.replace(",", "")

    try:
        return float(t) * mult
    except Exception:
        return None


def parse_compensation(
    salary_data: dict | str | None,
    default_currency: str = "IDR",
) -> Optional[Compensation]:
    """
    Parse salaryLabel string (SEEK v5) atau dict salary ke model Compensation.
    Contoh salaryLabel:
      - "Rp 10.000.000 – Rp 15.000.000 per month"
      - "Rp 8,000,000 - Rp 12,000,000 per month"
      - "RM 4,000 – RM 6,000 per month"
      - "$5,000 – $7,000 per month"
    """
    if not salary_data:
        return None

    if isinstance(salary_data, dict):
        min_amount = salary_data.get("minimum") or salary_data.get("min")
        max_amount = salary_data.get("maximum") or salary_data.get("max")
        currency = salary_data.get("currency") or default_currency
        salary_type = str(salary_data.get("type", "")).lower()

        interval = _detect_interval(salary_type)
        if min_amount is not None or max_amount is not None:
            try:
                return Compensation(
                    interval=interval,
                    min_amount=float(min_amount) if min_amount is not None else None,
                    max_amount=float(max_amount) if max_amount is not None else None,
                    currency=currency,
                )
            except Exception:
                return None
        return None

    if isinstance(salary_data, str):
        text = salary_data.strip()
        if not text:
            return None

        low = text.lower()
        currency = default_currency
        if "rp" in low or "idr" in low:
            currency = "IDR"
        elif "rm" in low or "myr" in low:
            currency = "MYR"
        elif "s$" in low or "sgd" in low:
            currency = "SGD"
        elif "php" in low or "₱" in low:
            currency = "PHP"
        elif "usd" in low or "us$" in low:
            currency = "USD"
        elif "$" in low and default_currency == "IDR":
            currency = "USD"

        interval = _detect_interval(low) or CompensationInterval.MONTHLY

        # Cari pola angka (termasuk ribuan dengan titik/koma dan akhiran k/jt/juta)
        matches = re.findall(
            r"\d+(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*(?:juta|jt|k)?",
            low,
        )
        amounts = []
        for m in matches:
            val = _parse_numeric_token(m, multiplier_hint=low)
            if val is not None and val > 0:
                amounts.append(val)

        if not amounts:
            return None

        min_amt = amounts[0]
        max_amt = amounts[1] if len(amounts) > 1 else amounts[0]
        if max_amt < min_amt:
            min_amt, max_amt = max_amt, min_amt

        return Compensation(
            interval=interval,
            min_amount=min_amt,
            max_amount=max_amt,
            currency=currency,
        )

    return None


def _detect_interval(text: str) -> Optional[CompensationInterval]:
    low = text.lower()
    if any(w in low for w in ("month", "bulan", "bln", "mth")):
        return CompensationInterval.MONTHLY
    if any(w in low for w in ("year", "annual", "tahun", "thn", "yr", "p.a")):
        return CompensationInterval.YEARLY
    if any(w in low for w in ("hour", "jam", "hr")):
        return CompensationInterval.HOURLY
    if any(w in low for w in ("day", "hari")):
        return CompensationInterval.DAILY
    if any(w in low for w in ("week", "minggu", "wk")):
        return CompensationInterval.WEEKLY
    return None


def parse_job_type(work_type: list[str] | str | None) -> Optional[List[JobType]]:
    """
    Map workTypes list (misal: ["Full time"]) atau string ke list[JobType].
    """
    if not work_type:
        return None

    if isinstance(work_type, list):
        wt = " ".join(str(x) for x in work_type).lower()
    else:
        wt = str(work_type).lower()

    types = []
    if "full" in wt or "tetap" in wt or "purnawaktu" in wt or "penuh waktu" in wt:
        types.append(JobType.FULL_TIME)
    if "part" in wt or "paruh" in wt:
        types.append(JobType.PART_TIME)
    if "contract" in wt or "kontrak" in wt or "freelance" in wt or "temp" in wt:
        types.append(JobType.CONTRACT)
    if "intern" in wt or "magang" in wt or "trainee" in wt:
        types.append(JobType.INTERNSHIP)

    return types if types else None


def parse_work_arrangement(
    work_arrangements: dict | list | str | None,
    work_types: Any = None,
    location_text: str | None = None,
    title_text: str | None = None,
) -> tuple[bool, Optional[str]]:
    """
    Ekstrak status is_remote dan work_from_home_type dari workArrangements SEEK v5.
    Contoh workArrangements: {"data": [{"id": "3", "label": {"text": "Remote"}}]}
    """
    labels: list[str] = []
    if isinstance(work_arrangements, dict):
        data_list = work_arrangements.get("data") or []
        if isinstance(data_list, list):
            for item in data_list:
                if isinstance(item, dict):
                    lbl = item.get("label")
                    if isinstance(lbl, dict) and lbl.get("text"):
                        labels.append(str(lbl["text"]).strip())
                    elif isinstance(lbl, str):
                        labels.append(lbl.strip())
    elif isinstance(work_arrangements, list):
        for item in work_arrangements:
            if isinstance(item, str):
                labels.append(item.strip())
    elif isinstance(work_arrangements, str):
        labels.append(work_arrangements.strip())

    wfh_type = ", ".join(labels) if labels else None
    combined = " ".join(
        [
            wfh_type or "",
            str(work_types or ""),
            str(location_text or ""),
            str(title_text or ""),
        ]
    ).lower()

    is_remote = any(
        kw in combined
        for kw in ("remote", "work from home", "wfh", "jarak jauh", "kerja dari rumah")
    )
    return is_remote, wfh_type
