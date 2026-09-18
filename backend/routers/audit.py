"""
Audit summary, LLM clinical rationales, and cache refresh API routes. Every route
requires login and is scoped to the caller's branch (hospital) unless they are the
network admin.
"""
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
import pandas as pd

from data_loader import STORE
from procurement_optimizer import recommend_procurement, suggest_transfers
from llm_explain import explain_risk
from risk_scoring import compute_risk
from schemas import ExplainRequest
from state import get_all_risk, invalidate_all_risk_cache, cache_age_seconds
from auth import get_current_user, resolve_branch_scope

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit/summary")
def audit_summary(user: dict = Depends(get_current_user)):
    """Generate executive audit summary report with actionable alerts and compliance readiness."""
    effective_branch = resolve_branch_scope(user, None)
    all_risk = get_all_risk(branch_id=effective_branch)
    cost_map = STORE.medicines.set_index("medicine_id")["unit_cost"].to_dict()

    critical_items = [r for r in all_risk if r.risk_tier == "Critical"]
    critical_value = sum(r.current_stock * cost_map.get(r.medicine_id, 5.0) for r in critical_items)
    total_expiry_value = sum(r.expiry_waste_units * cost_map.get(r.medicine_id, 5.0) for r in all_risk)

    # Inter-facility transfer recommendations are inherently cross-branch, so they are
    # only ever computed for the network admin; a branch-scoped audit has none.
    if user["role"] == "admin":
        transfer_ops = suggest_transfers(STORE, min_stockout_risk_pct=40.0, all_risk=all_risk)
    else:
        transfer_ops = []
    proc_ops, total_spend = recommend_procurement(STORE, top_n=5, all_risk=all_risk)

    return {
        "audit_timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "compliance_status": "COMPLIANT_WITH_ACTION_REQUIRED" if critical_items else "OPTIMAL",
        "system_health_score": max(0, int(100 - len(critical_items) * 3 - (sum(r.stockout_probability_pct for r in all_risk) / len(all_risk)) * 0.5)) if all_risk else 100,
        "critical_skus_count": len(critical_items),
        "critical_skus_inventory_value": round(critical_value, 2),
        "projected_expiry_loss_value": round(total_expiry_value, 2),
        "overdue_incoming_units": sum(r.overdue_orders_units for r in all_risk),
        "recommended_transfer_actions_count": len(transfer_ops),
        "immediate_transfers": [asdict(t) for t in transfer_ops[:3]],
        "top_procurement_actions": [asdict(p) for p in proc_ops],
        "dispatched_transfers_recorded": len(STORE.dispatched_transfers) if user["role"] == "admin" else len(
            [t for t in STORE.dispatched_transfers if t.get("from_branch") == user["branch_id"] or t.get("to_branch") == user["branch_id"]]
        ),
        "dispatched_orders_recorded": len(STORE.dispatched_orders) if user["role"] == "admin" else len(
            [o for o in STORE.dispatched_orders if o.get("branch_id") == user["branch_id"]]
        ),
    }


@router.post("/explain")
def explain(req: ExplainRequest, user: dict = Depends(get_current_user)):
    effective_branch = resolve_branch_scope(user, req.branch_id)
    try:
        risk = compute_risk(STORE, req.medicine_id, effective_branch)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # facts is built from exactly one (medicine, branch) risk computation -- there is
    # no code path here or in llm_explain.py that could merge two branches'/hospitals'
    # numbers into a single prompt.
    facts = asdict(risk)
    branch_row = STORE.branches[STORE.branches.branch_id == effective_branch]
    branch_name = branch_row.iloc[0]["name"] if not branch_row.empty else effective_branch
    facts["hospital_id"] = effective_branch
    facts["hospital_name"] = branch_name

    result = explain_risk(facts, api_key=req.api_key)
    return result


@router.post("/refresh")
def refresh_cache(user: dict = Depends(get_current_user)):
    effective_branch = resolve_branch_scope(user, None)
    invalidate_all_risk_cache()
    get_all_risk(branch_id=effective_branch, force=True)
    return {"status": "refreshed", "computed_at": cache_age_seconds(effective_branch)}
