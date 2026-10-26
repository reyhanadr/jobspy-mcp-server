import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gc
import os
import sys
import pandas as pd
from jobspy import scrape_jobs

# Ensure UTF-8 output on all platforms (especially Windows cp1252 consoles)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Upstream sites that work cleanly with scrape_jobs()
UPSTREAM_SITES = {
    "indeed",
    "linkedin",
    "zip_recruiter",
    "glassdoor",
    "google",
    "bayt",
    "naukri",
}

# Try importing sidecar scrapers and helper
try:
    from portals import LOCAL_SCRAPERS
    from portals.base import jobposts_to_df
except ImportError:
    LOCAL_SCRAPERS = {}
    jobposts_to_df = None


def is_local_portals_enabled() -> bool:
    val = os.environ.get("ENABLE_LOCAL_PORTALS", "true").strip().lower()
    return val not in ("0", "false", "no", "off")


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape jobs from various sites")
    parser.add_argument(
        "--site_name",
        default="indeed",
        help="Comma-separated list of sites to scrape: indeed,linkedin,zip_recruiter,glassdoor,google,bayt,naukri,bdjobs,jobstreet,glints",
    )
    parser.add_argument("--search_term", default="software engineer", help="Search term for jobs")
    parser.add_argument(
        "--google_search_term",
        default="software engineer jobs near San Francisco, CA since yesterday",
        help="Google specific search term",
    )
    parser.add_argument("--location", default="San Francisco, CA", help="Location for job search")
    parser.add_argument("--distance", type=int, default=50, help="Distance in miles (default: 50)")
    parser.add_argument(
        "--job_type",
        choices=["fulltime", "parttime", "internship", "contract"],
        help="Type of job (fulltime, parttime, internship, contract)",
    )
    parser.add_argument("--results_wanted", type=int, default=20, help="Number of results wanted")
    parser.add_argument(
        "--easy_apply",
        action="store_true",
        help="Filter for jobs that are hosted on the job board site",
    )
    parser.add_argument(
        "--description_format",
        default="markdown",
        choices=["markdown", "html"],
        help="Format type of the job descriptions (default: markdown)",
    )
    parser.add_argument("--offset", type=int, default=0, help="Starts the search from an offset")
    parser.add_argument("--hours_old", type=int, default=72, help="How many hours old the jobs can be")
    parser.add_argument(
        "--verbose",
        type=int,
        default=2,
        choices=[0, 1, 2],
        help="Controls verbosity (0=errors only, 1=errors+warnings, 2=all logs)",
    )
    parser.add_argument("--country_indeed", default="USA", help="Country for Indeed search")
    parser.add_argument("--is_remote", action="store_true", help="Whether to search for remote jobs only")
    parser.add_argument(
        "--linkedin_fetch_description",
        action="store_true",
        help="Fetch full job descriptions (slower)",
    )
    parser.add_argument(
        "--linkedin_company_ids",
        help="Comma-separated list of LinkedIn company IDs",
    )
    parser.add_argument(
        "--enforce_annual_salary",
        action="store_true",
        help="Converts wages to annual salary",
    )
    parser.add_argument("--proxies", help="Comma-separated list of proxies")
    parser.add_argument("--ca_cert", help="Path to CA Certificate file for proxies")
    parser.add_argument(
        "--output",
        help="Output file path without extension. If not provided, outputs to stdout",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=["csv", "json"],
        help="Output format (csv or json)",
    )
    return parser.parse_args()


def build_scraper_input(args, linkedin_company_ids=None):
    """
    Konversi argparse Namespace ke ScraperInput untuk sidecar scraper.
    """
    from jobspy.model import ScraperInput, Country, DescriptionFormat
    from jobspy.util import get_enum_from_value, set_logger_level

    set_logger_level(args.verbose)

    country = Country.USA
    if args.country_indeed:
        try:
            country = Country.from_string(args.country_indeed)
        except Exception:
            country = Country.USA

    desc_format = (
        DescriptionFormat.HTML
        if args.description_format == "html"
        else DescriptionFormat.MARKDOWN
    )

    job_type_enum = get_enum_from_value(args.job_type) if args.job_type else None

    return ScraperInput(
        site_type=[],
        search_term=args.search_term,
        google_search_term=args.google_search_term,
        location=args.location,
        distance=args.distance,
        is_remote=args.is_remote,
        job_type=job_type_enum,
        easy_apply=args.easy_apply,
        description_format=desc_format,
        linkedin_fetch_description=args.linkedin_fetch_description,
        linkedin_company_ids=linkedin_company_ids,
        offset=args.offset,
        hours_old=args.hours_old,
        results_wanted=args.results_wanted,
        country=country,
    )


def scrape_bdjobs_safely(args, proxies, linkedin_company_ids=None):
    """
    Eksekusi BDJobs secara aman tanpa bug 'user_agent' kwarg di upstream.
    """
    try:
        from jobspy.bdjobs import BDJobs
        from jobspy.model import Site

        scraper_input = build_scraper_input(args, linkedin_company_ids=linkedin_company_ids)
        scraper_input.site_type = [Site.BDJOBS]
        scraper = BDJobs(proxies=proxies, ca_cert=args.ca_cert)
        resp = scraper.scrape(scraper_input)
        if jobposts_to_df:
            return jobposts_to_df(
                resp.jobs,
                site="bdjobs",
                enforce_annual_salary=args.enforce_annual_salary,
            )
    except Exception as e:
        print(f"warning: bdjobs scraper failed: {e}", file=sys.stderr)
    return pd.DataFrame()


