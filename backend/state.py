"""
Shared state, cache, and helper functions for Healthcare Supply Chain Intelligence API.
"""
import time
from dataclasses import asdict
from typing import List

from data_loader import STORE
from risk_scoring import compute_all_risk, RiskBreakdown

_cache = {"all_risk": None, "computed_at": 0}
CACHE_TTL_SECONDS = 120


def get_all_risk(force: bool = False) -> List[RiskBreakdown]:
    now = time.time()
    if force or _cache["all_risk"] is None or (now - _cache["computed_at"]) > CACHE_TTL_SECONDS:
        _cache["all_risk"] = compute_all_risk(STORE)
        _cache["computed_at"] = now
    return _cache["all_risk"]


def risk_to_dict(r) -> dict:
    return asdict(r)
