"""
Audit summary, LLM clinical rationales, and cache refresh API routes.
"""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException
import pandas as pd

from data_loader import STORE
from procurement_optimizer import recommend_procurement, suggest_transfers
from llm_explain import explain_risk
from risk_scoring import compute_risk
from schemas import ExplainRequest
from state import get_all_risk, _cache

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit/summary")
def audit_summary():
    """Generate executive audit summary report with actionable alerts and compliance readiness."""
    all_risk = get_all_risk()
    cost_map = STORE.medicines.set_index("medicine_id")["unit_cost"].to_dict()

    critical_items = [r for r in all_risk if r.risk_tier == "Critical"]
    critical_value = sum(r.current_stock * cost_map.get(r.medicine_id, 5.0) for r in critical_items)
    total_expiry_value = sum(r.expiry_waste_units * cost_map.get(r.medicine_id, 5.0) for r in all_risk)
    
    transfer_ops = suggest_transfers(STORE, min_stockout_risk_pct=40.0, all_risk=all_risk)
    proc_ops, total_spend = recommend_procurement(STORE, top_n=5, all_risk=all_risk)

    return {
        "audit_timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "compliance_status": "COMPLIANT_WITH_ACTION_REQUIRED" if critical_items else "OPTIMAL",
        "system_health_score": max(0, int(100 - len(critical_items) * 3 - (sum(r.stockout_probability_pct for r in all_risk) / len(all_risk)) * 0.5)),
        "critical_skus_count": len(critical_items),
        "critical_skus_inventory_value": round(critical_value, 2),
        "projected_expiry_loss_value": round(total_expiry_value, 2),
        "overdue_incoming_units": sum(r.overdue_orders_units for r in all_risk),
        "recommended_transfer_actions_count": len(transfer_ops),
        "immediate_transfers": [asdict(t) for t in transfer_ops[:3]],
        "top_procurement_actions": [asdict(p) for p in proc_ops],
        "dispatched_transfers_recorded": len(STORE.dispatched_transfers),
        "dispatched_orders_recorded": len(STORE.dispatched_orders),
    }


@router.post("/explain")
def explain(req: ExplainRequest):
    try:
        risk = compute_risk(STORE, req.medicine_id, req.branch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    facts = asdict(risk)
    result = explain_risk(facts, api_key=req.api_key)
    return result


@router.post("/refresh")
def refresh_cache():
    get_all_risk(force=True)
    return {"status": "refreshed", "computed_at": _cache["computed_at"]}
