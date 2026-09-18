"""
Two decision-support outputs, operating on top of risk_scoring.py's numbers:

1. recommend_procurement() -- given a budget, rank SKUs by risk and recommend order
   quantities that bring each back to a safe cover level, greedily allocating budget to
   the highest-risk (criticality-weighted) items first, while respecting each SKU's
   emergency reserve floor.

2. suggest_transfers() -- the stretch novelty: instead of only ever recommending a fresh
   purchase order, check whether another branch is sitting on near-expiry surplus of the
   same SKU that a stockout-risk branch could use instead.
"""
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd

from risk_scoring import compute_risk, compute_all_risk, CRITICALITY_WEIGHT


@dataclass
class ProcurementRecommendation:
    medicine_id: str
    branch_id: str
    name: str
    category: str
    criticality: str
    composite_risk_score: float
    recommended_order_units: int
    unit_cost: float
    estimated_cost: float
    supplier_id: str
    rationale_facts: dict


@dataclass
class TransferSuggestion:
    medicine_id: str
    name: str
    category: str
    from_branch: str
    to_branch: str
    suggested_units: int
    from_branch_days_to_expiry: int
    to_branch_stockout_probability_pct: float
    rationale: str


def _target_stock_units(risk, target_cover_days: int = 21) -> float:
    return risk.forecast_daily_mean * target_cover_days + risk.emergency_reserve


def recommend_procurement(store, budget: Optional[float] = None, top_n: int = 30, all_risk: Optional[List] = None):
    """
    Allocates budget greedily to highest composite-risk items.
    Accepts precomputed all_risk to avoid recomputing simulations.
    """
    if all_risk is None:
        all_risk = compute_all_risk(store)

    risk_list = sorted(all_risk, key=lambda r: -r.composite_risk_score)
    unit_cost_lookup = store.medicines.set_index("medicine_id")["unit_cost"].to_dict()
    category_lookup = store.medicines.set_index("medicine_id")["category"].to_dict()

    recommendations = []
    spent = 0.0

    for risk in risk_list:
        if risk.risk_tier == "Low":
            continue
        target = _target_stock_units(risk)
        gap = max(0.0, target - risk.current_stock)
        if gap <= 0:
            continue

        order_units = int(round(gap))
        unit_cost = float(unit_cost_lookup.get(risk.medicine_id, 5.0))
        cost = order_units * unit_cost

        if budget is not None:
            if spent >= budget:
                break
            if spent + cost > budget:
                affordable_units = int((budget - spent) // unit_cost) if unit_cost > 0 else 0
                if affordable_units <= 0:
                    continue
                order_units = affordable_units
                cost = order_units * unit_cost

        spent += cost
        sup = store.supplier_for(risk.medicine_id) or {"supplier_id": "SUP-01"}
        recommendations.append(ProcurementRecommendation(
            medicine_id=risk.medicine_id,
            branch_id=risk.branch_id,
            name=risk.name,
            category=category_lookup.get(risk.medicine_id, risk.category),
            criticality=risk.criticality,
            composite_risk_score=risk.composite_risk_score,
            recommended_order_units=order_units,
            unit_cost=unit_cost,
            estimated_cost=round(cost, 2),
            supplier_id=sup.get("supplier_id", "SUP-01"),
            rationale_facts={
                "stockout_probability_pct": risk.stockout_probability_pct,
                "days_of_cover_p50": risk.days_of_cover_p50,
                "current_stock": risk.current_stock,
                "forecast_daily_mean": risk.forecast_daily_mean,
                "trend_direction": risk.trend_direction,
                "trend_pct_30d": risk.trend_pct_30d,
                "supplier_lead_time_mean": risk.supplier_lead_time_mean,
                "supplier_reliability": risk.supplier_reliability,
                "overdue_orders_units": risk.overdue_orders_units,
                "risk_tier": risk.risk_tier,
            },
        ))
        if len(recommendations) >= top_n:
            break

    return recommendations, round(spent, 2)


def suggest_transfers(
    store,
    min_stockout_risk_pct: float = 40.0,
    max_days_to_expiry_for_surplus: int = 45,
    all_risk: Optional[List] = None,
):
    """
    Look across branches: if one branch has meaningful stockout risk
    AND another branch is holding stock that will expire soon relative to its own
    consumption rate (genuine surplus), suggest transferring stock.
    Accepts precomputed all_risk for instantaneous performance.
    """
    if all_risk is None:
        all_risk = compute_all_risk(store)

    # Group risks by medicine_id
    by_med = {}
    for r in all_risk:
        by_med.setdefault(r.medicine_id, {})[r.branch_id] = r

    snapshot_date = store.inventory["snapshot_date"].max()
    suggestions = []

    for mid, branch_risks in by_med.items():
        if len(branch_risks) < 2:
            continue

        needy = {b: r for b, r in branch_risks.items() if r.stockout_probability_pct >= min_stockout_risk_pct}
        if not needy:
            continue

        for needy_bid, needy_risk in needy.items():
            for surplus_bid, surplus_risk in branch_risks.items():
                if surplus_bid == needy_bid:
                    continue
                inv_row = store.inventory_for(mid, surplus_bid)
                if inv_row.empty:
                    continue
                days_to_expiry = (pd.Timestamp(inv_row.iloc[0]["nearest_batch_expiry"]) - snapshot_date).days
                own_cover_days = surplus_risk.days_of_cover_p50

                is_genuine_surplus = (
                    days_to_expiry <= max_days_to_expiry_for_surplus
                    and own_cover_days > 25  # branch has more than enough for itself
                    and surplus_risk.stockout_probability_pct < 15
                )
                if not is_genuine_surplus:
                    continue

                shortfall = max(0.0, _target_stock_units(needy_risk) - needy_risk.current_stock)
                available_surplus = max(
                    0.0,
                    surplus_risk.current_stock
                    - surplus_risk.emergency_reserve
                    - surplus_risk.forecast_daily_mean * 10,
                )
                transfer_units = int(round(min(shortfall, available_surplus)))
                if transfer_units < 5:
                    continue

                suggestions.append(TransferSuggestion(
                    medicine_id=mid,
                    name=needy_risk.name,
                    category=needy_risk.category,
                    from_branch=surplus_bid,
                    to_branch=needy_bid,
                    suggested_units=transfer_units,
                    from_branch_days_to_expiry=int(days_to_expiry),
                    to_branch_stockout_probability_pct=needy_risk.stockout_probability_pct,
                    rationale=(
                        f"{surplus_bid} holds surplus {needy_risk.name} expiring in {int(days_to_expiry)} days "
                        f"with {own_cover_days:.0f} days of cover, while {needy_bid} faces "
                        f"{needy_risk.stockout_probability_pct:.0f}% stockout probability."
                    ),
                ))

    suggestions.sort(key=lambda s: -s.to_branch_stockout_probability_pct)
    return suggestions
