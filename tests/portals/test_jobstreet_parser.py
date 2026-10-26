"""
Offline unit tests untuk JobStreet parser (SEEK v5 REST API) dan sidecar normalisasi (base.py).
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

from portals.jobstreet import JobStreet
from portals.jobstreet.util import (
    resolve_country_code,
    clean_where_location,
    parse_date,
    parse_location,
    parse_compensation,
    parse_job_type,
    parse_work_arrangement,
)
from portals.base import jobposts_to_df
from jobspy.model import JobType, CompensationInterval, ScraperInput, Country
from jobspy.util import desired_order

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str = "jobstreet_search_response.json") -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def test_parse_response_returns_jobs():
    data = load_fixture()
    scraper = JobStreet.__new__(JobStreet)
    scraper.base_url = "https://id.jobstreet.com"

    jobs = scraper._parse_response(data)
    assert len(jobs) == 2

    # Job 1
    job1 = jobs[0]
    assert job1.id == "78901234"
    assert job1.title == "Senior Python Backend Engineer"
    assert job1.company_name == "Tech Corp Indonesia"
    assert job1.job_url == "https://id.jobstreet.com/id/job/78901234"
    assert job1.company_url == "https://id.jobstreet.com/companies/tech-corp-indonesia-438846"
    assert job1.company_industry == "Information & Communication Technology"
    assert job1.job_function == "Developers/Programmers"
    assert job1.date_posted == date(2026, 10, 20)
    assert job1.location.city == "Jakarta Selatan"
    assert job1.location.state == "DKI Jakarta"
    assert job1.location.country == "Indonesia"
    assert job1.job_type == [JobType.FULL_TIME]
    assert job1.compensation.min_amount == 25000000.0
    assert job1.compensation.max_amount == 40000000.0
    assert job1.compensation.interval == CompensationInterval.MONTHLY
    assert job1.compensation.currency == "IDR"
    assert job1.is_remote is False
    assert job1.work_from_home_type == "On-site"
    assert "BPJS Kesehatan" in job1.description

    # Job 2
    job2 = jobs[1]
    assert job2.id == "78901235"
    assert job2.title == "Remote AI Agent Developer"
    assert job2.company_name == "Global AI Labs"
    assert job2.is_remote is True
    assert job2.work_from_home_type == "Remote"
    assert job2.job_type == [JobType.CONTRACT]
    assert job2.compensation is None


def test_filters_remote_and_job_type():
    data = load_fixture()
    scraper = JobStreet.__new__(JobStreet)
    scraper.base_url = "https://id.jobstreet.com"

    remote_input = ScraperInput(site_type=[], is_remote=True)
    remote_jobs = scraper._parse_response(data, scraper_input=remote_input)
    assert len(remote_jobs) == 1
    assert remote_jobs[0].id == "78901235"

    ft_input = ScraperInput(site_type=[], job_type=JobType.FULL_TIME)
    ft_jobs = scraper._parse_response(data, scraper_input=ft_input)
    assert len(ft_jobs) == 1
    assert ft_jobs[0].id == "78901234"


def test_parse_empty_or_malformed_response():
    scraper = JobStreet.__new__(JobStreet)
    scraper.base_url = "https://id.jobstreet.com"

    assert scraper._parse_response({}) == []
    assert scraper._parse_response({"data": None}) == []
    assert scraper._parse_response({"data": []}) == []


def test_jobposts_to_df_structure():
    data = load_fixture()
    scraper = JobStreet.__new__(JobStreet)
    scraper.base_url = "https://id.jobstreet.com"

    jobs = scraper._parse_response(data)
    df = jobposts_to_df(jobs, site="jobstreet")

    assert list(df.columns) == desired_order
    assert len(df) == 2
    assert (df["site"] == "jobstreet").all()
    # Sorted by date_posted descending -> job 2 (2026-10-21) first, job 1 (2026-10-20) second
    assert df["id"].iloc[0] == "78901235"
    assert df["id"].iloc[1] == "78901234"
    assert df["location"].iloc[1] == "Jakarta Selatan, DKI Jakarta, Indonesia"
    assert df["min_amount"].iloc[1] == 25000000.0
    assert df["interval"].iloc[1] == "monthly"
    assert df["salary_source"].iloc[1] == "direct_data"


def test_country_and_location_helpers():
    assert resolve_country_code("Jakarta", Country.USA) == "ID"
    assert resolve_country_code("remote", Country.USA) == "ID"
    assert resolve_country_code("Singapore", Country.USA) == "SG"
    assert resolve_country_code("Kuala Lumpur, Malaysia", Country.USA) == "MY"
    assert resolve_country_code("Manila, Philippines", Country.USA) == "PH"

    assert clean_where_location("remote") is None
    assert clean_where_location("Indonesia") is None
    assert clean_where_location("Jakarta Selatan") == "Jakarta Selatan"


def test_salary_label_parser():
    comp_idr = parse_compensation("Rp 10.000.000 – Rp 15.000.000 per month", default_currency="IDR")
    assert comp_idr.min_amount == 10000000.0
    assert comp_idr.max_amount == 15000000.0
    assert comp_idr.currency == "IDR"
    assert comp_idr.interval == CompensationInterval.MONTHLY

    comp_myr = parse_compensation("RM 4,000 – RM 6,000 per month", default_currency="MYR")
    assert comp_myr.min_amount == 4000.0
    assert comp_myr.max_amount == 6000.0
    assert comp_myr.currency == "MYR"


def test_date_location_and_job_type_parsers():
    assert parse_date("2026-08-20T08:30:00.000Z") == date(2026, 8, 20)
    assert parse_date("2026-08-22") == date(2026, 8, 22)
    assert parse_date(None) is None
    assert parse_date("invalid-date") is None

    loc = parse_location("Bandung, Jawa Barat")
    assert loc.city == "Bandung"
    assert loc.state == "Jawa Barat"
    assert loc.country == "Indonesia"

    assert parse_job_type(["Full time"]) == [JobType.FULL_TIME]
    assert parse_job_type("Part-time") == [JobType.PART_TIME]
    assert parse_job_type("Kontrak") == [JobType.CONTRACT]
    assert parse_job_type("Magang / Internship") == [JobType.INTERNSHIP]
    assert parse_job_type("Unknown") is None

    is_rem, wfh = parse_work_arrangement({"data": [{"label": {"text": "Remote"}}]})
    assert is_rem is True
    assert wfh == "Remote"


if __name__ == "__main__":
    test_parse_response_returns_jobs()
    test_filters_remote_and_job_type()
    test_parse_empty_or_malformed_response()
    test_jobposts_to_df_structure()
    test_country_and_location_helpers()
    test_salary_label_parser()
    test_date_location_and_job_type_parsers()
    print("All JobStreet offline tests passed successfully!")
