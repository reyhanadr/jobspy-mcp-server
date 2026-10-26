"""
base.py — Normalisasi output scraper sidecar ke struktur DataFrame
          yang identik dengan output upstream scrape_jobs(),
          sehingga bisa langsung digabung via pd.concat.
"""
from __future__ import annotations

import pandas as pd
from datetime import date
from jobspy.model import JobPost, Location, SalarySource
from jobspy.util import desired_order, convert_to_annual


def jobposts_to_df(
    jobs: list[JobPost],
    site: str,
    enforce_annual_salary: bool = False,
) -> pd.DataFrame:
    """
    Konversi list JobPost ke DataFrame dengan kolom desired_order.
    Kolom yang tidak diisi portal otomatis bernilai None (NaN),
    sama persis dengan perilaku upstream scrape_jobs().
    """
    if not jobs:
        return pd.DataFrame(columns=desired_order)

    rows = []
    for job in jobs:
        comp = job.compensation
        loc = job.location

        if isinstance(loc, Location):
            loc_str = loc.display_location()
        elif isinstance(loc, dict):
            loc_str = Location(**loc).display_location()
        elif loc:
            loc_str = str(loc)
        else:
            loc_str = None

        min_amount = comp.min_amount if comp else None
        max_amount = comp.max_amount if comp else None
        interval_val = (
            comp.interval.value
            if comp and hasattr(comp, "interval") and comp.interval
            else None
        )
        currency_val = (comp.currency if comp and comp.currency else "USD") if comp else None
        has_salary = min_amount is not None or max_amount is not None

        emails_val = (
            ", ".join(job.emails)
            if isinstance(job.emails, list) and job.emails
            else (job.emails if isinstance(job.emails, str) else None)
        )
        skills_val = (
            ", ".join(job.skills)
            if isinstance(job.skills, list) and job.skills
            else (job.skills if isinstance(job.skills, str) else None)
        )

        row = {
            "id": job.id,
            "site": site,
            "job_url": job.job_url,
            "job_url_direct": job.job_url_direct,
            "title": job.title,
            "company": job.company_name,
            "location": loc_str,
            "date_posted": (
                job.date_posted.isoformat()
                if isinstance(job.date_posted, date)
                else job.date_posted
            ),
            "job_type": (
                ", ".join(jt.value[0] for jt in job.job_type)
                if job.job_type
                else None
            ),
            "salary_source": SalarySource.DIRECT_DATA.value if has_salary else None,
            "interval": interval_val,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "currency": currency_val if has_salary else None,
            "is_remote": job.is_remote,
            "job_level": job.job_level,
            "job_function": job.job_function,
            "listing_type": job.listing_type,
            "emails": emails_val,
            "description": job.description,
            "company_industry": job.company_industry,
            "company_url": job.company_url,
            "company_logo": job.company_logo,
            "company_url_direct": job.company_url_direct,
            "company_addresses": job.company_addresses,
            "company_num_employees": job.company_num_employees,
            "company_revenue": job.company_revenue,
            "company_description": job.company_description,
            # Portal-specific fields
            "skills": skills_val,
            "experience_range": job.experience_range,
            "company_rating": job.company_rating,
            "company_reviews_count": job.company_reviews_count,
            "vacancy_count": job.vacancy_count,
            "work_from_home_type": job.work_from_home_type,
        }

        if (
            enforce_annual_salary
            and row["interval"]
            and row["interval"] != "yearly"
            and row["min_amount"]
            and row["max_amount"]
        ):
            convert_to_annual(row)

        rows.append(row)

    df = pd.DataFrame(rows)

    # Pastikan semua kolom desired_order ada
    for col in desired_order:
        if col not in df.columns:
            df[col] = None

    df = df[desired_order]
    return df.sort_values(
        by=["site", "date_posted"], ascending=[True, False]
    ).reset_index(drop=True)
