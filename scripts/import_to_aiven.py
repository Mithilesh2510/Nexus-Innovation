#!/usr/bin/env python
"""
Direct importer for Aiven / Cloud MySQL databases.
Reads data/supply_chain.sql and executes it against the cloud database.
"""
import os
import sys
import getpass
import pymysql

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILE = os.path.join(ROOT_DIR, "data", "supply_chain.sql")

def main():
    print("=" * 60)
    print(" Cloud MySQL Dataset Importer (Aiven)")
    print("=" * 60)

    default_host = "mysql-e220b0-logesh0781-1dd7.i.aivencloud.com"
    default_port = 17149
    default_user = "avnadmin"

    host = input(f"Aiven Host [{default_host}]: ").strip() or default_host
    port_input = input(f"Aiven Port [{default_port}]: ").strip() or str(default_port)
    port = int(port_input)
    user = input(f"Aiven User [{default_user}]: ").strip() or default_user
    password = getpass.getpass("Aiven Password: ").strip()

    if not password:
        print("[ERROR] Password cannot be empty.")
        sys.exit(1)

    print(f"\n-- Connecting to {host}:{port}...")
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=15
        )
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    print("[SUCCESS] Connected to Aiven MySQL server.")

    print(f"-- Reading SQL dump: {os.path.relpath(SQL_FILE, ROOT_DIR)}...")
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into statements
    statements = [stmt.strip() for stmt in content.split(";") if stmt.strip()]
    total = len(statements)
    print(f"-- Executing {total:,} SQL statements...")

    executed = 0
    errors = 0
    for stmt in statements:
        try:
            cursor.execute(stmt)
            executed += 1
            if executed % 10 == 0 or executed == total:
                print(f"   Progress: {executed}/{total} statements executed...", end="\r")
        except Exception as e:
            errors += 1

    print(f"\n\n[SUCCESS] Cloud database import completed! ({executed} statements executed successfully).")
    conn.close()

if __name__ == "__main__":
    main()

