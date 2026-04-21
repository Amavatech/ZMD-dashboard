# Grafana Tools

These scripts interact with the Grafana HTTP API to manage dashboards and snapshots for the weather station data.

---

## `rebuild_dashboards.py`

**Purpose:** Rebuilds Grafana dashboards for all stations registered in `timestream_tables`.

```bash
python3 rebuild_dashboards.py
```

### When to Use

- After a bulk import of stations (e.g. via `import.py`) where dashboards were not auto-created.
- After changing the panel templates in `mqtt_dashboard/grafana_helpers.py`.
- When dashboards are broken or show incorrect data.

### What It Does

1. Opens a Flask application context.
2. Queries all `timestream_table` rows.
3. Calls `grafana_helpers.create_dashboard_table(table)` for each.
4. Prints OK/FAIL per station with the dashboard UID.
5. Commits updated UIDs to the database.

### Error Behaviour

Each station is processed in a try/except block. If one station's dashboard fails (Grafana returns an error, network issue, etc.), the error is printed and the script continues with the next station.

---

## `create_live_dashboard.py`

**Purpose:** Creates "live" Grafana dashboards — dashboards connected directly to the TimescaleDB datasource for real-time auto-updating views.

```bash
python3 create_live_dashboard.py
```

These dashboards use a TimescaleDB PostgreSQL datasource rather than Grafana's built-in snapshot format, allowing them to display data as it arrives.

---

## `create_live_snapshot.py`

**Purpose:** Creates Grafana snapshots from live dashboard data. Snapshots are static exports of a dashboard at a point in time — they do not auto-update and can be shared publicly.

```bash
python3 create_live_snapshot.py
```

**Use case:** Generating a publicly-accessible snapshot URL for a period report or sharing with stakeholders who don't have Grafana access.

---

## `create_timescale_dashboard.py`

**Purpose:** Creates Grafana dashboards configured specifically for TimescaleDB hypertable data, using time-series SQL queries targeting the `st_<station_id>` tables.

```bash
python3 create_timescale_dashboard.py
```

Similar to `rebuild_dashboards.py` but may include different panel configurations or query formats.

---

## `fetch_dashboards.py`

**Purpose:** Downloads the full JSON definition of all Grafana dashboards via the HTTP API and saves them to files. Used for backup or inspection of dashboard configurations.

```bash
python3 fetch_dashboards.py
```

Output files: `all_dashboards.json`, `dashboards_raw.json`, `dashboards_list.txt`

---

## `fix_all_dashboards.py`

**Purpose:** Iterates through all Grafana dashboards and repairs SQL queries that are in an incorrect format. This was used after the `migrate_to_station_ids.py` migration changed table names.

```bash
python3 fix_all_dashboards.py
```

The fix logic mirrors what is in `wiz2box_forward/import.py`'s `fix_dashboard_sql()` function — it updates panel `rawSql` to use the `st_<station_id>` naming convention.

---

## `get_dashboards_info.py`

**Purpose:** Extracts and prints metadata about all Grafana dashboards (UID, title, URL, creation time). Output is saved to `dashboards_info.json`.

```bash
python3 get_dashboards_info.py
```

---

## `format_dashboards_list.py`

**Purpose:** Formats the `dashboards_list.txt` file into a cleaner human-readable format. Helper/analysis script.

---

## Where These Scripts Write

| Script | Output |
|--------|--------|
| `fetch_dashboards.py` | `all_dashboards.json`, `dashboards_raw.json`, `dashboards_list.txt` |
| `get_dashboards_info.py` | `dashboards_info.json` |
| `rebuild_dashboards.py` | Updates `timestream_tables.db_uid` in the database |
| `fix_all_dashboards.py` | Modifies dashboards in Grafana via HTTP API |

---

## Grafana API Authentication

All these scripts authenticate with Grafana via an API key. The key is either hard-coded in the script or read from `config.ini` under `[Grafana]`:

```ini
[Grafana]
API_Key = eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0=
URL = http://localhost:3000
```

If the API key expires or is rotated, update it in `config.ini` and in any script that hard-codes it.

---

## Navigation

← [utilities/README.md](README.md) | [docs/README.md](../README.md)
