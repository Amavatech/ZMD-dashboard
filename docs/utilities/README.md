# Utilities — Overview

The project root contains several standalone utility scripts for database maintenance, Grafana management, and operational analysis. These are run manually or on demand — they are not part of the persistent services.

---

## Contents

- [database-maintenance.md](database-maintenance.md) — Station purge, data counting, metadata export, migration
- [grafana-tools.md](grafana-tools.md) — Dashboard rebuild, snapshot creation, and Grafana query tools
- [redundant-scripts.md](redundant-scripts.md) — Scripts and files that are obsolete or superseded
- [testing.md](testing.md) — Test and development scripts

---

## Script Inventory

| Script | Location | Category | Summary |
|--------|----------|----------|---------|
| `purge_empty_stations.py` | root | DB maintenance | Remove stations with no data |
| `purge_non_exempt_stations.py` | root | DB maintenance | Remove all non-exempt stations |
| `count_station_data.py` | root | DB maintenance | Count records per station |
| `export_metadata_csv.py` | root | DB maintenance | Export all relational tables to CSV |
| `migrate_to_station_ids.py` | root | DB maintenance | One-time migration (already run) |
| `rebuild_dashboards.py` | root | Grafana | Rebuild Grafana dashboards for all stations |
| `create_live_dashboard.py` | root | Grafana | Create live Grafana dashboards |
| `create_live_snapshot.py` | root | Grafana | Create Grafana snapshots for live data |
| `create_timescale_dashboard.py` | root | Grafana | Create TimescaleDB-specific dashboards |
| `fetch_dashboards.py` | root | Grafana | Fetch all dashboard JSON from Grafana API |
| `fix_all_dashboards.py` | root | Grafana | Fix SQL queries in existing dashboards |
| `get_dashboards_info.py` | root | Grafana | Extract dashboard metadata |
| `format_dashboards_list.py` | root | Grafana | Format a list of dashboards |
| `create_panels_270.py` | root | Grafana | ⚠️ One-off script for station 270 |
| `create_static_snapshot.py` | root | Grafana | ⚠️ Development artifact |
| `create_test_snapshot.py` | root | Grafana | ⚠️ Development artifact |
| `test_queries.py` | root | Dev/test | Ad-hoc database query testing |

---

## Common Setup

All root-level scripts connect directly to PostgreSQL using hardcoded credentials:

```python
DB_CONFIG = dict(
    dbname="mqtt_dashboard",
    user="postgres",
    password="campDashSQL",
    host="localhost",
    port=5432,
)
```

Run them from the project root with the virtual environment active:
```bash
cd /home/ubuntu/mqtt_dashboard
source venv/bin/activate
python3 <script_name>.py
```

---

## `exempt_station_ids.txt`

A plain text file used by purge scripts to protect active stations:

```
# One station ID per line. Lines starting with # are comments.
LusakaAirport
KitweStation
60790
```

The purge scripts match against:
- The `station_id` column in `timestream_tables`.
- Individual path segments of the MQTT topic (split on `/`, `-`, `_`).

**Always review and update this file before running any purge script.**

---

## Navigation

← [docs/README.md](../README.md)
