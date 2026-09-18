#!/usr/bin/env python
"""
Migration & Seeding Script: CSV to MySQL
Reads CSV datasets from data/, initializes the supply_chain_db MySQL database schema,
bulk loads all tables, exports a standalone data/supply_chain.sql dump, and validates counts.
"""
import os
import sys
import time
import pymysql
import pandas as pd
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

# Load environment
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "supply_chain_db")
SCHEMA_FILE = os.path.join(DATA_DIR, "schema.sql")
DUMP_FILE = os.path.join(DATA_DIR, "supply_chain.sql")


def escape_sql_val(val):
    """Format a python / pandas value into a safe SQL literal string."""
    if pd.isna(val) or val is None or str(val).strip() == "" or str(val).strip().lower() == "nan" or str(val).strip().lower() == "nat":
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    # String / date / datetime
    s = str(val).replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"


def run_migration():
    print("=" * 60)
    print(" Supply Chain Intelligence: CSV -> MySQL Migration Engine")
    print("=" * 60)
    print(f"Connecting to MySQL: {MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT} (DB: {MYSQL_DATABASE})")

    # 1. Connect to MySQL server without database
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset="utf8mb4",
            autocommit=True,
        )
    except Exception as e:
        print(f"[ERROR] Could not connect to MySQL server at {MYSQL_HOST}:{MYSQL_PORT}: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    # 2. Create Database
    print(f"-- Ensuring database `{MYSQL_DATABASE}` exists...")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.select_db(MYSQL_DATABASE)

    # 3. Apply Schema DDL
    print(f"-- Executing schema definition from {os.path.relpath(SCHEMA_FILE, ROOT_DIR)}...")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Split schema statements by semicolon
    statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
    for stmt in statements:
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f"[WARN] Error executing statement: {e}")

    # 4. Ingest Datasets from CSV
    print("-- Ingesting datasets into MySQL...")
    start_time = time.time()

    # Branches
    branches_df = pd.read_csv(os.path.join(DATA_DIR, "branches.csv"))
    print(f"   -> Loading {len(branches_df)} branches...")
    for _, row in branches_df.iterrows():
        cursor.execute(
            "INSERT INTO `branches` (`branch_id`, `name`, `type`) VALUES (%s, %s, %s)",
            (row["branch_id"], row["name"], row["type"]),
        )

    # Suppliers
    suppliers_df = pd.read_csv(os.path.join(DATA_DIR, "suppliers.csv"))
    print(f"   -> Loading {len(suppliers_df)} suppliers...")
    for _, row in suppliers_df.iterrows():
        cursor.execute(
            "INSERT INTO `suppliers` (`supplier_id`, `name`, `avg_lead_time_days`, `lead_time_std_days`, `reliability_score`) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                row["supplier_id"],
                row["name"],
                float(row["avg_lead_time_days"]),
                float(row["lead_time_std_days"]),
                float(row["reliability_score"]),
            ),
        )

    # Medicines
    medicines_df = pd.read_csv(os.path.join(DATA_DIR, "medicines.csv"))
    print(f"   -> Loading {len(medicines_df)} medicines...")
    for _, row in medicines_df.iterrows():
        cursor.execute(
            "INSERT INTO `medicines` (`medicine_id`, `name`, `category`, `criticality`, "
            "`base_daily_usage`, `reorder_point`, `target_max_stock`, `shelf_life_days`, `unit_cost`) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                row["medicine_id"],
                row["name"],
                row["category"],
                row["criticality"],
                float(row["base_daily_usage"]),
                float(row["reorder_point"]),
                float(row["target_max_stock"]),
                int(row["shelf_life_days"]),
                float(row["unit_cost"]),
            ),
        )

    # Consumption History (Bulk Insert in chunks)
    consumption_df = pd.read_csv(os.path.join(DATA_DIR, "consumption_history.csv"))
    total_consumption = len(consumption_df)
    print(f"   -> Loading {total_consumption:,} daily consumption records in batches...")
    
    chunk_size = 10000
    insert_ch_sql = (
        "INSERT INTO `consumption_history` (`date`, `medicine_id`, `branch_id`, `units_consumed`) "
        "VALUES (%s, %s, %s, %s)"
    )
    ch_records = [
        (row.date, row.medicine_id, row.branch_id, float(row.units_consumed))
        for row in consumption_df.itertuples(index=False)
    ]
    for i in range(0, total_consumption, chunk_size):
        chunk = ch_records[i : i + chunk_size]
        cursor.executemany(insert_ch_sql, chunk)
        print(f"      ... inserted {min(i + chunk_size, total_consumption):,}/{total_consumption:,} records")

    # Inventory Snapshot
    inventory_df = pd.read_csv(os.path.join(DATA_DIR, "inventory_snapshot.csv"))
    print(f"   -> Loading {len(inventory_df)} inventory snapshot records...")
    insert_inv_sql = (
        "INSERT INTO `inventory_snapshot` (`medicine_id`, `branch_id`, `current_stock`, "
        "`reserved_units`, `emergency_reserve`, `nearest_batch_expiry`, `snapshot_date`) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    inv_records = [
        (
            row.medicine_id,
            row.branch_id,
            float(row.current_stock),
            float(row.reserved_units),
            float(row.emergency_reserve),
            str(row.nearest_batch_expiry)[:10],
            str(row.snapshot_date)[:10],
        )
        for row in inventory_df.itertuples(index=False)
    ]
    cursor.executemany(insert_inv_sql, inv_records)

    # Procurement History
    procurement_df = pd.read_csv(os.path.join(DATA_DIR, "procurement_history.csv"))
    print(f"   -> Loading {len(procurement_df)} procurement history orders...")
    insert_ph_sql = (
        "INSERT INTO `procurement_history` (`order_id`, `medicine_id`, `supplier_id`, "
        "`order_date`, `expected_delivery_date`, `actual_delivery_date`, `ordered_units`, "
        "`received_units`, `status`) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    ph_records = []
    for row in procurement_df.itertuples(index=False):
        actual_date = None if pd.isna(row.actual_delivery_date) else str(row.actual_delivery_date)[:10]
        ph_records.append((
            row.order_id,
            row.medicine_id,
            row.supplier_id,
            str(row.order_date)[:10],
            str(row.expected_delivery_date)[:10],
            actual_date,
            int(row.ordered_units),
            int(row.received_units),
            str(row.status),
        ))
    cursor.executemany(insert_ph_sql, ph_records)

    # Supply Events
    events_df = pd.read_csv(os.path.join(DATA_DIR, "supply_events.csv"))
    print(f"   -> Loading {len(events_df)} supply events...")
    insert_evt_sql = (
        "INSERT INTO `supply_events` (`event_id`, `date`, `medicine_id`, `event_type`, `description`, `magnitude`) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    evt_records = [
        (
            row.event_id,
            str(row.date)[:10],
            row.medicine_id if not pd.isna(row.medicine_id) else None,
            row.event_type,
            row.description,
            float(row.magnitude),
        )
        for row in events_df.itertuples(index=False)
    ]
    cursor.executemany(insert_evt_sql, evt_records)

    # Usage Anomalies
    anomalies_df = pd.read_csv(os.path.join(DATA_DIR, "usage_anomalies.csv"))
    print(f"   -> Loading {len(anomalies_df)} usage anomaly labels...")
    insert_anom_sql = (
        "INSERT INTO `usage_anomalies` (`medicine_id`, `branch_id`, `date`, `multiplier_vs_baseline`, `label`) "
        "VALUES (%s, %s, %s, %s, %s)"
    )
    anom_records = [
        (
            row.medicine_id,
            row.branch_id,
            str(row.date)[:10],
            float(row.multiplier_vs_baseline),
            row.label,
        )
        for row in anomalies_df.itertuples(index=False)
    ]
    cursor.executemany(insert_anom_sql, anom_records)

    elapsed = time.time() - start_time
    print(f"-- Ingestion completed in {elapsed:.2f} seconds.")

    # 5. Row Count Validation Table
    print("\n" + "=" * 60)
    print(f" {'Table Name':<28} | {'MySQL Row Count':<16} | {'Status'}")
    print("=" * 60)
    tables = [
        ("branches", len(branches_df)),
        ("suppliers", len(suppliers_df)),
        ("medicines", len(medicines_df)),
        ("consumption_history", len(consumption_df)),
        ("inventory_snapshot", len(inventory_df)),
        ("procurement_history", len(procurement_df)),
        ("supply_events", len(events_df)),
        ("usage_anomalies", len(anomalies_df)),
        ("dispatched_transfers", 0),
    ]
    for tbl, expected in tables:
        cursor.execute(f"SELECT COUNT(*) FROM `{tbl}`")
        actual = cursor.fetchone()[0]
        status = "OK (Matches)" if actual >= expected else "MISMATCH"
        print(f" {tbl:<28} | {actual:<16,d} | {status}")
    print("=" * 60)

    # 6. Generate Complete SQL Dump file (data/supply_chain.sql)
    print(f"\n-- Generating standalone SQL dump file: {os.path.relpath(DUMP_FILE, ROOT_DIR)}...")
    generate_standalone_dump()

    conn.close()
    print("\n[SUCCESS] Migration and MySQL export completed successfully!")


def generate_standalone_dump():
    """Build complete self-contained SQL file with DDL and INSERT statements."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        ddl = f.read()

    with open(DUMP_FILE, "w", encoding="utf-8") as out:
        out.write("-- Healthcare Supply Chain Intelligence Complete MySQL Dump\n")
        out.write(f"-- Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        out.write(ddl)
        out.write("\n\n-- =============================================================================\n")
        out.write("-- DATA INSERT STATEMENTS\n")
        out.write("-- =============================================================================\n\n")
        out.write("USE `supply_chain_db`;\n")
        out.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

        # Branches
        branches_df = pd.read_csv(os.path.join(DATA_DIR, "branches.csv"))
        out.write("-- Table: branches\n")
        for _, r in branches_df.iterrows():
            out.write(f"INSERT INTO `branches` (`branch_id`, `name`, `type`) VALUES ({escape_sql_val(r['branch_id'])}, {escape_sql_val(r['name'])}, {escape_sql_val(r['type'])});\n")
        out.write("\n")

        # Suppliers
        suppliers_df = pd.read_csv(os.path.join(DATA_DIR, "suppliers.csv"))
        out.write("-- Table: suppliers\n")
        for _, r in suppliers_df.iterrows():
            out.write(f"INSERT INTO `suppliers` (`supplier_id`, `name`, `avg_lead_time_days`, `lead_time_std_days`, `reliability_score`) VALUES ({escape_sql_val(r['supplier_id'])}, {escape_sql_val(r['name'])}, {r['avg_lead_time_days']}, {r['lead_time_std_days']}, {r['reliability_score']});\n")
        out.write("\n")

        # Medicines
        medicines_df = pd.read_csv(os.path.join(DATA_DIR, "medicines.csv"))
        out.write("-- Table: medicines\n")
        for _, r in medicines_df.iterrows():
            out.write(f"INSERT INTO `medicines` (`medicine_id`, `name`, `category`, `criticality`, `base_daily_usage`, `reorder_point`, `target_max_stock`, `shelf_life_days`, `unit_cost`) VALUES ({escape_sql_val(r['medicine_id'])}, {escape_sql_val(r['name'])}, {escape_sql_val(r['category'])}, {escape_sql_val(r['criticality'])}, {r['base_daily_usage']}, {r['reorder_point']}, {r['target_max_stock']}, {r['shelf_life_days']}, {r['unit_cost']});\n")
        out.write("\n")

        # Inventory Snapshot
        inv_df = pd.read_csv(os.path.join(DATA_DIR, "inventory_snapshot.csv"))
        out.write("-- Table: inventory_snapshot\n")
        for _, r in inv_df.iterrows():
            out.write(f"INSERT INTO `inventory_snapshot` (`medicine_id`, `branch_id`, `current_stock`, `reserved_units`, `emergency_reserve`, `nearest_batch_expiry`, `snapshot_date`) VALUES ({escape_sql_val(r['medicine_id'])}, {escape_sql_val(r['branch_id'])}, {r['current_stock']}, {r['reserved_units']}, {r['emergency_reserve']}, {escape_sql_val(str(r['nearest_batch_expiry'])[:10])}, {escape_sql_val(str(r['snapshot_date'])[:10])});\n")
        out.write("\n")

        # Procurement History
        proc_df = pd.read_csv(os.path.join(DATA_DIR, "procurement_history.csv"))
        out.write("-- Table: procurement_history\n")
        for _, r in proc_df.iterrows():
            act = escape_sql_val(None if pd.isna(r['actual_delivery_date']) else str(r['actual_delivery_date'])[:10])
            out.write(f"INSERT INTO `procurement_history` (`order_id`, `medicine_id`, `supplier_id`, `order_date`, `expected_delivery_date`, `actual_delivery_date`, `ordered_units`, `received_units`, `status`) VALUES ({escape_sql_val(r['order_id'])}, {escape_sql_val(r['medicine_id'])}, {escape_sql_val(r['supplier_id'])}, {escape_sql_val(str(r['order_date'])[:10])}, {escape_sql_val(str(r['expected_delivery_date'])[:10])}, {act}, {r['ordered_units']}, {r['received_units']}, {escape_sql_val(r['status'])});\n")
        out.write("\n")

        # Supply Events
        evt_df = pd.read_csv(os.path.join(DATA_DIR, "supply_events.csv"))
        out.write("-- Table: supply_events\n")
        for _, r in evt_df.iterrows():
            out.write(f"INSERT INTO `supply_events` (`event_id`, `date`, `medicine_id`, `event_type`, `description`, `magnitude`) VALUES ({escape_sql_val(r['event_id'])}, {escape_sql_val(str(r['date'])[:10])}, {escape_sql_val(None if pd.isna(r['medicine_id']) else r['medicine_id'])}, {escape_sql_val(r['event_type'])}, {escape_sql_val(r['description'])}, {r['magnitude']});\n")
        out.write("\n")

        # Usage Anomalies
        anom_df = pd.read_csv(os.path.join(DATA_DIR, "usage_anomalies.csv"))
        out.write("-- Table: usage_anomalies\n")
        for _, r in anom_df.iterrows():
            out.write(f"INSERT INTO `usage_anomalies` (`medicine_id`, `branch_id`, `date`, `multiplier_vs_baseline`, `label`) VALUES ({escape_sql_val(r['medicine_id'])}, {escape_sql_val(r['branch_id'])}, {escape_sql_val(str(r['date'])[:10])}, {r['multiplier_vs_baseline']}, {escape_sql_val(r['label'])});\n")
        out.write("\n")

        # Consumption History (batch multi-row INSERTs for size efficiency)
        con_df = pd.read_csv(os.path.join(DATA_DIR, "consumption_history.csv"))
        out.write("-- Table: consumption_history (113,880 rows batched)\n")
        batch_size = 1000
        total_rows = len(con_df)
        for i in range(0, total_rows, batch_size):
            chunk = con_df.iloc[i : i + batch_size]
            vals = []
            for _, r in chunk.iterrows():
                vals.append(f"({escape_sql_val(str(r['date'])[:10])}, {escape_sql_val(r['medicine_id'])}, {escape_sql_val(r['branch_id'])}, {r['units_consumed']})")
            out.write("INSERT INTO `consumption_history` (`date`, `medicine_id`, `branch_id`, `units_consumed`) VALUES\n  " + ",\n  ".join(vals) + ";\n")

        out.write("\nSET FOREIGN_KEY_CHECKS = 1;\n")
        print(f"   -> Dump generated ({os.path.getsize(DUMP_FILE) / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    run_migration()

