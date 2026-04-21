#!/usr/bin/env python3
"""
Export and purge stations (timestream_tables rows) that have never published data.

A station is considered empty when:
  - Its physical hypertable does not exist, OR
  - Its physical hypertable exists but contains zero rows.

Exempt stations are protected from deletion by listing their serial IDs
(one per line) in exempt_station_ids.txt next to this script.  Any station
whose MQTT topic contains one of those IDs as a path segment will be skipped.

Steps performed:
  1. Identify all empty stations.
  2. Split them into EXEMPT and TO-PURGE using exempt_station_ids.txt.
  3. Write a CSV report: exports/empty_stations_<timestamp>.csv
  4. In --execute mode: delete TO-PURGE stations from the database
     (measurements -> permissions -> timestream_tables) and drop their
     physical hypertables.

Usage:
    python3 purge_empty_stations.py            # dry-run (no changes)
    python3 purge_empty_stations.py --execute  # actually delete
"""

import argparse
import csv
import os
import re
from datetime import datetime

import psycopg2
from psycopg2 import sql

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXEMPT_FILE = os.path.join(SCRIPT_DIR, "exempt_station_ids.txt")
EXPORT_DIR  = os.path.join(SCRIPT_DIR, "exports")

DB_CONFIG = dict(
    dbname="mqtt_dashboard",
    user="postgres",
    password="campDashSQL",
    host="localhost",
    port=5432,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_exempt_ids() -> set:
    """Return a set of stripped non-empty lines from the exemptions file."""
    if not os.path.exists(EXEMPT_FILE):
        return set()
    with open(EXEMPT_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def is_exempt(topic: str, exempt_ids: set) -> bool:
    """True if any segment of the topic path matches an exempt ID."""
    parts = re.split(r"[/\-_]", topic)
    return bool(exempt_ids.intersection(parts))


def fetch_measurements(cur, table_id: int):
    cur.execute(
        "SELECT measurementid, name, unit, type, visible "
        "FROM timestream_measurements WHERE tableid = %s ORDER BY measurementid;",
        (table_id,),
    )
    return cur.fetchall()


def normalize_table_name(topic: str) -> str:
    """Mirror the logic in timescaleUtil._normalize_table_name."""
    return topic.replace("/", "_").lower().replace("-", "_")[:63]


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return cur.fetchone() is not None


def row_count(cur, table_name: str) -> int:
    cur.execute(
        sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table_name))
    )
    return cur.fetchone()[0]


def main():
    parser = argparse.ArgumentParser(
        description="Export and purge inactive stations with no published data."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the deletions (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    exempt_ids = load_exempt_ids()
    print(f"Exempt station IDs loaded: {len(exempt_ids)}")
    if exempt_ids:
        print(f"  {sorted(exempt_ids)}")
    print()

    if dry_run:
        print("DRY-RUN mode — no changes will be made. Pass --execute to apply.\n")
    else:
        print("EXECUTE mode — deletions will be committed.\n")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # ---- Fetch all station metadata ----------------------------------------
    cur.execute(
        "SELECT tt.tableid, tt.topic, tt.longitude, tt.latitude, tt.groupid, "
        "       b.name AS broker_name "
        "FROM timestream_tables tt "
        "LEFT JOIN brokers b ON b.brokerid = tt.brokerid "
        "ORDER BY tt.tableid;"
    )
    all_stations = cur.fetchall()
    print(f"Total stations in database: {len(all_stations)}")

    # ---- Classify stations --------------------------------------------------
    empty_exempt   = []   # rows that are empty but protected
    empty_to_purge = []   # rows that are empty and will be deleted
    active_count   = 0

    for table_id, topic, longitude, latitude, group_id, broker_name in all_stations:
        phys = normalize_table_name(topic)
        if not table_exists(cur, phys):
            reason = "no physical table"
        else:
            count = row_count(cur, phys)
            if count == 0:
                reason = "table exists but 0 rows"
            else:
                active_count += 1
                continue

        row = (table_id, topic, phys, reason, longitude, latitude, group_id, broker_name)
        if is_exempt(topic, exempt_ids):
            empty_exempt.append(row)
        else:
            empty_to_purge.append(row)

    total_empty = len(empty_exempt) + len(empty_to_purge)
    print(f"Active stations (have data):   {active_count}")
    print(f"Empty stations total:          {total_empty}")
    print(f"  Protected by exemptions:     {len(empty_exempt)}")
    print(f"  To be purged:                {len(empty_to_purge)}\n")

    # ---- Write CSV export ---------------------------------------------------
    os.makedirs(EXPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = os.path.join(EXPORT_DIR, f"empty_stations_{timestamp}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "tableid", "topic", "physical_table", "reason",
            "longitude", "latitude", "groupid", "broker_name",
            "status", "measurement_count", "measurement_names",
        ])
        for row in empty_exempt + empty_to_purge:
            table_id, topic, phys, reason, longitude, latitude, group_id, broker_name = row
            measurements = fetch_measurements(cur, table_id)
            meas_names   = "|".join(m[1] or "" for m in measurements)
            status       = "EXEMPT" if row in empty_exempt else "TO_PURGE"
            writer.writerow([
                table_id, topic, phys, reason,
                longitude, latitude, group_id, broker_name,
                status, len(measurements), meas_names,
            ])

    print(f"CSV report written: {csv_path}\n")

    if not empty_to_purge:
        print("Nothing to purge.")
        conn.close()
        return

    if dry_run:
        print("Dry-run complete. Run with --execute to apply deletions.")
        conn.close()
        return

    # ---- Execute deletions --------------------------------------------------
    print("Deleting metadata rows...")
    purge_ids = [row[0] for row in empty_to_purge]

    cur.execute("DELETE FROM timestream_measurements WHERE tableid = ANY(%s);", (purge_ids,))
    meas_deleted = cur.rowcount

    cur.execute("DELETE FROM permissions WHERE tableid = ANY(%s);", (purge_ids,))
    perm_deleted = cur.rowcount

    cur.execute("DELETE FROM timestream_tables WHERE tableid = ANY(%s);", (purge_ids,))
    tables_deleted = cur.rowcount

    conn.commit()

    # Drop empty physical tables outside the transaction
    conn.autocommit = True
    dropped = 0
    for table_id, topic, phys, reason, *_ in empty_to_purge:
        if reason != "no physical table":
            try:
                cur.execute(
                    sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE;").format(
                        sql.Identifier(phys)
                    )
                )
                dropped += 1
                print(f"  Dropped table: {phys}")
            except Exception as exc:
                print(f"  WARNING: could not drop {phys}: {exc}")

    print(
        f"\nDone.\n"
        f"  Stations removed:        {tables_deleted}\n"
        f"  Measurements removed:    {meas_deleted}\n"
        f"  Permissions removed:     {perm_deleted}\n"
        f"  Physical tables dropped: {dropped}\n"
        f"  Exempt (kept):           {len(empty_exempt)}\n"
    )
    conn.close()


if __name__ == "__main__":
    main()
