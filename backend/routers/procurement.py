"""
Procurement recommendation, PO generation, and order history routes. Every route
requires login and is scoped to the caller's branch (hospital).

Caveat (data-model limitation, not a bug): procurement_history.csv itself has no
branch_id column -- historical purchase orders are recorded network-wide, only
inventory/consumption are per-branch. So overdue-order counts and per-medicine
order history are shared across branches for the same medicine; only budget
allocation, order dispatch, and this session's order log are branch-scoped here.
"""
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, Depends, Query

from data_loader import STORE
from procurement_optimizer import recommend_procurement
from schemas import CreateOrderRequest
from state import get_all_risk, invalidate_all_risk_cache
from auth import get_current_user, resolve_branch_scope

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


@router.get("/recommendations")
def procurement_recommendations(
    budget: Optional[float] = Query(None),
    top_n: int = Query(30, le=100),
    user: dict = Depends(get_current_user),
):
    effective_branch = resolve_branch_scope(user, None)
    all_risk = get_all_risk(branch_id=effective_branch)
    recs, spent = recommend_procurement(STORE, budget=budget, top_n=top_n, all_risk=all_risk)
    return {
        "budget": budget,
        "total_estimated_spend": spent,
        "recommendations": [
            {**asdict(r), "rationale_facts": r.rationale_facts} for r in recs
        ],
    }


@router.post("/order")
def create_procurement_order(req: CreateOrderRequest, user: dict = Depends(get_current_user)):
    """Dispatch a verified Purchase Order for an SKU. Branch-scoped accounts can only
    ever place orders against their own branch, regardless of what branch_id they send."""
    effective_branch = resolve_branch_scope(user, req.branch_id)
    record = STORE.create_order(req.medicine_id, effective_branch, req.units, req.unit_cost)
    invalidate_all_risk_cache()
    return {
        "status": "success",
        "message": f"Purchase Order {record['order_id']} dispatched for {record['ordered_units']} units of {record['medicine_name']}.",
        "order": record,
    }


@router.get("/history")
def procurement_orders_history(user: dict = Depends(get_current_user)):
    if user["role"] == "branch":
        return [o for o in STORE.dispatched_orders if o.get("branch_id") == user["branch_id"]]
    return STORE.dispatched_orders
