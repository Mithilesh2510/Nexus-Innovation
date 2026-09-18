"""
Hardcoded authentication and per-branch (hospital) access scoping.

No real user database, no password hashing -- this is a demo/hackathon-grade auth
layer, intentionally simple. What matters is that it is enforced *server-side*:

  - Each branch account is locked to its own branch_id via resolve_branch_scope(),
    which ignores whatever branch_id the client sends and substitutes the caller's
    own branch_id. A branch-scoped login can never read or influence another
    branch's (hospital's) data no matter what query params or body fields it sends.
  - Only the "admin" account (network-wide) may see cross-branch data or use
    features that inherently require it (inter-facility transfers, the macro
    network stress-tester).

This codebase's existing multi-facility dimension is `branch_id` (see
data/branches.csv), so that is the identifier used for hospital-level isolation
throughout -- there is no separate `hospital_id` column anywhere in the data.
"""
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException

USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin",
        "branch_id": None,
        "branch_name": "All Facilities (Network)",
    },
    "citygeneral": {
        "password": "demo123",
        "role": "branch",
        "branch_id": "BR01",
        "branch_name": "City General Hospital",
    },
    "riverside": {
        "password": "demo123",
        "role": "branch",
        "branch_id": "BR02",
        "branch_name": "Riverside Community Hospital",
    },
    "northdistrict": {
        "password": "demo123",
        "role": "branch",
        "branch_id": "BR03",
        "branch_name": "North District Clinic",
    },
}

# token -> username. In-memory only; resets on process restart.
TOKENS: dict[str, str] = {}


def create_token(username: str) -> str:
    token = secrets.token_hex(24)
    TOKENS[token] = username
    return token


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Resolves the caller's user record from an `Authorization: Bearer <token>`
    header. Raises 401 if the header is missing, malformed, or the token unknown.
    Every data-bearing endpoint in this app depends on this (directly, or via
    require_admin) before it does anything else."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[len("Bearer "):].strip()
    username = TOKENS.get(token)
    if username is None or username not in USERS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = dict(USERS[username])
    user["username"] = username
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency for endpoints that inherently require cross-branch visibility
    (inter-facility transfers, the macro network stress-tester). Branch-scoped
    accounts get 403."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="This endpoint requires network-wide (admin) access")
    return user


def resolve_branch_scope(user: dict, requested_branch_id: Optional[str] = None) -> Optional[str]:
    """Given the current user and whatever branch_id (if any) the client asked
    for, returns the branch_id that should actually be used.

    - Branch-role accounts are ALWAYS forced to their own branch_id, regardless
      of what the client sent in a query param or request body -- this is what
      makes the isolation server-side rather than trust-the-client.
    - Admin may pass through a specific branch_id, or None for network-wide.
    """
    if user["role"] == "branch":
        return user["branch_id"]
    return requested_branch_id