def snake_to_camel(name: str) -> str:
    if not isinstance(name, str):
        return name
    parts = [p for p in name.split("_") if p]
    if not parts:
        return name
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def main():
    args = parse_args()

    # Convert comma-separated string to list
    site_names = [s.strip() for s in args.site_name.split(",") if s.strip()]

    # Parse proxies if provided
    proxies = [p.strip() for p in args.proxies.split(",") if p.strip()] if args.proxies else None

    # Parse LinkedIn company IDs if provided
    linkedin_company_ids = (
        [int(cid.strip()) for cid in args.linkedin_company_ids.split(",") if cid.strip()]
        if args.linkedin_company_ids
        else None
    )

    # Multiplexing sites
    upstream_requested = [s for s in site_names if s in UPSTREAM_SITES]
    local_requested = [s for s in site_names if s in LOCAL_SCRAPERS]
    bdjobs_requested = "bdjobs" in site_names

    known_sites = UPSTREAM_SITES | set(LOCAL_SCRAPERS.keys()) | {"bdjobs"}
    unknown_sites = [s for s in site_names if s not in known_sites]
    if unknown_sites:
        print(f"warning: unknown sites ignored: {unknown_sites}", file=sys.stderr)

    frames = []

    # 1. Jalankan scraper upstream jika ada
    if upstream_requested:
        try:
            df_upstream = scrape_jobs(
                site_name=upstream_requested,
                search_term=args.search_term,
                google_search_term=args.google_search_term,
                location=args.location,
                distance=args.distance,
                job_type=args.job_type,
                results_wanted=args.results_wanted,
                easy_apply=args.easy_apply,
                description_format=args.description_format,
                offset=args.offset,
                hours_old=args.hours_old,
                verbose=args.verbose,
                country_indeed=args.country_indeed,
                is_remote=args.is_remote,
                linkedin_fetch_description=args.linkedin_fetch_description,
                linkedin_company_ids=linkedin_company_ids,
                enforce_annual_salary=args.enforce_annual_salary,
                proxies=proxies,
                ca_cert=args.ca_cert,
            )
            if df_upstream is not None and not df_upstream.empty:
                frames.append(df_upstream)
        except Exception as e:
            print(f"warning: upstream scrape_jobs failed: {e}", file=sys.stderr)
        finally:
            gc.collect()

    # 2. Jalankan bdjobs jika diminta (via direct scraper call untuk menghindari upstream kwarg bug)
    if bdjobs_requested:
        df_bdjobs = scrape_bdjobs_safely(args, proxies, linkedin_company_ids=linkedin_company_ids)
        if df_bdjobs is not None and not df_bdjobs.empty:
            frames.append(df_bdjobs)
        gc.collect()

    # 3. Jalankan sidecar scraper lokal dengan ThreadPoolExecutor(max_workers=2) & fail-soft
    if local_requested:
        if not is_local_portals_enabled():
            print(
                f"warning: local portals {local_requested} skipped because ENABLE_LOCAL_PORTALS is disabled",
                file=sys.stderr,
            )
        elif LOCAL_SCRAPERS and jobposts_to_df:
            scraper_input = build_scraper_input(args, linkedin_company_ids=linkedin_company_ids)

            def _run_local(portal_name: str) -> pd.DataFrame:
                scraper_cls = LOCAL_SCRAPERS[portal_name]
                scraper = scraper_cls(proxies=proxies, ca_cert=args.ca_cert)
                resp = scraper.scrape(scraper_input)
                return jobposts_to_df(
                    resp.jobs,
                    site=portal_name,
                    enforce_annual_salary=args.enforce_annual_salary,
                )

            max_workers = min(2, len(local_requested))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_name = {
                    executor.submit(_run_local, name): name for name in local_requested
                }
                for future in as_completed(future_to_name):
                    name = future_to_name[future]
                    try:
                        df_local = future.result()
                        if df_local is not None and not df_local.empty:
                            frames.append(df_local)
                    except Exception as e:
                        print(f"warning: {name} sidecar scraper failed: {e}", file=sys.stderr)
            gc.collect()

    jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # Output based on selected format
    if args.output:
        output_file = f"{args.output}.{args.format}"
        if args.format == "csv":
            jobs.to_csv(output_file, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
            print(f"Jobs saved to {output_file}")
        elif args.format == "json":
            if jobs is not None and not jobs.empty:
                jobs = jobs.rename(columns={col: snake_to_camel(col) for col in jobs.columns})
                jobs_json = jobs.to_json(orient="records", date_format="iso")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(f'{{"count":{len(jobs)},"jobs":{jobs_json}}}')
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write('{"count":0,"jobs":[]}')
            print(f"Jobs saved to {output_file}")
    else:
        # Output to stdout
        if args.format == "csv":
            jobs.to_csv(sys.stdout, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
        elif args.format == "json":
            if jobs is not None and not jobs.empty:
                jobs = jobs.rename(columns={col: snake_to_camel(col) for col in jobs.columns})
                jobs_json = jobs.to_json(orient="records", date_format="iso")
                sys.stdout.write(f'{{"count":{len(jobs)},"jobs":{jobs_json}}}\n')
            else:
                sys.stdout.write('{"count":0,"jobs":[]}\n')
            sys.stdout.flush()


if __name__ == "__main__":
    main()
