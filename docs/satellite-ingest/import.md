# `import.py` — Direct Database Import

**Script:** `wiz2box_forward/import.py`  
**Purpose:** Reads `.dat` files from `EUMETSAT/` and writes them **directly** into TimescaleDB, bypassing the MQTT broker entirely.

---

## When to Use This Script

Use `import.py` instead of `download.py` when:
- The MQTT broker is unavailable or unreachable.
- You need to bulk-backfill historical data without overloading the MQTT pipeline.
- You want to import data from already-downloaded `.dat` files.
- You are doing a one-time migration of historical data.

Do **not** use this script in normal operation — the MQTT pipeline (`download.py`) is preferred because it preserves full observability (all data flows through the subscriber, stats are reported, etc.).

---

## What It Does (Step by Step)

1. **Reads `stations.csv`** — same file as `download.py`.

2. **Finds `.dat` files** in `EUMETSAT/<StationName>_DCP_<DCP_ID>/`:
   - `<StationName>_TableHour.dat`
   - `<StationName>_TableSYNOP.dat`

3. **Determines the MQTT-equivalent topic** for each file:
   ```
   cs/v1/data/cr1000x/<Serial>/<HOUR|SYNOP>
   ```
   This topic is used to look up or create the `timestream_tables` metadata row.

4. **Ensures metadata rows exist** — checks `timestream_tables` for the topic; creates a row if missing (with `brokerID=11`, `groupID=6`).

5. **Checks the latest existing timestamp** — queries the hypertable for the newest `time` value to avoid reinserting duplicate rows.

6. **Reads the `.dat` file** with pandas (`skiprows=4` to skip the 4 TOA5 header rows).

7. **Inserts only new rows** — filters to rows with a `TIMESTAMP` newer than the latest DB timestamp.

8. **Calls `timescaleUtil.write_records()`** — same function used by the live subscriber.

9. **Calls `timescaleUtil.write_weather_data()`** — also mirrors the subscriber's behaviour.

---

## Station ID Inference

`import.py` includes its own station ID inference (`_infer_station_id_from_row()`):

1. `Station_Name` column in the data row.
2. `Station_ID` column in the data row.
3. Topic path segments (reverse scan, skipping known suffixes like `HOUR`, `SYNOP`, `DATA`).

---

## Schema Enforcement

The script explicitly sets `timescaleUtil._schema_name = "public"` to ensure all operations use the `public` schema — especially important because the module has a configurable schema variable.

---

## Grafana Dashboard Creation

When creating a new `timestream_tables` row, `import.py` also calls `mySqlUtil.create_dashboard_table()` to register the station in Grafana. If Grafana is unavailable, the error is logged and the import continues.

The script also contains a `fix_dashboard_sql()` helper that can patch existing Grafana dashboards to use the correct SQL query format. This is a utility function and is not called in the main import flow.

---

## Running the Script

```bash
cd /home/ubuntu/mqtt_dashboard
source venv/bin/activate
python3 wiz2box_forward/import.py
```

Output is logged at `INFO` level to stdout.

---

## Test Scripts

Two test scripts are provided for development:

| Script | Purpose |
|--------|---------|
| `test_dryrun.py` | Run import in dry-run mode — parses files and prints what would be inserted, without writing to the DB |
| `test_import_single.py` | Import a single station's data — useful for debugging one station without running everything |

---

## Navigation

← [satellite-ingest/README.md](README.md) | [docs/README.md](../README.md)
