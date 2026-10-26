"""
JobStreet (SEEK platform) — headers, multi-country config, dan konstanta API v5.
"""

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "origin": "https://id.jobstreet.com",
    "referer": "https://id.jobstreet.com/id/jobs",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "x-seek-site": "Jobstreet",
}

# Mapping kode negara APAC ke konfigurasi SEEK / JobStreet v5 API
COUNTRY_CONFIG = {
    "ID": {
        "base_url": "https://id.jobstreet.com",
        "site_key": "ID-Main",
        "country_name": "Indonesia",
        "currency": "IDR",
        "job_path": "/id/job",
    },
    "MY": {
        "base_url": "https://my.jobstreet.com",
        "site_key": "MY-Main",
        "country_name": "Malaysia",
        "currency": "MYR",
        "job_path": "/job",
    },
    "SG": {
        "base_url": "https://sg.jobstreet.com",
        "site_key": "SG-Main",
        "country_name": "Singapore",
        "currency": "SGD",
        "job_path": "/job",
    },
    "PH": {
        "base_url": "https://ph.jobstreet.com",
        "site_key": "PH-Main",
        "country_name": "Philippines",
        "currency": "PHP",
        "job_path": "/job",
    },
}
