"""
Single-SKU and Macro Network Stress Testing Simulation routes.

The single-SKU simulator is branch-scoped like every other endpoint: a branch login
is always forced to its own branch_id via resolve_branch_scope(), regardless of what
it sends. The macro network stress-tester is inherently cross-branch (it models the
whole hospital network at once) and is therefore restricted to the admin account.
"""
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
import numpy as np
import pandas as pd

from data_loader import STORE
from schemas import SimulateRequest, NetworkSimulateRequest
from risk_scoring import CRITICALITY_WEIGHT
from state import get_all_risk
from auth import get_current_user, require_admin, resolve_branch_scope

router = APIRouter(prefix="/api/simulate", tags=["simulations"])


@router.post("")
def simulate(req: SimulateRequest, user: dict = Depends(get_current_user)):
    from forecasting import forecast_demand as _fd
    from risk_scoring import monte_carlo_stockout_probability, expiry_waste_projection, CRITICALITY_WEIGHT

    effective_branch = resolve_branch_scope(user, req.branch_id)

    med = STORE.medicine_row(req.medicine_id)
    if med is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    inv_df = STORE.inventory_for(req.medicine_id, effective_branch)
    if inv_df.empty:
        raise HTTPException(status_code=404, detail="No inventory row for this medicine/branch")
    inv = inv_df.iloc[0]

    series = STORE.daily_consumption(req.medicine_id, branch_id=effective_branch)
    forecast = _fd(series, horizon_days=21)

    scaled_p50 = [v * req.demand_multiplier for v in forecast.p50]
    forecast.p50 = scaled_p50
    forecast.mean_daily_baseline = round(forecast.mean_daily_baseline * req.demand_multiplier, 2)

    supplier = STORE.supplier_for(req.medicine_id) or {"avg_lead_time_days": 10, "lead_time_std_days": 3, "reliability_score": 0.85}
    lead_mean = float(supplier["avg_lead_time_days"]) + req.lead_time_extra_days

    orders = STORE.orders_for(req.medicine_id)
    as_of = STORE.inventory["snapshot_date"].max()
    from risk_scoring import _reliable_incoming_units, _overdue_incoming_units
    reliable_incoming = _reliable_incoming_units(orders, as_of, horizon_days=21)
    overdue_units = _overdue_incoming_units(orders, as_of)

    current_stock = max(0.0, float(inv["current_stock"]) - float(inv.get("reserved_units", 0) or 0))

    stockout_prob = monte_carlo_stockout_probability(
        current_stock=current_stock, forecast=forecast, lead_time_mean=lead_mean,
        lead_time_std=float(supplier["lead_time_std_days"]), reliable_incoming=reliable_incoming,
    )
    days_to_expiry = (pd.Timestamp(inv["nearest_batch_expiry"]) - as_of).days
    waste_units, waste_risk = expiry_waste_projection(current_stock, forecast.mean_daily_baseline, days_to_expiry)

    crit_weight = CRITICALITY_WEIGHT.get(med["criticality"], 1.0)
    reliability_penalty = (1 - float(supplier["reliability_score"])) * 10
    overdue_penalty = min(15.0, overdue_units / max(med["reorder_point"], 1) * 10)
    base_score = stockout_prob * 0.55 + waste_risk * 100 * 0.20 + overdue_penalty + reliability_penalty
    composite = float(np.clip(base_score * crit_weight / 1.3, 0, 100))

    return {
        "medicine_id": req.medicine_id,
        "branch_id": effective_branch,
        "scenario": {"demand_multiplier": req.demand_multiplier, "lead_time_extra_days": req.lead_time_extra_days},
        "simulated_stockout_probability_pct": stockout_prob,
        "simulated_composite_risk_score": round(composite, 1),
        "simulated_days_of_cover": round(current_stock / forecast.mean_daily_baseline, 1) if forecast.mean_daily_baseline > 0 else 999,
        "forecast_p50": forecast.p50,
        "forecast_dates": forecast.dates,
    }


@router.post("/network")
def simulate_network_stress(req: NetworkSimulateRequest, user: dict = Depends(require_admin)):
    """
    Macro scenario stress-tester: simulates pandemic surges or supplier disruptions
    across the full hospital network without modifying underlying database.
    Cross-branch by design, so restricted to the network admin account.
    """
    all_risk = get_all_risk(branch_id=None)
    stressed_risks = []
    
    crit_before = sum(1 for r in all_risk if r.risk_tier == "Critical")
    high_before = sum(1 for r in all_risk if r.risk_tier == "High")
    avg_stockout_before = np.mean([r.stockout_probability_pct for r in all_risk])

    for r in all_risk:
        is_affected = True
        if req.affected_categories and r.category not in req.affected_categories:
            is_affected = False
        if req.affected_branches and r.branch_id not in req.affected_branches:
            is_affected = False

        if not is_affected:
            stressed_risks.append(r)
            continue

        lead_shock = req.lead_time_extra_days * 2.5
        demand_shock = (req.demand_multiplier - 1.0) * 35.0
        new_stockout = float(np.clip(r.stockout_probability_pct + demand_shock + lead_shock, 0.0, 100.0))
        
        crit_weight = CRITICALITY_WEIGHT.get(r.criticality, 1.0)
        new_base = (
            new_stockout * 0.55
            + r.expiry_waste_risk_score * 100 * 0.20
            + (min(15.0, r.overdue_orders_units / 50.0 * 10))
            + (1 - r.supplier_reliability) * 10
        )
        new_comp = float(np.clip(new_base * crit_weight / 1.3, 0.0, 100.0))
        
        tier = "Critical" if new_comp >= 70 else ("High" if new_comp >= 45 else ("Moderate" if new_comp >= 25 else "Low"))
        
        cloned = asdict(r)
        cloned["stockout_probability_pct"] = round(new_stockout, 1)
        cloned["composite_risk_score"] = round(new_comp, 1)
        cloned["risk_tier"] = tier
        cloned["days_of_cover_p50"] = round(r.days_of_cover_p50 / max(req.demand_multiplier, 0.1), 1)
        stressed_risks.append(cloned)

    crit_after = sum(1 for r in stressed_risks if (r.risk_tier if hasattr(r, 'risk_tier') else r['risk_tier']) == "Critical")
    high_after = sum(1 for r in stressed_risks if (r.risk_tier if hasattr(r, 'risk_tier') else r['risk_tier']) == "High")
    avg_stockout_after = np.mean([
        (r.stockout_probability_pct if hasattr(r, 'stockout_probability_pct') else r['stockout_probability_pct'])
        for r in stressed_risks
    ])

    return {
        "scenario_name": req.scenario_name,
        "impact_summary": {
            "critical_skus_before": crit_before,
            "critical_skus_after": crit_after,
            "critical_delta": crit_after - crit_before,
            "high_skus_before": high_before,
            "high_skus_after": high_after,
            "avg_stockout_pct_before": round(avg_stockout_before, 1),
            "avg_stockout_pct_after": round(avg_stockout_after, 1),
            "stockout_delta_pct": round(avg_stockout_after - avg_stockout_before, 1),
        },
        "top_vulnerable_skus": sorted(
            [r if isinstance(r, dict) else asdict(r) for r in stressed_risks],
            key=lambda x: -x["composite_risk_score"]
        )[:15],
    }
