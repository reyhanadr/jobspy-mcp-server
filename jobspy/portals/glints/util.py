"""
Utility parser untuk portal Glints (GraphQL API v2).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Optional, List
from jobspy.model import Location, Compensation, CompensationInterval, JobType, Country
from .constant import COUNTRY_CONFIG


def resolve_country_code(location: str | None, country: Country | str | None) -> str:
    """
    Tentukan pasar negara Glints (ID, SG, MY, VN, TW) dari location atau country.
    Default ke 'ID' (Indonesia).
    """
    candidates = []
    if location:
        candidates.append(str(location).lower())
    if country:
        if isinstance(country, Country):
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
    if any(k in combined for k in ("vietnam", "ho chi minh", "hanoi", "da nang", " vn")):
        return "VN"
    if any(k in combined for k in ("taiwan", "taipei", "kaohsiung", "taichung", " tw")):
        return "TW"
    return "ID"


def clean_search_location(location: str | None) -> Optional[str]:
    """
    Kembalikan nama kota/daerah spesifik jika ada, atau None jika hanya 'remote' / nama negara.
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
        "singapore",
        "malaysia",
        "vietnam",
        "taiwan",
        "id",
        "sg",
        "my",
        "vn",
        "tw",
    ):
        return None
    return loc_clean


