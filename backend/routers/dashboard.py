"""
Dashboard and metadata API routes.
"""
import time
from fastapi import APIRouter
from data_loader import STORE
from state import get_all_risk, _cache

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/branches")
def get_branches():
    return STORE.branches.to_dict(orient="records")


@router.get("/categories")
def get_categories():
    categories = sorted(STORE.medicines["category"].unique().tolist())
    return categories


@router.get("/dashboard/summary")
def dashboard_summary():
    all_risk = get_all_risk()
    n_critical = sum(1 for r in all_risk if r.risk_tier == "Critical")
    n_high = sum(1 for r in all_risk if r.risk_tier == "High")
    n_moderate = sum(1 for r in all_risk if r.risk_tier == "Moderate")
    n_low = sum(1 for r in all_risk if r.risk_tier == "Low")
    total_overdue_units = sum(r.overdue_orders_units for r in all_risk)
    avg_stockout = round(sum(r.stockout_probability_pct for r in all_risk) / len(all_risk), 1) if all_risk else 0
    total_expiry_waste = round(sum(r.expiry_waste_units for r in all_risk), 0)

    cost_map = STORE.medicines.set_index("medicine_id")["unit_cost"].to_dict()
    total_inventory_value = sum(
        r.current_stock * cost_map.get(r.medicine_id, 5.0) for r in all_risk
    )
    total_expiry_value = sum(
        r.expiry_waste_units * cost_map.get(r.medicine_id, 5.0) for r in all_risk
    )

    return {
        "total_skus_tracked": len(STORE.medicines),
        "total_branch_sku_pairs": len(all_risk),
        "risk_tier_counts": {"Critical": n_critical, "High": n_high, "Moderate": n_moderate, "Low": n_low},
        "avg_stockout_probability_pct": avg_stockout,
        "total_overdue_incoming_units": total_overdue_units,
        "total_projected_expiry_waste_units": total_expiry_waste,
        "total_inventory_value": round(total_inventory_value, 2),
        "total_expiry_value": round(total_expiry_value, 2),
        "dispatched_transfers_count": len(STORE.dispatched_transfers),
        "dispatched_orders_count": len(STORE.dispatched_orders),
        "cache_age_seconds": round(time.time() - _cache["computed_at"], 1),
    }
