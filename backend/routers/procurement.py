"""
Procurement recommendation, PO generation, and order history routes.
"""
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, Query

from data_loader import STORE
from procurement_optimizer import recommend_procurement
from schemas import CreateOrderRequest
from state import get_all_risk

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("/recommendations")
def procurement_recommendations(budget: Optional[float] = Query(None), top_n: int = Query(30, le=100)):
    all_risk = get_all_risk()
    recs, spent = recommend_procurement(STORE, budget=budget, top_n=top_n, all_risk=all_risk)
    return {
        "budget": budget,
        "total_estimated_spend": spent,
        "recommendations": [
            {**asdict(r), "rationale_facts": r.rationale_facts} for r in recs
        ],
    }


@router.post("/order")
def create_procurement_order(req: CreateOrderRequest):
    """Dispatch a verified Purchase Order for an SKU."""
    record = STORE.create_order(req.medicine_id, req.branch_id, req.units, req.unit_cost)
    get_all_risk(force=True)
    return {
        "status": "success",
        "message": f"Purchase Order {record['order_id']} dispatched for {record['ordered_units']} units of {record['medicine_name']}.",
        "order": record,
    }


@router.get("/history")
def procurement_orders_history():
    return STORE.dispatched_orders
