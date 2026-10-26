"""
Glints Scraper — Sidecar Scraper untuk glints.com (GraphQL v2 API).
Mendukung pasar Indonesia (ID), Singapura (SG), Malaysia (MY), Vietnam (VN), dan Taiwan (TW)
tanpa headless browser.
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

from .constant import HEADERS, COUNTRY_CONFIG, SEARCH_JOBS_QUERY, GET_JOB_BY_ID_QUERY
from .util import (
    resolve_country_code,
    clean_search_location,
    parse_date,
    parse_location,
    parse_compensation,
    parse_job_type,
    format_experience_range,
    parse_draftjs_description,
    build_summary_description,
)

log = create_logger("Glints")


class Glints(Scraper):
    """
    Sidecar scraper untuk glints.com menggunakan GraphQL v2 endpoint (/api/v2/graphql).
    """

    base_url = "https://glints.com"
    graphql_url = f"{base_url}/api/v2/graphql"
    delay = 1
    band_delay = 2

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
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
        Scrape jobs dari Glints GraphQL API berdasarkan kriteria input.
        """
        jobs: List[JobPost] = []
        seen_ids: set[str] = set()

        country_code = resolve_country_code(scraper_input.location, scraper_input.country)
        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["ID"])
        self.session.headers["x-glints-country-code"] = country_code

        results_wanted = min(max(scraper_input.results_wanted or 20, 1), 500)
        limit = min(30, max(results_wanted, 10))
        offset = max(scraper_input.offset or 0, 0)

        search_term = (scraper_input.search_term or "").strip()
        loc_hint = clean_search_location(scraper_input.location)

        log.info(
            f"Scraping Glints ({country_code}) for '{search_term}' "
            f"(location filter: '{loc_hint or 'All'}', wanted: {results_wanted})"
        )

        max_pages = max(math.ceil(results_wanted / limit) + 3, 5)
        pages_fetched = 0

        while len(jobs) < results_wanted and pages_fetched < max_pages:
            payload = {
                "operationName": "searchJobs",
                "query": SEARCH_JOBS_QUERY,
                "variables": {
                    "data": {
                        "SearchTerm": search_term,
                        "CountryCode": country_code,
                        "includeExternalJobs": True,
                        "limit": limit,
                        "offset": offset,
                    }
                },
            }

            try:
                res = self.session.post(
                    f"{self.graphql_url}?op=searchJobs",
                    json=payload,
                    timeout_seconds=30,
                )
            except Exception as e:
                log.error(f"Glints connection error at offset {offset}: {e}")
                break

            if res.status_code not in range(200, 400):
                log.error(f"Glints API status {res.status_code} at offset {offset}")
                break

            try:
                data = res.json()
            except Exception as e:
                log.error(f"Failed to parse Glints JSON response: {e}")
                break

            raw_nodes = self._extract_job_nodes(data)
            if not raw_nodes:
                log.info(f"No more Glints jobs found at offset {offset}")
                break

            batch = self._parse_response(
                data,
                scraper_input=scraper_input,
                country_code=country_code,
            )

            for job in batch:
                if job.id and job.id in seen_ids:
                    continue
                if job.id:
                    seen_ids.add(job.id)
                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break

            pages_fetched += 1
            log.info(f"Fetched {len(batch)} matching jobs at offset {offset} (total: {len(jobs)})")

            if len(raw_nodes) < limit:
                break

            offset += limit
            if len(jobs) < results_wanted:
                time.sleep(self.delay + random.uniform(0, self.band_delay))

        return JobResponse(jobs=jobs[:results_wanted])

    def _fetch_job_description(self, job_id: str) -> Optional[str]:
        """
        Ambil deskripsi lengkap dari query getJobById (Draft.js JSON → Markdown).
        """
        if not job_id:
            return None
        payload = {
            "operationName": "getJobById",
            "query": GET_JOB_BY_ID_QUERY,
            "variables": {"id": job_id},
        }
        try:
            res = self.session.post(
                f"{self.graphql_url}?op=getJobById",
                json=payload,
                timeout_seconds=15,
            )
            if res.status_code in range(200, 400):
                body = res.json()
                job_data = ((body.get("data") or {}).get("getJobById")) or {}
                raw_json_str = job_data.get("descriptionJsonString")
                return parse_draftjs_description(raw_json_str)
        except Exception as e:
            log.warning(f"Failed to fetch detail description for Glints job {job_id}: {e}")
        return None

    def _extract_job_nodes(self, data: dict) -> list[dict]:
        if not isinstance(data, dict):
            return []
        data_block = data.get("data")
        if not isinstance(data_block, dict):
            return []

        for key in ("searchJobs", "searchJobsV3"):
            block = data_block.get(key)
            if isinstance(block, dict) and isinstance(block.get("jobsInPage"), list):
                return [n for n in block["jobsInPage"] if isinstance(n, dict)]

        return []

    def _parse_response(
        self,
        data: dict,
        scraper_input: ScraperInput | None = None,
        country_code: str = "ID",
    ) -> List[JobPost]:
        """
        Parse payload GraphQL Glints → list[JobPost].
        """
        jobs: List[JobPost] = []
        job_nodes = self._extract_job_nodes(data)
        if not job_nodes:
            return jobs

        cfg = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["ID"])
        default_country = cfg["country_name"]
        default_currency = cfg["currency"]
        path_prefix = cfg["path_prefix"]

        cutoff_date: Optional[date] = None
        if scraper_input and scraper_input.hours_old:
            days = max(1, math.ceil(scraper_input.hours_old / 24))
            cutoff_date = date.today() - timedelta(days=days)

        loc_filter = clean_search_location(
            scraper_input.location if scraper_input else None
        )

        for node in job_nodes:
            try:
                job_id = str(node.get("id") or "").strip()
                title = str(node.get("title") or "").strip()
                if not title:
                    continue

                company = node.get("company") if isinstance(node.get("company"), dict) else {}
                company_name = company.get("name")
                company_id = company.get("id")
                company_logo_raw = company.get("logo")
                company_logo = (
                    f"https://images.glints.com/unsafe/glints-dashboard.s3.amazonaws.com/company-logo/{company_logo_raw}"
                    if company_logo_raw and not str(company_logo_raw).startswith("http")
                    else company_logo_raw
                )
                industry_obj = company.get("industry") if isinstance(company.get("industry"), dict) else {}
                company_industry = industry_obj.get("name")

                company_url = (
                    f"{self.base_url}{path_prefix}/companies/{company_id}"
                    if company_id
                    else None
                )
                job_url = (
                    f"{self.base_url}{path_prefix}/opportunities/jobs/{job_id}"
                    if job_id
                    else self.base_url
                )

                # Lokasi
                location_obj = parse_location(
                    node.get("location") if isinstance(node.get("location"), dict) else None,
                    city_node=node.get("city") if isinstance(node.get("city"), dict) else None,
                    country_node=node.get("country") if isinstance(node.get("country"), dict) else None,
                    default_country=default_country,
                )

                if loc_filter and location_obj:
                    loc_str = location_obj.display_location().lower()
                    if loc_filter.lower() not in loc_str:
                        # Tetap izinkan jika remote
                        work_arr_tmp = str(node.get("workArrangementOption") or "").upper()
                        if work_arr_tmp != "REMOTE":
                            continue

                # Tanggal posting
                date_val = node.get("createdAt") or node.get("updatedAt")
                date_posted = parse_date(date_val)
                if cutoff_date and date_posted and date_posted < cutoff_date:
                    continue

                # Tipe pekerjaan
                job_types = parse_job_type(node.get("type"))
                if (
                    scraper_input
                    and scraper_input.job_type
                    and job_types
                    and scraper_input.job_type not in job_types
                ):
                    continue

                # Work arrangement (ONSITE / HYBRID / REMOTE)
                work_arr = str(node.get("workArrangementOption") or "").upper() or None
                is_remote = work_arr == "REMOTE" or "remote" in title.lower()
                if scraper_input and scraper_input.is_remote and not is_remote:
                    continue

                # Kompensasi / Gaji
                compensation = parse_compensation(
                    node.get("salaries"),
                    default_currency=default_currency,
                )

                # Skills
                skills_list: list[str] = []
                raw_skills = node.get("skills")
                if isinstance(raw_skills, list):
                    for s_item in raw_skills:
                        if isinstance(s_item, dict):
                            sk = s_item.get("skill")
                            if isinstance(sk, dict) and sk.get("name"):
                                skills_list.append(str(sk["name"]).strip())

                # Experience & Category & Education
                exp_range = format_experience_range(
                    node.get("minYearsOfExperience"),
                    node.get("maxYearsOfExperience"),
                )
                cat_obj = (
                    node.get("hierarchicalJobCategory")
                    if isinstance(node.get("hierarchicalJobCategory"), dict)
                    else {}
                )
                job_function = cat_obj.get("name")
                education_level = node.get("educationLevel")

                # Deskripsi: full via getJobById hanya jika linkedin_fetch_description=True
                description = None
                if scraper_input and scraper_input.linkedin_fetch_description and job_id:
                    description = self._fetch_job_description(job_id)

                if not description:
                    description = build_summary_description(
                        title=title,
                        company_name=company_name,
                        category_name=job_function,
                        work_arrangement=work_arr,
                        experience_range=exp_range,
                        education_level=education_level,
                        skills=skills_list or None,
                    )

                if (
                    description
                    and scraper_input
                    and scraper_input.description_format == DescriptionFormat.HTML
                ):
                    description = markdown_converter(description) if "<" in description else description

                emails = extract_emails_from_text(description) if description else None

                job_post = JobPost(
                    id=job_id if job_id else None,
                    title=title,
                    company_name=company_name,
                    job_url=job_url,
                    location=location_obj,
                    description=description,
                    company_url=company_url,
                    company_logo=company_logo,
                    company_industry=company_industry,
                    job_function=job_function,
                    job_level=education_level,
                    job_type=job_types,
                    compensation=compensation,
                    date_posted=date_posted,
                    emails=emails,
                    is_remote=is_remote,
                    skills=skills_list if skills_list else None,
                    experience_range=exp_range,
                    work_from_home_type=work_arr,
                )
                jobs.append(job_post)
            except Exception as e:
                log.warning(f"Error parsing Glints job node: {e}")
                continue

        return jobs
