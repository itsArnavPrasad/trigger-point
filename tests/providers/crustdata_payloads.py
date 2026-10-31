"""Response payloads shaped exactly like docs.crustdata.com examples (API 2025-11-01)."""

from typing import Any


def basic(cid: int, name: str, domain: str, url: str, size: str = "51-200") -> dict[str, Any]:
    return {
        "crustdata_company_id": cid,
        "name": name,
        "primary_domain": domain,
        "all_domains": [domain],
        "website": f"https://{domain}",
        "professional_network_url": url,
        "professional_network_id": str(cid),
        "profile_name": name,
        "logo_permalink": None,
        "description": None,
        "company_type": None,
        "year_founded": None,
        "employee_count_range": size,
        "markets": None,
        "industries": ["Software Development"],
    }


def match(cid: int, name: str, domain: str, url: str, score: float = 1) -> dict[str, Any]:
    return {
        "confidence_score": score,
        "company_data": {"crustdata_company_id": cid, "basic_info": basic(cid, name, domain, url)},
    }


# docs example "exact_domain_multiple_matches": cashfree.com -> company + two showcase pages
CASHFREE = [
    {
        "matched_on": "cashfree.com",
        "match_type": "domain",
        "matches": [
            match(
                622934,
                "Cashfree Payments",
                "cashfree.com",
                "https://www.linkedin.com/company/cashfree",
            ),
            match(
                908846,
                "Cashfree Tech",
                "cashfree.com",
                "https://www.linkedin.com/showcase/cashfree-tech/",
            ),
            match(
                10956299,
                "WTFraud",
                "cashfree.com",
                "https://www.linkedin.com/showcase/wtfraud-community/",
            ),
        ],
    }
]

# docs example "identify_by_name_response": three different companies, all confidence 1
SERVE_BY_NAME = [
    {
        "matched_on": "Serve Robotics",
        "match_type": "name",
        "matches": [
            match(
                628895,
                "Serve Robotics",
                "serverobotics.com",
                "https://www.linkedin.com/company/serverobotics",
            ),
            match(
                5825197,
                "Site Serve Robotics",
                "siteserverobotics.co.uk",
                "https://www.linkedin.com/company/site-serve-robotics",
            ),
            match(
                25592234,
                "iServe Robotics",
                "iserve.ai",
                "https://www.linkedin.com/company/iserve-robotics",
            ),
        ],
    }
]

NO_MATCH = [
    {"matched_on": "thisdomaindoesnotexist12345xyz.com", "match_type": "domain", "matches": []}
]


def company_record(cid: int, name: str, domain: str, **extra: Any) -> dict[str, Any]:
    return {
        "crustdata_company_id": cid,
        "basic_info": {
            "name": name,
            "primary_domain": domain,
            "website": f"https://{domain}",
            "professional_network_url": f"https://www.linkedin.com/company/{cid}",
            "employee_count_range": "201-500",
            "industries": ["Software Development"],
        },
        "headcount": {
            "total": 320,
            "growth_percent": {"1m": 1.2, "3m": 4.0, "6m": 9.5, "12m": 21.0},
        },
        "hiring": {"openings_count": 14},
        "updated_at": "2026-10-23T00:00:00Z",
        **extra,
    }


SEARCH_PAGE = {
    "companies": [
        company_record(1001, "Ledgerloop", "ledgerloop.example"),
        company_record(1002, "Quartzdesk", "quartzdesk.example"),
    ],
    "next_cursor": None,
    "total_count": 2,
}
