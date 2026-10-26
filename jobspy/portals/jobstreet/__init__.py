"""
JobStreet Scraper — Sidecar Scraper untuk JobStreet (SEEK v5 REST API).
Mendukung pasar Indonesia (ID), Malaysia (MY), Singapura (SG), dan Filipina (PH)
tanpa menggunakan headless browser.
"""
from __future__ import annotations

import math
import time
import random
from datetime import date, timedelta
from typing import List, Optional

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    DescriptionFormat,
)
from jobspy.util import (
    create_session,
    create_logger,
    markdown_converter,
    extract_emails_from_text,
)

from .constant import HEADERS, COUNTRY_CONFIG
from .util import (
    resolve_country_code,
    clean_where_location,
    parse_date,
    parse_location,
    parse_compensation,
    parse_job_type,
    parse_work_arrangement,
)

log = create_logger("JobStreet")


class JobStreet(Scraper):
    """
    Sidecar scraper untuk JobStreet (SEEK v5 API: /api/jobsearch/v5/search).
    Men-subclass Scraper bawaan jobspy.model.
    """

    base_url = "https://id.jobstreet.com"
    delay = 1
    band_delay = 2

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        # Gunakan Site.BAYT sebagai placeholder teknis untuk Scraper superclass;
        # kolom 'site' di-set eksplisit menjadi 'jobstreet' di base.py
        super().__init__(Site.BAYT, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        self.session = create_session(
            proxies=proxies,
            ca_cert=ca_cert,
            is_tls=True,
            has_retry=True,
        )
        self.session.headers.update(HEADERS)
        if user_agent:
            self.session.headers["user-agent"] = user_agent

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrape jobs dari JobStreet SEEK v5 REST API berdasarkan kriteria input.
        """
        jobs: List[JobPost] = []
        seen_ids: set[str] = set()

        country_code = resolve_country_code(scraper_input.location, scraper_input.country)
        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["ID"])
        self.base_url = cfg["base_url"]
        search_url = f"{self.base_url}/api/jobsearch/v5/search"

        results_wanted = min(max(scraper_input.results_wanted or 20, 1), 500)
        page_size = min(30, max(results_wanted, 10))
        offset = max(scraper_input.offset or 0, 0)
        page = (offset // page_size) + 1
        skip_in_first_page = offset % page_size

        search_term = scraper_input.search_term or ""
        if scraper_input.is_remote and "remote" not in search_term.lower():
            # Bantu SEEK mengutamakan lowongan remote jika diminta
            effective_keywords = f"{search_term} remote".strip()
        else:
            effective_keywords = search_term

        where_loc = clean_where_location(scraper_input.location)

        log.info(
            f"Scraping JobStreet ({country_code}) for '{effective_keywords}' "
            f"in '{where_loc or 'All Locations'}' (wanted: {results_wanted})"
        )

        max_pages = max(math.ceil((results_wanted + offset) / page_size) + 2, 5)
        pages_fetched = 0

        while len(jobs) < results_wanted and pages_fetched < max_pages:
            params: dict[str, str | int] = {
                "siteKey": cfg["site_key"],
                "keywords": effective_keywords,
                "page": page,
                "pageSize": page_size,
            }
            if where_loc:
                params["where"] = where_loc
            if scraper_input.hours_old:
                params["daterange"] = max(1, math.ceil(scraper_input.hours_old / 24))

            try:
                res = self.session.get(
                    search_url,
                    params=params,
                    timeout_seconds=30,
                )
            except Exception as e:
                log.error(f"JobStreet connection error on page {page}: {e}")
                break

            if res.status_code not in range(200, 400):
                log.error(f"JobStreet API status {res.status_code} on page {page}")
                break

            try:
                payload = res.json()
            except Exception as e:
                log.error(f"Failed to parse JobStreet JSON response: {e}")
                break

            raw_nodes = self._extract_job_nodes(payload)
            if not raw_nodes:
                log.info(f"No more jobs found at page {page}")
                break

            batch = self._parse_response(
                payload,
                scraper_input=scraper_input,
                country_code=country_code,
            )

            if pages_fetched == 0 and skip_in_first_page > 0:
                batch = batch[skip_in_first_page:]

            for job in batch:
                if job.id and job.id in seen_ids:
                    continue
                if job.id:
                    seen_ids.add(job.id)
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break

            pages_fetched += 1
            log.info(f"Fetched {len(batch)} matching jobs from page {page} (total: {len(jobs)})")

            if len(raw_nodes) < page_size:
                break

            page += 1
            if len(jobs) < results_wanted:
                time.sleep(self.delay + random.uniform(0, self.band_delay))

        return JobResponse(jobs=jobs[:results_wanted])

    def _extract_job_nodes(self, data: dict) -> list[dict]:
        """
        Ekstrak list job dict dari respons SEEK v5 REST API (`data['data']`)
        maupun struktur fallback (`data['data']['jobSearch']['jobs']`).
        """
        if not isinstance(data, dict):
            return []

        top_data = data.get("data")
        if isinstance(top_data, list):
            return [n for n in top_data if isinstance(n, dict)]

        if isinstance(top_data, dict):
            if "jobSearch" in top_data and isinstance(top_data["jobSearch"], dict):
                jobs = top_data["jobSearch"].get("jobs", [])
                if isinstance(jobs, list):
                    return [n for n in jobs if isinstance(n, dict)]
            if "jobs" in top_data and isinstance(top_data["jobs"], list):
                return [n for n in top_data["jobs"] if isinstance(n, dict)]
            for val in top_data.values():
                if isinstance(val, dict) and isinstance(val.get("jobs"), list):
                    return [n for n in val["jobs"] if isinstance(n, dict)]

        return []

    def _parse_response(
        self,
        data: dict,
        scraper_input: ScraperInput | None = None,
        country_code: str = "ID",
    ) -> List[JobPost]:
        """
        Parse payload JSON dari JobStreet SEEK v5 API → list[JobPost].
        """
        jobs: List[JobPost] = []
        job_nodes = self._extract_job_nodes(data)
        if not job_nodes:
            return jobs

        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["ID"])
        base_url = getattr(self, "base_url", None) or cfg["base_url"]
        default_country = cfg["country_name"]
        default_currency = cfg["currency"]
        job_path = cfg["job_path"]

        cutoff_date: Optional[date] = None
        if scraper_input and scraper_input.hours_old:
            days = max(1, math.ceil(scraper_input.hours_old / 24))
            cutoff_date = date.today() - timedelta(days=days)

        for node in job_nodes:
            try:
                job_id = str(node.get("id", "")).strip()
                title = (node.get("title") or node.get("jobTitle") or "").strip()
                if not title:
                    continue

                adv = node.get("advertiser") if isinstance(node.get("advertiser"), dict) else {}
                employer = node.get("employer") if isinstance(node.get("employer"), dict) else {}
                company_name = (
                    node.get("companyName")
                    or adv.get("description")
                    or adv.get("name")
                    or employer.get("name")
                    or node.get("company")
                )

                job_url = node.get("jobUrl") or (
                    f"{base_url}{job_path}/{job_id}" if job_id else base_url
                )
                job_url_direct = node.get("jobUrlDirect") or node.get("applyUrl")

                company_url = employer.get("companyUrl") or node.get("companyUrl")
                branding = node.get("branding") if isinstance(node.get("branding"), dict) else {}
                company_logo = branding.get("serpLogoUrl") or node.get("companyLogo")

                # Industri & fungsi pekerjaan dari classifications
                company_industry = None
                job_function = None
                classifications = node.get("classifications")
                if isinstance(classifications, list) and classifications:
                    first_cls = classifications[0] if isinstance(classifications[0], dict) else {}
                    cls_obj = first_cls.get("classification")
                    sub_obj = first_cls.get("subclassification")
                    if isinstance(cls_obj, dict):
                        company_industry = cls_obj.get("description")
                    if isinstance(sub_obj, dict):
                        job_function = sub_obj.get("description")

                # Bangun deskripsi dari teaser + bulletPoints
                teaser = (node.get("teaser") or node.get("description") or node.get("summary") or "").strip()
                bullets = node.get("bulletPoints")
                bullet_lines = (
                    [str(b).strip() for b in bullets if str(b).strip()]
                    if isinstance(bullets, list)
                    else []
                )

                desc_parts = []
                if teaser:
                    desc_parts.append(teaser)
                if bullet_lines:
                    desc_parts.append("\n".join(f"- {b}" for b in bullet_lines))
                raw_desc = "\n\n".join(desc_parts)

                if raw_desc:
                    if (
                        scraper_input
                        and scraper_input.description_format == DescriptionFormat.HTML
                    ):
                        description = raw_desc
                    else:
                        description = markdown_converter(raw_desc) if "<" in raw_desc else raw_desc
                else:
                    description = None

                # Lokasi
                location_val = (
                    node.get("locations")
                    or node.get("location")
                    or node.get("locationLabel")
                )
                location_obj = parse_location(location_val, default_country=default_country)

                # Tanggal posting
                date_val = node.get("listingDate") or node.get("createdAt") or node.get("datePosted")
                date_posted = parse_date(date_val)
                if cutoff_date and date_posted and date_posted < cutoff_date:
                    continue

                # Tipe pekerjaan & remote arrangement
                work_type_val = node.get("workTypes") or node.get("workType") or node.get("jobType")
                job_types = parse_job_type(work_type_val)
                if (
                    scraper_input
                    and scraper_input.job_type
                    and job_types
                    and scraper_input.job_type not in job_types
                ):
                    continue

                loc_display = location_obj.display_location() if location_obj else ""
                is_remote, wfh_type = parse_work_arrangement(
                    node.get("workArrangements"),
                    work_types=work_type_val,
                    location_text=loc_display,
                    title_text=title,
                )
                if scraper_input and scraper_input.is_remote and not is_remote:
                    continue

                # Gaji / kompensasi
                salary_val = node.get("salaryLabel") or node.get("salary") or node.get("compensation")
                compensation = parse_compensation(salary_val, default_currency=default_currency)

                emails = extract_emails_from_text(description) if description else None

                job_post = JobPost(
                    id=job_id if job_id else None,
                    title=title,
                    company_name=company_name,
                    job_url=job_url,
                    job_url_direct=job_url_direct,
                    location=location_obj,
                    description=description,
                    company_url=company_url,
                    company_logo=company_logo,
                    company_industry=company_industry,
                    job_function=job_function,
                    job_type=job_types,
                    compensation=compensation,
                    date_posted=date_posted,
                    emails=emails,
                    is_remote=is_remote,
                    work_from_home_type=wfh_type,
                )
                jobs.append(job_post)
            except Exception as e:
                log.warning(f"Error parsing JobStreet job node: {e}")
                continue

        return jobs
