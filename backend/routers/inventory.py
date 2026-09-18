"""
Inventory catalog, medicine details, and demand forecasting API routes.
"""
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import numpy as np
import pandas as pd

from data_loader import STORE
from forecasting import forecast_demand
from anomaly_detection import detect_anomalies
from risk_scoring import compute_risk
from state import get_all_risk, risk_to_dict

router = APIRouter(prefix="/api/medicines", tags=["inventory"])


@router.get("")
def list_medicines(
    branch_id: Optional[str] = Query(None),
    criticality: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_risk: float = Query(0.0),
    sort: str = Query("risk_desc", enum=["risk_desc", "risk_asc", "name"]),
    limit: int = Query(500, le=1000),
):
    all_risk = get_all_risk()
    rows = all_risk
    if branch_id:
        rows = [r for r in rows if r.branch_id == branch_id]
    if criticality:
        rows = [r for r in rows if r.criticality == criticality]
    if category:
        rows = [r for r in rows if r.category.lower() == category.lower()]
    if search:
        q = search.lower()
        rows = [r for r in rows if q in r.name.lower() or q in r.medicine_id.lower() or q in r.category.lower()]
    rows = [r for r in rows if r.composite_risk_score >= min_risk]

    if sort == "risk_desc":
        rows.sort(key=lambda r: -r.composite_risk_score)
    elif sort == "risk_asc":
        rows.sort(key=lambda r: r.composite_risk_score)
    else:
        rows.sort(key=lambda r: r.name)

    return [risk_to_dict(r) for r in rows[:limit]]


@router.get("/{medicine_id}")
def medicine_detail(medicine_id: str, branch_id: str = Query(...)):
    try:
        risk = compute_risk(STORE, medicine_id, branch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    series = STORE.daily_consumption(medicine_id, branch_id=branch_id)
    forecast = forecast_demand(series, horizon_days=21)
    anomalies = detect_anomalies(series)

    orders = STORE.orders_for(medicine_id)
    orders_out = orders.sort_values("order_date", ascending=False).head(10).copy()
    
    # Sanitize orders DataFrame for robust JSON serialization (handling NaT, nan, null)
    for col in ["order_date", "expected_delivery_date", "actual_delivery_date"]:
        if col in orders_out.columns:
            orders_out[col] = orders_out[col].astype(str).replace({"NaT": "", "nan": ""})
    orders_out = orders_out.fillna("")
    recent_orders_list = orders_out.to_dict(orient="records")

    return {
        "risk": risk_to_dict(risk),
        "forecast": {
            "dates": forecast.dates,
            "p10": forecast.p10,
            "p50": forecast.p50,
            "p90": forecast.p90,
            "p95": forecast.p95,
            "model_type": forecast.model_type,
            "history_dates": forecast.history_dates,
            "history_values": forecast.history_values,
        },
        "recent_anomalies": [asdict(a) for a in anomalies[-10:]],
        "recent_orders": recent_orders_list,
    }


@router.get("/{medicine_id}/forecast")
def medicine_forecast(medicine_id: str, branch_id: Optional[str] = Query(None), horizon_days: int = Query(21, le=90)):
    series = STORE.daily_consumption(medicine_id, branch_id=branch_id)
    if series.empty:
        raise HTTPException(status_code=404, detail="No consumption history found")
    forecast = forecast_demand(series, horizon_days=horizon_days)
    return asdict(forecast)
