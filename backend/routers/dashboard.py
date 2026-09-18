"""
Dashboard and metadata API routes. Every route requires login; results are scoped
to the caller's branch (hospital) unless the caller is the network-wide admin.
"""
from fastapi import APIRouter, Depends
from data_loader import STORE
from state import get_all_risk, cache_age_seconds
from auth import get_current_user, resolve_branch_scope

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/branches")
def get_branches(user: dict = Depends(get_current_user)):
    if user["role"] == "branch":
        return STORE.branches[STORE.branches.branch_id == user["branch_id"]].to_dict(orient="records")
    return STORE.branches.to_dict(orient="records")


@router.get("/categories")
def get_categories(user: dict = Depends(get_current_user)):
    # Medicine categories are catalog metadata (medicines.csv has no branch_id), so
    # this list is identical for every branch -- nothing to scope.
    categories = sorted(STORE.medicines["category"].unique().tolist())
    return categories


@router.get("/dashboard/summary")
def dashboard_summary(user: dict = Depends(get_current_user)):
    branch_id = resolve_branch_scope(user, None)
    all_risk = get_all_risk(branch_id=branch_id)
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

    dispatched_transfers = STORE.dispatched_transfers
    dispatched_orders = STORE.dispatched_orders
    if user["role"] == "branch":
        dispatched_transfers = [
            t for t in dispatched_transfers
            if t.get("from_branch") == user["branch_id"] or t.get("to_branch") == user["branch_id"]
        ]
        dispatched_orders = [o for o in dispatched_orders if o.get("branch_id") == user["branch_id"]]

    return {
        "total_skus_tracked": len(STORE.medicines),
        "total_branch_sku_pairs": len(all_risk),
        "risk_tier_counts": {"Critical": n_critical, "High": n_high, "Moderate": n_moderate, "Low": n_low},
        "avg_stockout_probability_pct": avg_stockout,
        "total_overdue_incoming_units": total_overdue_units,
        "total_projected_expiry_waste_units": total_expiry_waste,
        "total_inventory_value": round(total_inventory_value, 2),
        "total_expiry_value": round(total_expiry_value, 2),
        "dispatched_transfers_count": len(dispatched_transfers),
        "dispatched_orders_count": len(dispatched_orders),
        "cache_age_seconds": cache_age_seconds(branch_id),
    }
