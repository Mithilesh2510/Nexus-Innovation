"""
Shared state, cache, and helper functions for Healthcare Supply Chain Intelligence API.

Risk is cached per scope key: a specific branch_id, or "__ALL__" for the network-wide
computation (only ever requested by an admin user). Keying the cache this way means a
branch-scoped request can never be served from -- or pollute -- another branch's or the
network-wide cache.
"""
import time
from dataclasses import asdict
from typing import List, Optional

from data_loader import STORE
from risk_scoring import compute_all_risk, RiskBreakdown

CACHE_TTL_SECONDS = 120
_cache: dict = {}  # scope_key -> {"data": [...], "computed_at": ts}


def _scope_key(branch_id: Optional[str]) -> str:
    return branch_id or "__ALL__"


def get_all_risk(branch_id: Optional[str] = None, force: bool = False) -> List[RiskBreakdown]:
    now = time.time()
    key = _scope_key(branch_id)
    entry = _cache.get(key)
    if force or entry is None or (now - entry["computed_at"]) > CACHE_TTL_SECONDS:
        entry = {"data": compute_all_risk(STORE, branch_id=branch_id), "computed_at": now}
        _cache[key] = entry
    return entry["data"]


def cache_age_seconds(branch_id: Optional[str] = None) -> float:
    entry = _cache.get(_scope_key(branch_id))
    if entry is None:
        return 0.0
    return round(time.time() - entry["computed_at"], 1)


def invalidate_all_risk_cache():
    """Data was mutated (an order or transfer was dispatched) -- every cached scope
    (every branch, and the network-wide aggregate) is now potentially stale."""
    _cache.clear()


def risk_to_dict(r) -> dict:
    return asdict(r)
