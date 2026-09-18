"""
Control-chart anomaly detection & model validation API routes.
"""
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from data_loader import STORE
from anomaly_detection import detect_anomalies, validate_detector

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
def anomalies(medicine_id: str = Query(...), branch_id: Optional[str] = Query(None)):
    series = STORE.daily_consumption(medicine_id, branch_id=branch_id)
    if series.empty:
        raise HTTPException(status_code=404, detail="No consumption history found")
    flags = detect_anomalies(series)
    return [asdict(f) for f in flags]


@router.get("/validate")
def anomalies_validate(sample_size: Optional[int] = Query(None)):
    """Validates the EWMA/CUSUM detector against usage_anomalies.csv ground-truth labels."""
    return validate_detector(STORE, sample_size=sample_size)
