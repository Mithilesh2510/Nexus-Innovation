"""
Synthetic dataset generator for the Healthcare Supply Chain Intelligence system.

Generates:
  medicines.csv            - SKU master data (criticality, reorder points, shelf life)
  branches.csv              - 3 hospital branches (for inter-facility transfer novelty)
  consumption_history.csv   - 365 days x ~100 SKUs x 3 branches of daily usage
  inventory_snapshot.csv    - current stock / reserved / emergency reserve / nearest expiry, per branch
  suppliers.csv              - lead time mean/std, reliability
  procurement_history.csv   - past orders incl. some PARTIAL / overdue PENDING orders
  supply_events.csv         - injected disruption events (for demo scripting)
  usage_anomalies.csv       - ground-truth labeled anomaly days (to validate the detector against)
  data_dictionary.csv       - column definitions for every file above

Run:  python generate_data.py
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

RNG = np.random.default_rng(42)
N_DAYS = 365
TODAY = datetime(2026, 9, 18)
START_DATE = TODAY - timedelta(days=N_DAYS - 1)
DATES = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]

BRANCHES = [
    {"branch_id": "BR01", "name": "City General Hospital", "type": "Main Campus"},
    {"branch_id": "BR02", "name": "Riverside Community Hospital", "type": "Satellite"},
    {"branch_id": "BR03", "name": "North District Clinic", "type": "Satellite"},
]

CATEGORIES = {
    "Emergency Drugs": {"criticality": "Critical", "n": 12, "base_range": (5, 40), "shelf_life": (180, 730)},
    "Antibiotics": {"criticality": "High", "n": 20, "base_range": (10, 80), "shelf_life": (365, 1095)},
    "Blood Products": {"criticality": "Critical", "n": 6, "base_range": (3, 25), "shelf_life": (21, 42)},
    "Chronic Disease Meds": {"criticality": "High", "n": 18, "base_range": (15, 100), "shelf_life": (365, 730)},
    "Analgesics": {"criticality": "Medium", "n": 14, "base_range": (20, 120), "shelf_life": (365, 1095)},
    "PPE / Consumables": {"criticality": "Medium", "n": 16, "base_range": (50, 400), "shelf_life": (730, 1825)},
    "Vaccines": {"criticality": "Critical", "n": 8, "base_range": (5, 30), "shelf_life": (90, 365)},
    "General OTC": {"criticality": "Low", "n": 10, "base_range": (10, 60), "shelf_life": (365, 1095)},
}

DRUG_NAME_STEMS = [
    "Amoxicillin", "Paracetamol", "Ibuprofen", "Ceftriaxone", "Metformin",
    "Insulin", "Epinephrine", "Atorvastatin", "Losartan", "Omeprazole",
    "Azithromycin", "Salbutamol", "Diazepam", "Morphine", "Furosemide",
    "Warfarin", "Heparin", "Vancomycin", "Cefixime", "Doxycycline",
    "Prednisolone", "Hydrocortisone", "Tramadol", "Diclofenac", "Amlodipine",
    "Ranitidine", "Ondansetron", "Metronidazole", "Ciprofloxacin", "Clopidogrel",
    "Enoxaparin", "Albumin", "Packed RBC", "Fresh Frozen Plasma", "Platelets",
    "Whole Blood", "MMR Vaccine", "Hepatitis B Vaccine", "Tetanus Vaccine",
    "COVID-19 Vaccine", "Influenza Vaccine", "BCG Vaccine", "Rabies Vaccine",
    "Surgical Gloves", "N95 Masks", "Surgical Gowns", "IV Cannula", "Syringes 5ml",
    "Gauze Rolls", "Alcohol Swabs", "Face Shields", "Sanitizer 500ml", "Suture Kits",
    "Catheters", "IV Fluid NS 500ml", "IV Fluid RL 500ml", "Oxygen Masks", "ECG Electrodes",
]


def build_medicines():
    rows = []
    idx = 1
    stem_i = 0
    for cat, cfg in CATEGORIES.items():
        for _ in range(cfg["n"]):
            mid = f"MED{idx:03d}"
            name = DRUG_NAME_STEMS[stem_i % len(DRUG_NAME_STEMS)]
            stem_i += 1
            base_usage = RNG.uniform(*cfg["base_range"])
            shelf_life = int(RNG.integers(cfg["shelf_life"][0], cfg["shelf_life"][1] + 1))
            unit_cost = round(float(RNG.uniform(0.5, 150)), 2)
            reorder_point = round(base_usage * RNG.uniform(7, 14), 0)      # ~1-2 weeks cover
            target_max = round(base_usage * RNG.uniform(25, 45), 0)         # ~1-1.5 months cover
            rows.append({
                "medicine_id": mid,
                "name": f"{name} {RNG.choice(['500mg','250mg','1g','10ml','Unit','Box'])}",
                "category": cat,
                "criticality": cfg["criticality"],
                "base_daily_usage": round(base_usage, 2),
                "reorder_point": reorder_point,
                "target_max_stock": target_max,
                "shelf_life_days": shelf_life,
                "unit_cost": unit_cost,
            })
            idx += 1
    return pd.DataFrame(rows)


def build_suppliers(n=15):
    rows = []
    for i in range(1, n + 1):
        mean_lead = RNG.uniform(3, 21)
        rows.append({
            "supplier_id": f"SUP{i:03d}",
            "name": f"Supplier {i:02d} Ltd.",
            "avg_lead_time_days": round(mean_lead, 1),
            "lead_time_std_days": round(mean_lead * RNG.uniform(0.15, 0.45), 1),
            "reliability_score": round(float(np.clip(RNG.normal(0.9, 0.08), 0.55, 0.99)), 2),
        })
    return pd.DataFrame(rows)


def assign_supplier(medicines_df, suppliers_df):
    return {mid: RNG.choice(suppliers_df["supplier_id"].values) for mid in medicines_df["medicine_id"]}


def build_consumption_and_anomalies(medicines_df):
    """
    Build daily consumption per medicine per branch with:
      - weekly seasonality (lower weekend usage)
      - slow trend drift
      - random noise
      - injected anomaly spikes (labeled) for a subset of med/day combos
      - a scripted "outbreak" surge for a handful of medicines in the last 3 weeks (demo scenario)
    """
    consumption_rows = []
    anomaly_rows = []
    branch_share = {"BR01": 0.55, "BR02": 0.30, "BR03": 0.15}  # main campus does more volume

    # pick medicines for the scripted "outbreak" demo (last 21 days ramp-up)
    outbreak_meds = RNG.choice(medicines_df["medicine_id"].values, size=3, replace=False)

    for _, med in medicines_df.iterrows():
        mid = med["medicine_id"]
        base = med["base_daily_usage"]
        # slow multiplicative trend across the year
        trend = np.linspace(RNG.uniform(0.9, 1.0), RNG.uniform(1.0, 1.15), N_DAYS)
        is_outbreak_med = mid in outbreak_meds

        for branch_id, share in branch_share.items():
            branch_base = base * share
            for day_i, date in enumerate(DATES):
                weekday = date.weekday()
                weekend_factor = 0.75 if weekday >= 5 else 1.0
                noise = RNG.normal(1.0, 0.12)
                value = branch_base * trend[day_i] * weekend_factor * noise

                # scripted outbreak ramp in the final 21 days, main campus only, for chosen meds
                if is_outbreak_med and branch_id == "BR01" and day_i >= N_DAYS - 21:
                    days_into = day_i - (N_DAYS - 21)
                    multiplier = 1.0 + (days_into / 20) * 2.2  # ramps up to ~3.2x
                    value *= multiplier
                    if multiplier > 1.5:
                        anomaly_rows.append({
                            "medicine_id": mid, "branch_id": branch_id, "date": date.strftime("%Y-%m-%d"),
                            "multiplier_vs_baseline": round(float(multiplier), 2), "label": "abnormal_usage",
                        })

                # random sporadic spikes (~0.6% of med-day-branch combos), independent of outbreak script
                elif RNG.random() < 0.006:
                    spike_mult = RNG.uniform(2.0, 4.5)
                    value *= spike_mult
                    anomaly_rows.append({
                        "medicine_id": mid, "branch_id": branch_id, "date": date.strftime("%Y-%m-%d"),
                        "multiplier_vs_baseline": round(float(spike_mult), 2), "label": "abnormal_usage",
                    })

                value = max(0, value)
                consumption_rows.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "medicine_id": mid,
                    "branch_id": branch_id,
                    "units_consumed": round(float(value), 1),
                })

    return pd.DataFrame(consumption_rows), pd.DataFrame(anomaly_rows), outbreak_meds


def build_inventory_snapshot(medicines_df, consumption_df):
    rows = []
    branches = ["BR01", "BR02", "BR03"]
    branch_stock_share = {"BR01": 0.5, "BR02": 0.32, "BR03": 0.18}

    for _, med in medicines_df.iterrows():
        mid = med["medicine_id"]
        recent_daily = consumption_df[(consumption_df.medicine_id == mid)].groupby("date")["units_consumed"].sum().tail(14).mean()

        for branch_id in branches:
            share = branch_stock_share[branch_id]
            # Randomize stock health: some low, some healthy, some overstocked-near-expiry
            profile = RNG.choice(["low", "healthy", "overstock"], p=[0.25, 0.55, 0.20])
            branch_daily = recent_daily * share if pd.notna(recent_daily) else med["base_daily_usage"] * share

            if profile == "low":
                days_cover = RNG.uniform(1.5, 5)
            elif profile == "healthy":
                days_cover = RNG.uniform(10, 25)
            else:
                days_cover = RNG.uniform(40, 90)

            current_stock = round(max(0, branch_daily * days_cover), 0)
            emergency_reserve = round(med["reorder_point"] * share * 0.3, 0) if med["criticality"] in ("Critical", "High") else round(med["reorder_point"] * share * 0.1, 0)
            reserved_units = round(current_stock * RNG.uniform(0, 0.1), 0)

            shelf = int(med["shelf_life_days"])
            if profile == "overstock":
                nearest_expiry_days = int(RNG.integers(5, min(45, shelf)))
            else:
                lo = min(30, max(1, shelf - 1))
                hi = max(lo + 1, shelf)
                nearest_expiry_days = int(RNG.integers(lo, hi))
            nearest_expiry = (TODAY + timedelta(days=nearest_expiry_days)).strftime("%Y-%m-%d")

            rows.append({
                "medicine_id": mid,
                "branch_id": branch_id,
                "current_stock": current_stock,
                "reserved_units": reserved_units,
                "emergency_reserve": emergency_reserve,
                "nearest_batch_expiry": nearest_expiry,
                "snapshot_date": TODAY.strftime("%Y-%m-%d"),
            })
    return pd.DataFrame(rows)


def build_procurement_history(medicines_df, supplier_map, suppliers_df, n_orders=500):
    rows = []
    supplier_lookup = suppliers_df.set_index("supplier_id").to_dict("index")

    for i in range(1, n_orders + 1):
        mid = RNG.choice(medicines_df["medicine_id"].values)
        sup_id = supplier_map[mid]
        sup = supplier_lookup[sup_id]

        order_date = START_DATE + timedelta(days=int(RNG.integers(0, N_DAYS - 5)))
        mean_lead = sup["avg_lead_time_days"]
        std_lead = sup["lead_time_std_days"]
        actual_lead = max(1, RNG.normal(mean_lead, std_lead))
        expected_delivery = order_date + timedelta(days=int(round(mean_lead)))

        ordered_units = int(RNG.integers(50, 1500))
        reliability = sup["reliability_score"]
        roll = RNG.random()

        days_since_order = (TODAY - order_date).days

        if days_since_order < actual_lead - 2:
            status = "PENDING"
            received_units = 0
            actual_delivery_date = ""
        elif roll < reliability:
            status = "DELIVERED"
            received_units = ordered_units
            actual_delivery_date = (order_date + timedelta(days=int(round(actual_lead)))).strftime("%Y-%m-%d")
        elif roll < reliability + 0.06:
            status = "PARTIAL"
            received_units = int(ordered_units * RNG.uniform(0.4, 0.85))
            actual_delivery_date = (order_date + timedelta(days=int(round(actual_lead * 1.3)))).strftime("%Y-%m-%d")
        else:
            # overdue / stuck PENDING order (the real-data nuance: stale POs)
            status = "PENDING"
            received_units = 0
            actual_delivery_date = ""
            expected_delivery = order_date + timedelta(days=int(round(mean_lead * 0.7)))  # already overdue

        rows.append({
            "order_id": f"PO{i:04d}",
            "medicine_id": mid,
            "supplier_id": sup_id,
            "order_date": order_date.strftime("%Y-%m-%d"),
            "expected_delivery_date": expected_delivery.strftime("%Y-%m-%d"),
            "actual_delivery_date": actual_delivery_date,
            "ordered_units": ordered_units,
            "received_units": received_units,
            "status": status,
        })
    return pd.DataFrame(rows)


def build_supply_events(medicines_df, outbreak_meds):
    rows = []
    eid = 1
    for mid in outbreak_meds:
        rows.append({
            "event_id": f"EVT{eid:03d}", "date": (TODAY - timedelta(days=18)).strftime("%Y-%m-%d"),
            "medicine_id": mid, "event_type": "abnormal_usage",
            "description": "Sustained demand surge consistent with a local outbreak pattern",
            "magnitude": round(float(RNG.uniform(2.0, 3.2)), 2),
        })
        eid += 1
    # a couple of scripted supplier delay events
    for mid in RNG.choice(medicines_df["medicine_id"].values, size=4, replace=False):
        rows.append({
            "event_id": f"EVT{eid:03d}", "date": (TODAY - timedelta(days=int(RNG.integers(2, 15)))).strftime("%Y-%m-%d"),
            "medicine_id": mid, "event_type": "supplier_delay",
            "description": "Supplier reported logistics delay beyond contracted lead time",
            "magnitude": round(float(RNG.uniform(1.3, 2.5)), 2),
        })
        eid += 1
    return pd.DataFrame(rows)


def build_data_dictionary():
    entries = [
        ("medicines.csv", "medicine_id", "Unique SKU identifier"),
        ("medicines.csv", "name", "Medicine / consumable display name"),
        ("medicines.csv", "category", "SKU category (Antibiotics, Blood Products, PPE, etc.)"),
        ("medicines.csv", "criticality", "Critical / High / Medium / Low — drives service-level target & emergency reserve sizing"),
        ("medicines.csv", "base_daily_usage", "Average daily consumption across all branches (units)"),
        ("medicines.csv", "reorder_point", "Legacy static reorder threshold (kept for comparison to the new system)"),
        ("medicines.csv", "target_max_stock", "Legacy static max-stock threshold"),
        ("medicines.csv", "shelf_life_days", "Shelf life from manufacture, in days"),
        ("medicines.csv", "unit_cost", "Cost per unit, used for budget-constrained procurement optimization"),
        ("branches.csv", "branch_id", "Unique hospital branch identifier"),
        ("branches.csv", "name", "Branch display name"),
        ("branches.csv", "type", "Main Campus / Satellite"),
        ("consumption_history.csv", "date", "Calendar date of consumption (daily grain)"),
        ("consumption_history.csv", "medicine_id", "FK to medicines.csv"),
        ("consumption_history.csv", "branch_id", "FK to branches.csv"),
        ("consumption_history.csv", "units_consumed", "Units consumed that day at that branch"),
        ("inventory_snapshot.csv", "medicine_id", "FK to medicines.csv"),
        ("inventory_snapshot.csv", "branch_id", "FK to branches.csv"),
        ("inventory_snapshot.csv", "current_stock", "On-hand stock as of snapshot_date"),
        ("inventory_snapshot.csv", "reserved_units", "Stock already earmarked for scheduled procedures/patients"),
        ("inventory_snapshot.csv", "emergency_reserve", "Hard floor that must not be dipped into except in emergencies"),
        ("inventory_snapshot.csv", "nearest_batch_expiry", "Expiry date of the soonest-expiring batch on hand"),
        ("inventory_snapshot.csv", "snapshot_date", "Date this snapshot was taken"),
        ("suppliers.csv", "supplier_id", "Unique supplier identifier"),
        ("suppliers.csv", "avg_lead_time_days", "Mean historical lead time"),
        ("suppliers.csv", "lead_time_std_days", "Std deviation of historical lead time — feeds Monte Carlo simulation"),
        ("suppliers.csv", "reliability_score", "Fraction of orders delivered on-spec and on-time"),
        ("procurement_history.csv", "order_id", "Unique purchase order identifier"),
        ("procurement_history.csv", "medicine_id", "FK to medicines.csv"),
        ("procurement_history.csv", "supplier_id", "FK to suppliers.csv"),
        ("procurement_history.csv", "order_date", "Date the PO was placed"),
        ("procurement_history.csv", "expected_delivery_date", "Contracted/expected delivery date"),
        ("procurement_history.csv", "actual_delivery_date", "Actual delivery date (blank if still PENDING)"),
        ("procurement_history.csv", "ordered_units", "Units ordered"),
        ("procurement_history.csv", "received_units", "Units actually received (< ordered for PARTIAL, 0 for PENDING)"),
        ("procurement_history.csv", "status", "DELIVERED / PARTIAL / PENDING"),
        ("supply_events.csv", "event_id", "Unique disruption event id"),
        ("supply_events.csv", "event_type", "abnormal_usage / supplier_delay"),
        ("supply_events.csv", "magnitude", "Severity multiplier of the event"),
        ("usage_anomalies.csv", "medicine_id", "FK to medicines.csv"),
        ("usage_anomalies.csv", "branch_id", "FK to branches.csv"),
        ("usage_anomalies.csv", "date", "Date of the labeled anomalous consumption"),
        ("usage_anomalies.csv", "multiplier_vs_baseline", "How many times baseline usage this day represented"),
        ("usage_anomalies.csv", "label", "Ground-truth label used to validate the EWMA/CUSUM detector"),
    ]
    return pd.DataFrame(entries, columns=["file", "column", "description"])


def main():
    out_dir = __file__.rsplit("/", 1)[0]
    medicines_df = build_medicines()
    branches_df = pd.DataFrame(BRANCHES)
    suppliers_df = build_suppliers()
    supplier_map = assign_supplier(medicines_df, suppliers_df)

    consumption_df, anomalies_df, outbreak_meds = build_consumption_and_anomalies(medicines_df)
    inventory_df = build_inventory_snapshot(medicines_df, consumption_df)
    procurement_df = build_procurement_history(medicines_df, supplier_map, suppliers_df)
    events_df = build_supply_events(medicines_df, outbreak_meds)
    dict_df = build_data_dictionary()

    medicines_df.to_csv(f"{out_dir}/medicines.csv", index=False)
    branches_df.to_csv(f"{out_dir}/branches.csv", index=False)
    suppliers_df.to_csv(f"{out_dir}/suppliers.csv", index=False)
    consumption_df.to_csv(f"{out_dir}/consumption_history.csv", index=False)
    inventory_df.to_csv(f"{out_dir}/inventory_snapshot.csv", index=False)
    procurement_df.to_csv(f"{out_dir}/procurement_history.csv", index=False)
    events_df.to_csv(f"{out_dir}/supply_events.csv", index=False)
    anomalies_df.to_csv(f"{out_dir}/usage_anomalies.csv", index=False)
    dict_df.to_csv(f"{out_dir}/data_dictionary.csv", index=False)

    print(f"medicines: {len(medicines_df)}")
    print(f"branches: {len(branches_df)}")
    print(f"suppliers: {len(suppliers_df)}")
    print(f"consumption_history rows: {len(consumption_df)}")
    print(f"inventory_snapshot rows: {len(inventory_df)}")
    print(f"procurement_history rows: {len(procurement_df)}")
    print(f"supply_events rows: {len(events_df)}")
    print(f"usage_anomalies rows: {len(anomalies_df)}")
    print(f"outbreak demo medicines: {list(outbreak_meds)}")


if __name__ == "__main__":
    main()