def parse_date(raw_date: str | int | float | None) -> Optional[date]:
    """
    Parse ISO 8601 date string atau timestamp dari Glints ke date object.
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
    location_node: dict | None,
    city_node: dict | None = None,
    country_node: dict | None = None,
    default_country: str = "Indonesia",
) -> Optional[Location]:
    """
    Parse hierarchical location dari Glints GraphQL ke model Location.
    Level hirarki Glints:
      level 1 = Country (misal Indonesia)
      level 2 = Province/State (misal DKI Jakarta)
      level 3 = City/Regency (misal Jakarta Selatan)
      level 4 = District (misal Setiabudi)
    """
    country_name = (
        country_node.get("name")
        if isinstance(country_node, dict) and country_node.get("name")
        else default_country
    )
    city_name = (
        city_node.get("name")
        if isinstance(city_node, dict) and city_node.get("name")
        else None
    )
    state_name = None

    if isinstance(location_node, dict):
        loc_level = location_node.get("level")
        loc_name = location_node.get("formattedName") or location_node.get("name")
        parents = location_node.get("parents") or []

        by_level: dict[int, str] = {}
        if isinstance(loc_level, int) and loc_name:
            by_level[loc_level] = str(loc_name)

        if isinstance(parents, list):
            for p in parents:
                if isinstance(p, dict):
                    p_level = p.get("level")
                    p_name = p.get("formattedName") or p.get("name")
                    if isinstance(p_level, int) and p_name:
                        by_level[p_level] = str(p_name)

        if 1 in by_level:
            country_name = by_level[1]
        if 2 in by_level:
            state_name = by_level[2]
        if 3 in by_level:
            city_name = by_level[3]
        elif 4 in by_level and not city_name:
            city_name = by_level[4]
        elif loc_name and not city_name and loc_level not in (1, 2):
            city_name = str(loc_name)

    if not city_name and not state_name and not country_name:
        return None

    return Location(
        city=city_name,
        state=state_name,
        country=country_name,
    )


def parse_compensation(
    salaries: list | dict | None,
    default_currency: str = "IDR",
) -> Optional[Compensation]:
    """
    Parse salaries list dari Glints GraphQL ke model Compensation.
    """
    if not salaries:
        return None

    salary_obj = None
    if isinstance(salaries, list):
        if not salaries:
            return None
        salary_obj = salaries[0] if isinstance(salaries[0], dict) else None
    elif isinstance(salaries, dict):
        salary_obj = salaries

    if not salary_obj:
        return None

    min_amount = salary_obj.get("minAmount")
    max_amount = salary_obj.get("maxAmount")
    if min_amount is None and max_amount is None:
        return None

    currency = salary_obj.get("CurrencyCode") or salary_obj.get("currency") or default_currency
    mode = str(salary_obj.get("salaryMode") or "MONTH").upper()

    interval = CompensationInterval.MONTHLY
    if "YEAR" in mode or "ANNUAL" in mode:
        interval = CompensationInterval.YEARLY
    elif "HOUR" in mode:
        interval = CompensationInterval.HOURLY
    elif "DAY" in mode:
        interval = CompensationInterval.DAILY
    elif "WEEK" in mode:
        interval = CompensationInterval.WEEKLY

    try:
        return Compensation(
            interval=interval,
            min_amount=float(min_amount) if min_amount is not None else None,
            max_amount=float(max_amount) if max_amount is not None else None,
            currency=currency,
        )
    except Exception:
        return None


def parse_job_type(raw_type: str | None) -> Optional[List[JobType]]:
    """
    Map Glints job type ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERNSHIP', 'PROJECT_BASED', 'FREELANCE')
    ke list[JobType].
    """
    if not raw_type:
        return None

    wt = str(raw_type).upper()
    types = []
    if "FULL" in wt:
        types.append(JobType.FULL_TIME)
    if "PART" in wt:
        types.append(JobType.PART_TIME)
    if "CONTRACT" in wt or "FREELANCE" in wt or "PROJECT" in wt:
        types.append(JobType.CONTRACT)
    if "INTERN" in wt:
        types.append(JobType.INTERNSHIP)

    return types if types else None


def format_experience_range(min_exp: int | None, max_exp: int | None) -> Optional[str]:
    """
    Format minYearsOfExperience & maxYearsOfExperience ke string seperti '1 - 3 years'.
    """
    if min_exp is None and max_exp is None:
        return None
    if min_exp is not None and max_exp is not None:
        if min_exp == max_exp:
            return f"{min_exp} years"
        return f"{min_exp} - {max_exp} years"
    if min_exp is not None:
        return f"{min_exp}+ years"
    return f"Up to {max_exp} years"


def parse_draftjs_description(desc_json_str: str | None) -> Optional[str]:
    """
    Konversi Draft.js JSON string (`descriptionJsonString` dari getJobById) menjadi Markdown.
    """
    if not desc_json_str or not isinstance(desc_json_str, str):
        return None

    try:
        parsed = json.loads(desc_json_str)
    except Exception:
        return desc_json_str.strip() or None

    if not isinstance(parsed, dict):
        return None

    blocks = parsed.get("blocks")
    if not isinstance(blocks, list):
        return None

    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        btype = str(block.get("type") or "unstyled")
        if not text:
            continue

        if btype.startswith("header-"):
            lines.append(f"### {text}")
        elif btype == "unordered-list-item":
            lines.append(f"- {text}")
        elif btype == "ordered-list-item":
            lines.append(f"1. {text}")
        else:
            lines.append(text)

    return "\n\n".join(lines).strip() if lines else None


def build_summary_description(
    title: str,
    company_name: str | None,
    category_name: str | None,
    work_arrangement: str | None,
    experience_range: str | None,
    education_level: str | None,
    skills: list[str] | None,
) -> Optional[str]:
    """
    Bangun ringkasan deskripsi terstruktur dari metadata pencarian Glints
    saat full description (getJobById) tidak diminta.
    """
    parts: list[str] = []
    header = f"**{title}**"
    if company_name:
        header += f" at **{company_name}**"
    parts.append(header)

    meta_bullets: list[str] = []
    if category_name:
        meta_bullets.append(f"- **Category:** {category_name}")
    if work_arrangement:
        meta_bullets.append(f"- **Work Arrangement:** {work_arrangement}")
    if experience_range:
        meta_bullets.append(f"- **Experience Required:** {experience_range}")
    if education_level:
        clean_edu = str(education_level).replace("_", " ").title()
        meta_bullets.append(f"- **Education:** {clean_edu}")
    if skills:
        meta_bullets.append(f"- **Skills:** {', '.join(skills)}")

    if meta_bullets:
        parts.append("\n".join(meta_bullets))

    return "\n\n".join(parts) if parts else None
