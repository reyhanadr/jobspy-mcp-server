"""
Local portal registry — scrapers yang berjalan di luar python-jobspy upstream.
"""
from __future__ import annotations
from .jobstreet import JobStreet
from .glints import Glints

LOCAL_SCRAPERS: dict[str, type] = {
    "jobstreet": JobStreet,
    "glints": Glints,
}
