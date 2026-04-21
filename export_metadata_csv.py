#!/usr/bin/env python3
"""
Export all metadata tables from the mqtt_dashboard database to CSV files.
Tables exported: brokers, timestream_tables, timestream_measurements,
                 users, groups, permissions
"""

import csv
import os
from datetime import datetime
import psycopg2

DB_CONFIG = {
    "dbname": "mqtt_dashboard",
    "user": "postgres",
    "password": "campDashSQL",
    "host": "localhost",
    "port": 5432,
}

TABLES = [
    "brokers",
    "timestream_tables",
    "timestream_measurements",
    "users",
    "groups",
    "permissions",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "exports")


def export_table(cursor, table_name: str, output_path: str) -> int:
    cursor.execute(f"SELECT * FROM {table_name} ORDER BY 1;")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        writer.writerows(rows)

    return len(rows)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Connecting to database '{DB_CONFIG['dbname']}' on {DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print(f"Exporting to: {OUTPUT_DIR}/\n")
    print(f"{'Table':<30} {'Rows':>6}  File")
    print("-" * 70)

    for table in TABLES:
        filename = f"{table}_{timestamp}.csv"
        output_path = os.path.join(OUTPUT_DIR, filename)
        try:
            row_count = export_table(cursor, table, output_path)
            print(f"{table:<30} {row_count:>6}  {filename}")
        except Exception as e:
            print(f"{table:<30}  ERROR: {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
