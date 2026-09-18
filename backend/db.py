"""
MySQL Database Connectivity and Persistence Layer for Healthcare Supply Chain Intelligence.
Handles connection pooling, table queries into pandas DataFrames, and transaction persistence.
"""
import os
import logging
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# Load backend .env if available
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH)

logger = logging.getLogger("supply_chain.db")

USE_MYSQL = os.getenv("USE_MYSQL", "true").lower() in ("true", "1", "yes")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "supply_chain_db")

_ENGINE: Optional[Engine] = None


def get_db_url(include_db: bool = True) -> str:
    """Build MySQL connection URL using PyMySQL dialect."""
    db_part = f"/{MYSQL_DATABASE}" if include_db else ""
    return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}{db_part}?charset=utf8mb4"


def get_db_engine() -> Engine:
    """Returns a singleton SQLAlchemy engine with health-check pre-ping."""
    global _ENGINE
    if _ENGINE is None:
        url = get_db_url(include_db=True)
        _ENGINE = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
        )
    return _ENGINE


def check_mysql_connection() -> Tuple[bool, str]:
    """Fast health check to verify MySQL connectivity."""
    if not USE_MYSQL:
        return False, "MySQL is disabled via USE_MYSQL=false"
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"Connected to MySQL at {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    except Exception as e:
        return False, f"MySQL connection failed: {e}"


def load_table_as_dataframe(
    table_name: str,
    columns: Optional[List[str]] = None,
    parse_dates: Optional[List[str]] = None
) -> pd.DataFrame:
    """Query a table from MySQL into a pandas DataFrame."""
    engine = get_db_engine()
    col_clause = ", ".join([f"`{c}`" for c in columns]) if columns else "*"
    query = f"SELECT {col_clause} FROM `{table_name}`"
    
    df = pd.read_sql_query(
        sql=text(query),
        con=engine.connect(),
        parse_dates=parse_dates,
    )
    return df


def update_inventory_stock(medicine_id: str, branch_id: str, new_stock: float) -> bool:
    """Persist updated current_stock for a given SKU and branch."""
    try:
        engine = get_db_engine()
        stmt = text("""
            UPDATE `inventory_snapshot`
            SET `current_stock` = :stock
            WHERE `medicine_id` = :mid AND `branch_id` = :bid
        """)
        with engine.begin() as conn:
            conn.execute(stmt, {"stock": new_stock, "mid": medicine_id, "bid": branch_id})
        return True
    except Exception as e:
        logger.error(f"Failed to update inventory stock in MySQL: {e}")
        return False


def persist_dispatched_transfer(record: Dict[str, Any]) -> bool:
    """Insert a dispatched transfer record into MySQL."""
    try:
        engine = get_db_engine()
        stmt = text("""
            INSERT INTO `dispatched_transfers` (
                `transfer_id`, `timestamp`, `medicine_id`, `medicine_name`,
                `from_branch`, `to_branch`, `units`, `status`
            ) VALUES (
                :transfer_id, :timestamp, :medicine_id, :medicine_name,
                :from_branch, :to_branch, :units, :status
            )
        """)
        with engine.begin() as conn:
            conn.execute(stmt, record)
        return True
    except Exception as e:
        logger.error(f"Failed to persist lateral transfer to MySQL: {e}")
        return False


def persist_procurement_order(record: Dict[str, Any]) -> bool:
    """Insert a new purchase order into MySQL procurement_history."""
    try:
        engine = get_db_engine()
        stmt = text("""
            INSERT INTO `procurement_history` (
                `order_id`, `medicine_id`, `supplier_id`, `branch_id`,
                `medicine_name`, `order_date`, `expected_delivery_date`,
                `actual_delivery_date`, `ordered_units`, `received_units`,
                `status`, `unit_cost`, `total_cost`
            ) VALUES (
                :order_id, :medicine_id, :supplier_id, :branch_id,
                :medicine_name, :order_date, :expected_delivery_date,
                :actual_delivery_date, :ordered_units, :received_units,
                :status, :unit_cost, :total_cost
            )
        """)
        payload = {
            "order_id": record.get("order_id"),
            "medicine_id": record.get("medicine_id"),
            "supplier_id": record.get("supplier_id"),
            "branch_id": record.get("branch_id"),
            "medicine_name": record.get("medicine_name"),
            "order_date": record.get("order_date"),
            "expected_delivery_date": record.get("expected_delivery_date"),
            "actual_delivery_date": record.get("actual_delivery_date") if record.get("actual_delivery_date") != "NaT" else None,
            "ordered_units": int(record.get("ordered_units", 0)),
            "received_units": int(record.get("received_units", 0)),
            "status": record.get("status", "PENDING"),
            "unit_cost": float(record.get("unit_cost", 0.0)),
            "total_cost": float(record.get("total_cost", 0.0)),
        }
        with engine.begin() as conn:
            conn.execute(stmt, payload)
        return True
    except Exception as e:
        logger.error(f"Failed to persist procurement order to MySQL: {e}")
        return False

