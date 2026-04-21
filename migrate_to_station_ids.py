#!/usr/bin/env python3
"""
Migration: topic-per-row → station_id-per-row
==============================================
Merges all timestream_table rows that belong to the same physical station into
a single row keyed by station_id (logger serial number).

Steps
-----
1.  Classify every topic → canonical station_id
2.  For each station_id group:
    a.  Choose the "primary" surviving timestream_table row
    b.  Set station_id, topics[] on the primary row
    c.  Merge timestream_measurements (dedup by name) into primary
    d.  Rename / merge physical per-topic hypertables into  st_{station_id}
    e.  Delete duplicate timestream_table rows (cascades measurements/permissions)
    f.  Delete orphaned Grafana dashboards for removed rows
3.  Commit

Run as: python3 migrate_to_station_ids.py [--dry-run]
"""
import argparse
import re
import sys
import os
import logging
import psycopg2
import requests
from psycopg2 import sql
from collections import defaultdict
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DB_CONFIG = dict(
    dbname="mqtt_dashboard",
    user="postgres",
    password="campDashSQL",
    host="localhost",
    port=5432,
)

# Grafana config
GRAFANA_URL = "http://127.0.0.1:3000"
GRAFANA_HDR = {
    "Authorization": "Bearer eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0=",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Station-ID extraction – must match what _infer_station_id does in subscriber
# ---------------------------------------------------------------------------

def extract_station_id(topic: str, all_topics_by_name: Optional[dict] = None) -> str:
    """Return canonical station_id for a topic.

    Priority:
    1.  First 4+ digit numeric run found in the path
    2.  For name-only /data topics: look up the numeric ID from sibling topics
    3.  Non-numeric alphanumeric segment (e.g. BZZW-D8JH-JVVR)
    """
    # 1) Numeric ID anywhere in path
    m = re.search(r'/(\d{4,})(/|$)', topic)
    if m:
        return m.group(1)

    # 2) Named /data topic without numeric ID
    #    Extract station name and try to find associated numeric ID from siblings
    name_m = re.search(r'/0-894-2-([^/]+)/data', topic)
    if name_m:
        name = name_m.group(1)
        if all_topics_by_name and name in all_topics_by_name:
            for sibling in all_topics_by_name[name]:
                num = re.search(r'/(\d{4,})(/|$)', sibling)
                if num:
                    return num.group(1)
        # Fallback: use the name itself as the station_id
        return name

    # 3) Last non-trivial path segment (e.g. BZZW-D8JH-JVVR)
    parts = [p for p in re.split(r'[/]', topic) if p and p.lower() not in
             {'data', 'cr1000x', 'cr1000', 'synop', 'hour', 'cr350', 'satellite',
              'status', 'state', 'table2m', 'campbell', 'v1', 'campbell-v1',
              'southafrica', 'zmb', 'stellenbosch', 'csa', 'csaf', 'limpopo'}]
    return parts[-1] if parts else topic


def physical_table_name(topic: str) -> str:
    """Reproduce the normalisation used in timescaleUtil._normalize_table_name."""
    return topic.lower().replace("/", "_").replace("-", "_")[:63]


def st_table_name(station_id: str) -> str:
    return f"st_{station_id.lower().replace('-', '_')}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ddl(conn, cur, stmt, params=None):
    """Execute a DDL statement that requires autocommit (ALTER TABLE, DROP TABLE etc.)."""
    try:
        conn.commit()          # close any open transaction first
    except Exception:
        pass
    conn.autocommit = True
    try:
        if params:
            cur.execute(stmt, params)
        else:
            cur.execute(stmt)
    finally:
        conn.autocommit = False


def table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s", (name,))
    return cur.fetchone() is not None


def row_count(cur, name: str) -> int:
    try:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(
            sql.Identifier(name)))
        return cur.fetchone()[0]
    except Exception:
        return 0


