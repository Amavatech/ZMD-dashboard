#!/usr/bin/env python3
"""
Export and purge ALL stations that are NOT listed in exempt_station_ids.txt,
regardless of whether they have data or not.

Exempt stations are protected by listing their serial IDs (one per line) in
exempt_station_ids.txt next to this script.  Any station whose MQTT topic
contains one of those IDs as a path segment will be kept.

Steps performed:
  1. Identify all non-exempt stations.
  2. Write a CSV report: exports/non_exempt_stations_<timestamp>.csv
  3. In --execute mode: delete non-exempt stations from the database
     (measurements -> permissions -> timestream_tables) and drop their
     physical hypertables.

Usage:
    python3 purge_non_exempt_stations.py            # dry-run (no changes)
    python3 purge_non_exempt_stations.py --execute  # actually delete
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
    if not os.path.exists(EXEMPT_FILE):
        print(f"WARNING: {EXEMPT_FILE} not found — no stations will be exempt!")
        return set()
    with open(EXEMPT_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def is_exempt(topic: str, station_id: str, exempt_ids: set) -> bool:
    """A station is exempt if its station_id (or any topic path segment) appears in exempt_ids."""
    if station_id and station_id in exempt_ids:
        return True
    parts = re.split(r"[/\-_]", topic)
    return bool(exempt_ids.intersection(parts))


def physical_table_name(topic: str, station_id: str = None) -> str:
    """Return the physical table name — st_{station_id} if available, else normalized topic."""
    if station_id:
        return f"st_{station_id}"
    return topic.replace("/", "_").lower().replace("-", "_")[:63]


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    )
    return cur.fetchone() is not None


def fetch_row_count(cur, table_name: str) -> int:
    try:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table_name))
        )
        return cur.fetchone()[0]
    except Exception:
        return -1


def fetch_measurements(cur, table_id: int):
    cur.execute(
        "SELECT measurementid, name, unit, type, visible "
        "FROM timestream_measurements WHERE tableid = %s ORDER BY measurementid;",
        (table_id,),
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export and purge all non-exempt stations."
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

    if not exempt_ids:
        print("ERROR: No exempt IDs found. Refusing to run — this would delete everything.")
        return

    if dry_run:
        print("DRY-RUN mode — no changes will be made. Pass --execute to apply.\n")
    else:
        print("EXECUTE mode — deletions will be committed.\n")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # ---- Fetch all station metadata ----------------------------------------
    cur.execute(
        "SELECT tt.tableid, tt.topic, tt.station_id, tt.longitude, tt.latitude, tt.groupid, "
        "       b.name AS broker_name "
        "FROM timestream_tables tt "
        "LEFT JOIN brokers b ON b.brokerid = tt.brokerid "
        "ORDER BY tt.tableid;"
    )
    all_stations = cur.fetchall()
    print(f"Total stations in database: {len(all_stations)}")

    # ---- Classify stations --------------------------------------------------
    to_keep  = []
    to_purge = []

    for table_id, topic, station_id, longitude, latitude, group_id, broker_name in all_stations:
        phys = physical_table_name(topic, station_id)
        row  = (table_id, topic, station_id, phys, longitude, latitude, group_id, broker_name)
        if is_exempt(topic, station_id, exempt_ids):
            to_keep.append(row)
        else:
            to_purge.append(row)

    print(f"Exempt (to keep):   {len(to_keep)}")
    print(f"Non-exempt (purge): {len(to_purge)}\n")

    # ---- Write CSV export ---------------------------------------------------
    os.makedirs(EXPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = os.path.join(EXPORT_DIR, f"non_exempt_stations_{timestamp}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "tableid", "topic", "station_id", "physical_table",
            "longitude", "latitude", "groupid", "broker_name",
            "status", "has_physical_table", "row_count",
            "measurement_count", "measurement_names",
        ])
        for rows, status in [(to_keep, "KEEP"), (to_purge, "TO_PURGE")]:
            for row in rows:
                table_id, topic, station_id, phys, longitude, latitude, group_id, broker_name = row
                has_phys = table_exists(cur, phys)
                rcount   = fetch_row_count(cur, phys) if has_phys else 0
                measurements = fetch_measurements(cur, table_id)
                meas_names   = "|".join(m[1] or "" for m in measurements)
                writer.writerow([
                    table_id, topic, station_id, phys,
                    longitude, latitude, group_id, broker_name,
                    status, has_phys, rcount,
                    len(measurements), meas_names,
                ])

    print(f"CSV report written: {csv_path}\n")

    if not to_purge:
        print("Nothing to purge.")
        conn.close()
        return

    if dry_run:
        print("Dry-run complete. Run with --execute to apply deletions.")
        conn.close()
        return

    # ---- Execute deletions --------------------------------------------------
    print("Deleting metadata rows...")
    purge_ids = [row[0] for row in to_purge]

    cur.execute("DELETE FROM timestream_measurements WHERE tableid = ANY(%s);", (purge_ids,))
    meas_deleted = cur.rowcount

    cur.execute("DELETE FROM permissions WHERE tableid = ANY(%s);", (purge_ids,))
    perm_deleted = cur.rowcount

    cur.execute("DELETE FROM timestream_tables WHERE tableid = ANY(%s);", (purge_ids,))
    tables_deleted = cur.rowcount

    conn.commit()

    # Drop physical hypertables outside the transaction
    conn.autocommit = True
    dropped = 0
    for table_id, topic, station_id, phys, *_ in to_purge:
        if table_exists(cur, phys):
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
        f"  Kept (exempt):           {len(to_keep)}\n"
    )
    conn.close()


if __name__ == "__main__":
    main()
