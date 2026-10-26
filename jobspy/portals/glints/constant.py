"""
Glints (glints.com) — headers, multi-country config, dan GraphQL queries.
"""

HEADERS = {
    "accept": "*/*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://glints.com",
    "referer": "https://glints.com/id/opportunities/jobs/explore",
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
    "x-glints-country-code": "ID",
}

COUNTRY_CONFIG = {
    "ID": {
        "country_code": "ID",
        "country_name": "Indonesia",
        "currency": "IDR",
        "path_prefix": "/id",
    },
    "SG": {
        "country_code": "SG",
        "country_name": "Singapore",
        "currency": "SGD",
        "path_prefix": "/sg",
    },
    "MY": {
        "country_code": "MY",
        "country_name": "Malaysia",
        "currency": "MYR",
        "path_prefix": "/my",
    },
    "VN": {
        "country_code": "VN",
        "country_name": "Vietnam",
        "currency": "VND",
        "path_prefix": "/vn",
    },
    "TW": {
        "country_code": "TW",
        "country_name": "Taiwan",
        "currency": "TWD",
        "path_prefix": "/tw",
    },
}

SEARCH_JOBS_QUERY = """
query searchJobs($data: JobSearchConditionInput!) {
  searchJobs(data: $data) {
    jobsInPage {
      id
      title
      workArrangementOption
      status
      createdAt
      updatedAt
      educationLevel
      type
      minYearsOfExperience
      maxYearsOfExperience
      company {
        id
        name
        logo
        industry {
          name
        }
      }
      citySubDivision {
        id
        name
      }
      city {
        id
        name
      }
      country {
        code
        name
      }
      location {
        id
        name
        formattedName
        level
        parents {
          id
          name
          formattedName
          level
        }
      }
      salaries {
        id
        salaryType
        salaryMode
        maxAmount
        minAmount
        CurrencyCode
      }
      hierarchicalJobCategory {
        id
        level
        name
      }
      skills {
        skill {
          id
          name
        }
        mustHave
      }
    }
    hasMore
  }
}
"""

GET_JOB_BY_ID_QUERY = """
query getJobById($id: String!) {
  getJobById(id: $id) {
    id
    descriptionJsonString
  }
}
"""