def grafana_delete_uid(uid: str):
    if not uid:
        return
    try:
        requests.delete(f"{GRAFANA_URL}/api/dashboards/uid/{uid}",
                        headers=GRAFANA_HDR, verify=False, timeout=5)
    except Exception as e:
        log.warning("Grafana delete uid=%s failed: %s", uid, e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print actions without committing.")
    args = ap.parse_args()
    dry = args.dry_run
    if dry:
        log.info("DRY-RUN mode – no changes will be committed")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # ── 1.  Load all topics ───────────────────────────────────────────────
    cur.execute("SELECT tableid, topic, db_uid FROM timestream_tables ORDER BY tableid;")
    rows = cur.fetchall()
    log.info("Loaded %d timestream_table rows", len(rows))

    # Build name → [topic] map for resolving named /data topics
    name_to_topics: dict = defaultdict(list)
    for _, topic, _ in rows:
        m = re.search(r'/0-894-2-([^/]+)/', topic)
        if m:
            name_to_topics[m.group(1)].append(topic)

    # ── 2.  Classify every topic ──────────────────────────────────────────
    topic_to_sid: dict = {}
    for tid, topic, _ in rows:
        sid = extract_station_id(topic, name_to_topics)
        topic_to_sid[topic] = sid

    # Group tableids by station_id
    groups: dict = defaultdict(list)   # sid → [(tableid, topic, db_uid)]
    for tid, topic, db_uid in rows:
        sid = topic_to_sid[topic]
        groups[sid].append((tid, topic, db_uid))

    log.info("Found %d distinct station_ids from %d topics", len(groups), len(rows))

    # ── 3.  Process each station group ───────────────────────────────────
    merged_count = 0
    skipped_count = 0

    for sid, members in sorted(groups.items(), key=lambda x: x[0]):
        # Choose primary row:
        # preference: /data topic > SYNOP > HOUR > anything (most measurements)
        def priority(m):
            tid, topic, _ = m
            if topic.endswith('/data'):
                return (0, 0)
            if topic.endswith('/SYNOP'):
                return (1, 0)
            if topic.endswith('/HOUR'):
                return (2, 0)
            return (3, 0)

        members_sorted = sorted(members, key=priority)
        primary_tid, primary_topic, primary_db_uid = members_sorted[0]
        duplicates = members_sorted[1:]

        all_topics = [t for _, t, _ in members_sorted]
        st_name = st_table_name(sid)

        log.info(
            "Station %-8s  primary_tid=%-4d  topics=%d  st_table=%s",
            sid, primary_tid, len(members), st_name
        )

        if not dry:
            # ── 3a.  Set station_id and topics[] on primary row ───────────
            cur.execute(
                "UPDATE timestream_tables SET station_id=%s, topics=%s WHERE tableid=%s",
                (sid, all_topics, primary_tid)
            )

        # ── 3b.  Merge measurements ───────────────────────────────────────
        if not dry:
            # Collect existing measurement names on the primary
            cur.execute("SELECT name FROM timestream_measurements WHERE tableid=%s",
                        (primary_tid,))
            existing_names = {r[0] for r in cur.fetchall()}

            for dup_tid, dup_topic, dup_uid in duplicates:
                cur.execute(
                    "SELECT name, directionname, unit, nickname, type, graph, visible, status "
                    "FROM timestream_measurements WHERE tableid=%s",
                    (dup_tid,))
                for mrow in cur.fetchall():
                    mname = mrow[0]
                    if mname not in existing_names:
                        cur.execute(
                            """INSERT INTO timestream_measurements
                               (name, directionname, tableid, unit, nickname, type, graph, visible, status)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (mname, mrow[1], primary_tid, mrow[2], mrow[3],
                             mrow[4], mrow[5], mrow[6], mrow[7])
                        )
                        existing_names.add(mname)

        # ── 3c.  Merge / rename physical tables ───────────────────────────
        # Build list of physical tables that exist for this station, sorted
        # by row count descending so we migrate DATA into the biggest one
        phys_existing = []
        for _, t, _ in members_sorted:
            pn = physical_table_name(t)
            if table_exists(cur, pn):
                rc = row_count(cur, pn)
                phys_existing.append((pn, rc))

        # Also check if st_* already exists
        st_already = table_exists(cur, st_name)

        if not dry:
            if not phys_existing and not st_already:
                # No physical table yet – create it now
                _ddl(conn, cur, sql.SQL("""
                        CREATE TABLE IF NOT EXISTS public.{t} (
                            time TIMESTAMPTZ NOT NULL,
                            measure_name TEXT NOT NULL,
                            measure_value_double DOUBLE PRECISION NULL,
                            measure_value_varchar TEXT NULL,
                            unit TEXT NULL,
                            measurement_type TEXT NULL
                        )
                    """).format(t=sql.Identifier(st_name)))
                try:
                    _ddl(conn, cur,
                         "SELECT create_hypertable(%s, %s, if_not_exists => TRUE);",
                         (f"public.{st_name}", "time"))
                except Exception as e:
                    log.warning("create_hypertable %s: %s", st_name, e)

            elif not st_already and phys_existing:
                # Rename the table with the most data to st_{sid}
                primary_phys = max(phys_existing, key=lambda x: x[1])[0]
                if primary_phys != st_name:
                    try:
                        log.info("  RENAME %s → %s", primary_phys, st_name)
                        _ddl(conn, cur,
                             sql.SQL("ALTER TABLE public.{} RENAME TO {};").format(
                                 sql.Identifier(primary_phys),
                                 sql.Identifier(st_name)
                             ))
                        phys_existing = [(p, r) for p, r in phys_existing if p != primary_phys]
                    except Exception as e:
                        log.warning("  Could not rename %s: %s", primary_phys, e)

                # Merge remaining physical tables
                for pn, _ in phys_existing:
                    if pn == st_name:
                        continue
                    if table_exists(cur, pn):
                        log.info("  MERGE data %s → %s", pn, st_name)
                        try:
                            cur.execute(
                                sql.SQL("""
                                    INSERT INTO public.{dst}
                                    (time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type)
                                    SELECT time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type
                                    FROM public.{src}
                                    ON CONFLICT DO NOTHING
                                """).format(
                                    dst=sql.Identifier(st_name),
                                    src=sql.Identifier(pn)
                                )
                            )
                            conn.commit()
                            _ddl(conn, cur,
                                 sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE;").format(
                                     sql.Identifier(pn)))
                        except Exception as e:
                            log.warning("  Merge/drop %s failed: %s", pn, e)
                            try:
                                conn.rollback()
                            except Exception:
                                pass

            elif st_already and phys_existing:
                # st_ table exists, just merge old ones in
                for pn, _ in phys_existing:
                    if pn == st_name:
                        continue
                    log.info("  MERGE data %s → %s (st_ exists)", pn, st_name)
                    try:
                        cur.execute(
                            sql.SQL("""
                                INSERT INTO public.{dst}
                                (time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type)
                                SELECT time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type
                                FROM public.{src}
                                ON CONFLICT DO NOTHING
                            """).format(
                                dst=sql.Identifier(st_name),
                                src=sql.Identifier(pn)
                            )
                        )
                        conn.commit()
                        _ddl(conn, cur,
                             sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE;").format(
                                 sql.Identifier(pn)))
                    except Exception as e:
                        log.warning("  Merge/drop %s (into existing st_) failed: %s", pn, e)
                        try:
                            conn.rollback()
                        except Exception:
                            pass

            # Update primary row's topic to the canonical form and also update
            # the physical_table reference used by Grafana SQL
            cur.execute(
                "UPDATE timestream_tables SET topic=%s WHERE tableid=%s",
                (primary_topic, primary_tid)
            )

        # ── 3d.  Delete duplicate metadata rows ───────────────────────────
        for dup_tid, dup_topic, dup_uid in duplicates:
            log.info("  DELETE dup tableid=%d topic=%s", dup_tid, dup_topic)
            if not dry:
                cur.execute("DELETE FROM timestream_measurements WHERE tableid=%s", (dup_tid,))
                cur.execute("DELETE FROM permissions WHERE tableid=%s", (dup_tid,))
                cur.execute("DELETE FROM timestream_tables WHERE tableid=%s", (dup_tid,))
            # Delete orphaned Grafana dashboard
            grafana_delete_uid(dup_uid)

        if len(duplicates) > 0:
            merged_count += len(duplicates)
        else:
            skipped_count += 1

        if not dry:
            conn.commit()

    log.info("Migration complete: %d duplicate rows merged, %d single-topic stations",
             merged_count, skipped_count)

    # ── 4.  Add index on weather_data.station_id if missing ──────────────
    if not dry:
        try:
            conn.commit()
        except Exception:
            pass
        try:
            _ddl(conn, cur, """
                CREATE INDEX IF NOT EXISTS weather_data_station_id_idx
                ON public.weather_data (station_id, time DESC);
            """)
            log.info("Ensured index on weather_data.station_id")
        except Exception as e:
            log.warning("weather_data index: %s", e)

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
