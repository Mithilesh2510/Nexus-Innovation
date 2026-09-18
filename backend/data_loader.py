"""
Loads supply chain data from MySQL database (with graceful fallback to CSV)
and exposes fast O(1) indexed accessors.
Pre-indexes consumption, inventory, and procurement records to eliminate
repeated DataFrame scans across 100k+ rows.
"""
import os
import uuid
import logging
import pandas as pd

from db import (
    USE_MYSQL,
    check_mysql_connection,
    load_table_as_dataframe,
    update_inventory_stock,
    persist_dispatched_transfer,
    persist_procurement_order,
)

logger = logging.getLogger("supply_chain.data_loader")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class DataStore:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.backend_source = "CSV"
        self.dispatched_transfers = []
        self.dispatched_orders = []

        mysql_ok, msg = check_mysql_connection()
        if USE_MYSQL and mysql_ok:
            try:
                print(f"[DataStore] Connecting to MySQL database... ({msg})")
                self._load_from_mysql()
                self.backend_source = "MySQL"
                print(f"[DataStore] Successfully loaded all tables from MySQL.")
            except Exception as e:
                print(f"[DataStore WARNING] MySQL load failed: {e}. Falling back to CSV.")
                self._load_from_csv()
                self.backend_source = "CSV"
        else:
            print(f"[DataStore] MySQL not active ({msg}). Loading from CSV in {data_dir}.")
            self._load_from_csv()
            self.backend_source = "CSV"

        self._build_indexes()

    def _load_from_mysql(self):
        """Loads all datasets directly from MySQL database tables."""
        self.medicines = load_table_as_dataframe("medicines")
        self.branches = load_table_as_dataframe("branches")
        self.suppliers = load_table_as_dataframe("suppliers")
        self.consumption = load_table_as_dataframe("consumption_history", parse_dates=["date"])
        self.inventory = load_table_as_dataframe(
            "inventory_snapshot",
            parse_dates=["nearest_batch_expiry", "snapshot_date"]
        )
        self.procurement = load_table_as_dataframe(
            "procurement_history",
            parse_dates=["order_date", "expected_delivery_date", "actual_delivery_date"]
        )
        self.events = load_table_as_dataframe("supply_events", parse_dates=["date"])
        self.anomalies_truth = load_table_as_dataframe("usage_anomalies", parse_dates=["date"])

        # Load previously persisted lateral transfers if any
        try:
            prev_transfers = load_table_as_dataframe("dispatched_transfers", parse_dates=["timestamp"])
            if not prev_transfers.empty:
                prev_transfers["timestamp"] = prev_transfers["timestamp"].astype(str)
                self.dispatched_transfers = prev_transfers.to_dict(orient="records")
        except Exception:
            self.dispatched_transfers = []

        # Load pending/dispatched orders placed in current cycle
        if "status" in self.procurement.columns:
            pending = self.procurement[self.procurement["status"] == "PENDING"]
            if not pending.empty:
                self.dispatched_orders = pending.copy().fillna("").to_dict(orient="records")

    def _load_from_csv(self):
        """Fallback loader: loads data directly from local CSV files."""
        data_dir = self.data_dir
        self.medicines = pd.read_csv(f"{data_dir}/medicines.csv")
        self.branches = pd.read_csv(f"{data_dir}/branches.csv")
        self.suppliers = pd.read_csv(f"{data_dir}/suppliers.csv")
        self.consumption = pd.read_csv(f"{data_dir}/consumption_history.csv", parse_dates=["date"])
        self.inventory = pd.read_csv(
            f"{data_dir}/inventory_snapshot.csv",
            parse_dates=["nearest_batch_expiry", "snapshot_date"]
        )
        self.procurement = pd.read_csv(
            f"{data_dir}/procurement_history.csv",
            parse_dates=["order_date", "expected_delivery_date", "actual_delivery_date"],
        )
        self.events = pd.read_csv(f"{data_dir}/supply_events.csv", parse_dates=["date"])
        self.anomalies_truth = pd.read_csv(f"{data_dir}/usage_anomalies.csv", parse_dates=["date"])

    def _build_indexes(self):
        """Pre-indexes data structures for instantaneous O(1) lookups."""
        # Ensure correct numeric types
        self.medicines["unit_cost"] = pd.to_numeric(self.medicines["unit_cost"], errors="coerce").fillna(0.0)
        self.inventory["current_stock"] = pd.to_numeric(self.inventory["current_stock"], errors="coerce").fillna(0.0)
        self.consumption["units_consumed"] = pd.to_numeric(self.consumption["units_consumed"], errors="coerce").fillna(0.0)

        # medicine -> assigned supplier (most frequent supplier in procurement history)
        sup_mode = (
            self.procurement.groupby("medicine_id")["supplier_id"]
            .agg(lambda s: s.value_counts().idxmax() if not s.empty else "SUP001")
            .to_dict()
        )
        self._supplier_for_medicine = sup_mode

        # Fast O(1) lookup tables
        self._supplier_rows = {row["supplier_id"]: row for row in self.suppliers.to_dict(orient="records")}
        self._medicine_rows = {row["medicine_id"]: row for row in self.medicines.to_dict(orient="records")}

        # Pre-group orders by medicine_id
        self._orders_by_med = {
            mid: group.copy() for mid, group in self.procurement.groupby("medicine_id")
        }

        # Pre-index daily consumption by (medicine_id, branch_id) and (medicine_id, None)
        self._consumption_cache = {}
        for (mid, bid), group in self.consumption.groupby(["medicine_id", "branch_id"]):
            s = group.set_index("date")["units_consumed"].sort_index()
            self._consumption_cache[(mid, bid)] = s

        # Pre-index aggregate consumption across all branches
        for mid, group in self.consumption.groupby("medicine_id"):
            agg = group.groupby("date")["units_consumed"].sum().sort_index()
            self._consumption_cache[(mid, None)] = agg

    def supplier_for(self, medicine_id: str):
        sup_id = self._supplier_for_medicine.get(medicine_id)
        if sup_id is None:
            return None
        return self._supplier_rows.get(sup_id)

    def medicine_row(self, medicine_id: str):
        return self._medicine_rows.get(medicine_id)

    def daily_consumption(self, medicine_id: str, branch_id: str | None = None) -> pd.Series:
        key = (medicine_id, branch_id)
        if key in self._consumption_cache:
            return self._consumption_cache[key]
        return pd.Series(dtype=float)

    def inventory_for(self, medicine_id: str, branch_id: str | None = None):
        df = self.inventory[self.inventory.medicine_id == medicine_id]
        if branch_id:
            df = df[df.branch_id == branch_id]
        return df

    def orders_for(self, medicine_id: str):
        if medicine_id in self._orders_by_med:
            return self._orders_by_med[medicine_id].copy()
        return self.procurement[self.procurement.medicine_id == medicine_id].copy()

    def dispatch_transfer(self, medicine_id: str, from_branch: str, to_branch: str, units: int):
        """Rebalance stock between branches with persistence to MySQL."""
        mask_from = (self.inventory.medicine_id == medicine_id) & (self.inventory.branch_id == from_branch)
        mask_to = (self.inventory.medicine_id == medicine_id) & (self.inventory.branch_id == to_branch)

        if not self.inventory[mask_from].empty and not self.inventory[mask_to].empty:
            curr_from = float(self.inventory.loc[mask_from, "current_stock"].iloc[0])
            actual_units = min(units, int(curr_from))
            new_from_stock = max(0.0, curr_from - actual_units)
            curr_to = float(self.inventory.loc[mask_to, "current_stock"].iloc[0])
            new_to_stock = curr_to + actual_units

            self.inventory.loc[mask_from, "current_stock"] = new_from_stock
            self.inventory.loc[mask_to, "current_stock"] = new_to_stock

            now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "transfer_id": f"TRF-{uuid.uuid4().hex[:6].upper()}",
                "timestamp": now_str,
                "medicine_id": medicine_id,
                "medicine_name": self._medicine_rows.get(medicine_id, {}).get("name", medicine_id),
                "from_branch": from_branch,
                "to_branch": to_branch,
                "units": actual_units,
                "status": "IN_TRANSIT",
            }
            self.dispatched_transfers.append(record)

            # Persist to MySQL if active
            if self.backend_source == "MySQL":
                update_inventory_stock(medicine_id, from_branch, new_from_stock)
                update_inventory_stock(medicine_id, to_branch, new_to_stock)
                persist_dispatched_transfer(record)

            return record
        return None

    def create_order(self, medicine_id: str, branch_id: str, units: int, unit_cost: float):
        """Create a new pending purchase order with persistence to MySQL."""
        sup = self.supplier_for(medicine_id) or {"supplier_id": "SUP001", "avg_lead_time_days": 7}
        lead_days = int(sup.get("avg_lead_time_days", 7))
        now = pd.Timestamp.now()
        expected = now + pd.Timedelta(days=lead_days)

        po_id = f"PO-{uuid.uuid4().hex[:6].upper()}"
        record = {
            "order_id": po_id,
            "order_date": now.strftime("%Y-%m-%d"),
            "medicine_id": medicine_id,
            "medicine_name": self._medicine_rows.get(medicine_id, {}).get("name", medicine_id),
            "branch_id": branch_id,
            "supplier_id": sup.get("supplier_id"),
            "ordered_units": units,
            "received_units": 0,
            "expected_delivery_date": expected.strftime("%Y-%m-%d"),
            "status": "PENDING",
            "unit_cost": unit_cost,
            "total_cost": round(units * unit_cost, 2),
        }
        self.dispatched_orders.append(record)

        # Append to procurement dataframe and update cache
        new_row = pd.DataFrame([record])
        new_row["order_date"] = pd.to_datetime(new_row["order_date"])
        new_row["expected_delivery_date"] = pd.to_datetime(new_row["expected_delivery_date"])
        new_row["actual_delivery_date"] = pd.NaT

        self.procurement = pd.concat([self.procurement, new_row], ignore_index=True)
        if medicine_id in self._orders_by_med:
            self._orders_by_med[medicine_id] = pd.concat([self._orders_by_med[medicine_id], new_row], ignore_index=True)
        else:
            self._orders_by_med[medicine_id] = new_row

        # Persist to MySQL if active
        if self.backend_source == "MySQL":
            persist_procurement_order(record)

        return record


# Singleton used across the FastAPI app
STORE = DataStore()
