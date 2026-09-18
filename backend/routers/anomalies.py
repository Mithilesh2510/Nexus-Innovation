"""
Control-chart anomaly detection & model validation API routes. Every route requires
login and is scoped to the caller's branch (hospital) via resolve_branch_scope().
"""
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from data_loader import STORE
from anomaly_detection import detect_anomalies, validate_detector
from auth import get_current_user, resolve_branch_scope

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
def anomalies(medicine_id: str = Query(...), branch_id: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    effective_branch = resolve_branch_scope(user, branch_id)
    series = STORE.daily_consumption(medicine_id, branch_id=effective_branch)
    if series.empty:
        raise HTTPException(status_code=404, detail="No consumption history found")
    flags = detect_anomalies(series)
    return [asdict(f) for f in flags]


@router.get("/validate")
def anomalies_validate(sample_size: Optional[int] = Query(None), user: dict = Depends(get_current_user)):
    """Validates the EWMA/CUSUM detector against usage_anomalies.csv ground-truth labels,
    restricted to the caller's own branch (hospital) unless they are the network admin."""
    effective_branch = resolve_branch_scope(user, None)
    return validate_detector(STORE, sample_size=sample_size, branch_id=effective_branch)
