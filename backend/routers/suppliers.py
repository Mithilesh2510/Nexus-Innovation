"""
Supplier intelligence and scorecard analytics routes.
"""
from fastapi import APIRouter
import pandas as pd
from data_loader import STORE

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("/intelligence")
def supplier_intelligence():
    """Detailed supplier performance scorecards derived from historical procurement data."""
    now = pd.Timestamp.now()
    proc = STORE.procurement.copy()
    suppliers = STORE.suppliers.to_dict(orient="records")
    
    meds_by_sup = {}
    for mid, sid in STORE._supplier_for_medicine.items():
        med_row = STORE.medicine_row(mid)
        if med_row:
            meds_by_sup.setdefault(sid, []).append(med_row["name"])

    scorecards = []
    for sup in suppliers:
        sid = sup["supplier_id"]
        sup_orders = proc[proc.supplier_id == sid]
        total_orders = len(sup_orders)
        
        if total_orders > 0:
            delivered = sup_orders[sup_orders.status == "DELIVERED"]
            delayed = delivered[delivered.actual_delivery_date > delivered.expected_delivery_date]
            delay_count = len(delayed)
            on_time_count = len(delivered) - delay_count
            on_time_pct = round(100.0 * on_time_count / len(delivered), 1) if len(delivered) else 0.0
            
            pending = sup_orders[sup_orders.status == "PENDING"]
            overdue_pending = pending[pending.expected_delivery_date < now]
            stuck_units = int(overdue_pending["ordered_units"].sum()) if not overdue_pending.empty else 0
            
            partial_count = len(sup_orders[sup_orders.status == "PARTIAL"])
        else:
            on_time_pct = round(float(sup["reliability_score"]) * 100, 1)
            delay_count = 0
            stuck_units = 0
            partial_count = 0

        score = float(sup["reliability_score"])
        if score >= 0.95 and on_time_pct >= 85:
            grade = "A+ Elite"
            grade_color = "low"
        elif score >= 0.88:
            grade = "A Reliable"
            grade_color = "low"
        elif score >= 0.78:
            grade = "B Monitored"
            grade_color = "moderate"
        elif score >= 0.70:
            grade = "C Warning"
            grade_color = "high"
        else:
            grade = "Critical Risk"
            grade_color = "critical"

        scorecards.append({
            "supplier_id": sid,
            "name": sup["name"],
            "avg_lead_time_days": float(sup["avg_lead_time_days"]),
            "lead_time_std_days": float(sup["lead_time_std_days"]),
            "reliability_score": float(sup["reliability_score"]),
            "reliability_pct": round(float(sup["reliability_score"]) * 100, 1),
            "grade": grade,
            "grade_color": grade_color,
            "total_orders_tracked": total_orders,
            "on_time_delivery_pct": on_time_pct,
            "delayed_orders_count": delay_count,
            "stuck_pending_units": stuck_units,
            "partial_shipments_count": partial_count,
            "supplied_medicines_count": len(meds_by_sup.get(sid, [])),
            "sample_medicines": meds_by_sup.get(sid, [])[:4],
        })

    scorecards.sort(key=lambda x: -x["reliability_pct"])
    return scorecards
