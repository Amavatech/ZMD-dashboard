#!/usr/bin/env python3
"""
Count data records received per station ID from the weather_data table.

Station IDs are deduplicated — if the same ID appears across multiple MQTT
topics it is counted as one station.

The "transmissions" column counts distinct timestamps per station (i.e. the
number of separate message payloads received), rather than the total number of
metric rows, so stations with more sensors don't appear artificially busier.

Results are printed to the terminal and saved to:
  exports/station_counts_<timestamp>.csv

Usage:
    python3 count_station_data.py                  # all time
    python3 count_station_data.py --days 7         # last 7 days
    python3 count_station_data.py --since 2026-02-01   # since a date
"""

import argparse
import csv
import os
import re
from datetime import datetime, timezone, timedelta

import psycopg2

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


def load_exempt_ids() -> set:
    if not os.path.exists(EXEMPT_FILE):
        return set()
    with open(EXEMPT_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def station_id_matches_exempt(station_id: str, exempt_ids: set) -> bool:
    """Match station_id against exempt IDs, splitting on common separators."""
    parts = re.split(r"[/\-_]", station_id)
    return bool(exempt_ids.intersection(parts)) or station_id in exempt_ids


def main():
    parser = argparse.ArgumentParser(description="Count data received per station ID.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, metavar="N",
                       help="Count records from the last N days only.")
    group.add_argument("--since", metavar="YYYY-MM-DD",
                       help="Count records since this date (UTC).")
    args = parser.parse_args()

    # Build time filter
    time_filter = ""
    params: list = []
    if args.days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
        time_filter = "WHERE time >= %s"
        params.append(cutoff)
        label = f"last {args.days} days"
    elif args.since:
        cutoff = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        time_filter = "WHERE time >= %s"
        params.append(cutoff)
        label = f"since {args.since}"
    else:
        label = "all time"

    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    query = f"""
        SELECT
            station_id,
            COUNT(DISTINCT time)   AS transmissions,
            COUNT(*)               AS total_metric_rows,
            MIN(time)              AS first_seen,
            MAX(time)              AS last_seen
        FROM weather_data
        {time_filter}
        GROUP BY station_id
        ORDER BY transmissions DESC, station_id;
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    exempt_ids = load_exempt_ids()

    # Annotate with exempt status
    annotated = []
    for station_id, transmissions, total_rows, first_seen, last_seen in rows:
        exempt = station_id_matches_exempt(str(station_id), exempt_ids)
        annotated.append((
            station_id, transmissions, total_rows,
            first_seen, last_seen, "EXEMPT" if exempt else "non-exempt"
        ))

    # ---- Print summary -------------------------------------------------------
    total_transmissions = sum(r[1] for r in annotated)
    print(f"Station data counts ({label})")
    print(f"Unique station IDs:   {len(annotated)}")
    print(f"Total transmissions:  {total_transmissions:,}")
    print()
    print(f"{'station_id':<20} {'transmissions':>14} {'metric_rows':>12}  {'exempt':<12}  last_seen")
    print("-" * 90)
    for station_id, transmissions, total_rows, first_seen, last_seen, status in annotated:
        print(
            f"{str(station_id):<20} {transmissions:>14,} {total_rows:>12,}  "
            f"{status:<12}  {last_seen}"
        )

    # ---- Write CSV -----------------------------------------------------------
    os.makedirs(EXPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = os.path.join(EXPORT_DIR, f"station_counts_{timestamp}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "station_id", "transmissions", "total_metric_rows",
            "first_seen", "last_seen", "exempt_status",
        ])
        for station_id, transmissions, total_rows, first_seen, last_seen, status in annotated:
            writer.writerow([
                station_id, transmissions, total_rows,
                first_seen, last_seen, status,
            ])

    print(f"\nCSV saved: {csv_path}")


if __name__ == "__main__":
    main()
