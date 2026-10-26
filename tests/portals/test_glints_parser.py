"""
Offline unit tests untuk Glints parser (GraphQL v2 API) dan sidecar normalisasi (base.py).
Dijalankan tanpa koneksi jaringan menggunakan JSON fixture.
"""
import json
import sys
from pathlib import Path
from datetime import date

# Add jobspy directory to sys.path
JOBSPY_DIR = Path(__file__).resolve().parent.parent.parent / "jobspy"
if str(JOBSPY_DIR) not in sys.path:
    sys.path.insert(0, str(JOBSPY_DIR))

from portals.glints import Glints
from portals.glints.util import (
    resolve_country_code,
    parse_date,
    parse_location,
    parse_compensation,
    parse_job_type,
    parse_draftjs_description,
    format_experience_range,
)
from portals.base import jobposts_to_df
from jobspy.model import JobType, CompensationInterval, ScraperInput, Country
from jobspy.util import desired_order

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str = "glints_search_response.json") -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def test_parse_response_returns_jobs():
    data = load_fixture()
    scraper = Glints.__new__(Glints)
    scraper.base_url = "https://glints.com"

    jobs = scraper._parse_response(data)
    assert len(jobs) == 2

    # Job 1
    job1 = jobs[0]
    assert job1.id == "99297a29-e473-4ab5-a511-323c8e99146b"
    assert job1.title == "Python Engineer"
    assert job1.company_name == "PT First Wap International"
    assert job1.company_industry == "Telecommunications"
    assert job1.job_function == "Backend Developer"
    assert job1.job_level == "BACHELOR_DEGREE"
    assert job1.experience_range == "1 - 3 years"
    assert job1.skills == ["Python", "Django", "PostgreSQL"]
    assert job1.date_posted == date(2026, 10, 18)
    assert job1.location.city == "Jakarta Selatan"
    assert job1.location.state == "DKI Jakarta"
    assert job1.location.country == "Indonesia"
    assert job1.job_type == [JobType.FULL_TIME]
    assert job1.compensation.min_amount == 9000000.0
    assert job1.compensation.max_amount == 13000000.0
    assert job1.compensation.currency == "IDR"
    assert job1.compensation.interval == CompensationInterval.MONTHLY
    assert job1.is_remote is False
    assert job1.work_from_home_type == "ONSITE"
    assert "Python, Django, PostgreSQL" in job1.description

    # Job 2
    job2 = jobs[1]
    assert job2.id == "2a1cd3ef-799e-4005-a6c1-7a1a6a344ac3"
    assert job2.title == "Remote AI & Data Engineer"
    assert job2.company_name == "Nusantara Cloud AI"
    assert job2.is_remote is True
    assert job2.work_from_home_type == "REMOTE"
    assert job2.job_type == [JobType.CONTRACT]
    assert job2.compensation is None
    assert job2.location.city == "Bandung"
    assert job2.location.country == "Indonesia"


def test_filters_remote_and_job_type():
    data = load_fixture()
    scraper = Glints.__new__(Glints)
    scraper.base_url = "https://glints.com"

    remote_input = ScraperInput(site_type=[], is_remote=True)
    remote_jobs = scraper._parse_response(data, scraper_input=remote_input)
    assert len(remote_jobs) == 1
    assert remote_jobs[0].id == "2a1cd3ef-799e-4005-a6c1-7a1a6a344ac3"

    ft_input = ScraperInput(site_type=[], job_type=JobType.FULL_TIME)
    ft_jobs = scraper._parse_response(data, scraper_input=ft_input)
    assert len(ft_jobs) == 1
    assert ft_jobs[0].id == "99297a29-e473-4ab5-a511-323c8e99146b"


def test_jobposts_to_df_structure():
    data = load_fixture()
    scraper = Glints.__new__(Glints)
    scraper.base_url = "https://glints.com"

    jobs = scraper._parse_response(data)
    df = jobposts_to_df(jobs, site="glints")

    assert list(df.columns) == desired_order
    assert len(df) == 2
    assert (df["site"] == "glints").all()
    # Sorted by date_posted descending -> job 2 (2026-10-20) first, job 1 (2026-10-18) second
    assert df["id"].iloc[0] == "2a1cd3ef-799e-4005-a6c1-7a1a6a344ac3"
    assert df["id"].iloc[1] == "99297a29-e473-4ab5-a511-323c8e99146b"
    assert df["skills"].iloc[1] == "Python, Django, PostgreSQL"
    assert df["experience_range"].iloc[1] == "1 - 3 years"
    assert df["location"].iloc[1] == "Jakarta Selatan, DKI Jakarta, Indonesia"


def test_draftjs_parser_and_helpers():
    draft_json = json.dumps(
        {
            "blocks": [
                {"text": "Job Responsibilities", "type": "header-three"},
                {"text": "Build scalable Python APIs", "type": "unordered-list-item"},
                {"text": "Write unit tests", "type": "unordered-list-item"},
            ]
        }
    )
    md = parse_draftjs_description(draft_json)
    assert "### Job Responsibilities" in md
    assert "- Build scalable Python APIs" in md
    assert "- Write unit tests" in md

    assert resolve_country_code("Jakarta", Country.USA) == "ID"
    assert resolve_country_code("Singapore", Country.USA) == "SG"
    assert resolve_country_code("Ho Chi Minh, Vietnam", Country.USA) == "VN"
    assert resolve_country_code("Taipei, Taiwan", Country.USA) == "TW"
    assert format_experience_range(1, 3) == "1 - 3 years"
    assert format_experience_range(2, 2) == "2 years"


if __name__ == "__main__":
    test_parse_response_returns_jobs()
    test_filters_remote_and_job_type()
    test_jobposts_to_df_structure()
    test_draftjs_parser_and_helpers()
    print("All Glints offline tests passed successfully!")
