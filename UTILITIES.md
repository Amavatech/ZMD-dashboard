# Utilities & Maintenance Scripts

Scripts for database maintenance, Grafana management, data forwarding, and testing. These are one-off or periodic tools; they are **not** long-running services.

---

## Root-Level Scripts

All scripts below live in `/home/ubuntu/mqtt_dashboard/`. Run them from that directory using the project virtual environment:

```bash
cd /home/ubuntu/mqtt_dashboard
./venv/bin/python3 <script.py>
```

### Database Maintenance

#### `count_station_data.py`
Counts records received per station from the `weather_data` hypertable. Deduplicates station IDs across topics. Results are printed and saved to `exports/station_counts_<timestamp>.csv`.

```bash
./venv/bin/python3 count_station_data.py              # all time
./venv/bin/python3 count_station_data.py --days 7     # last 7 days
./venv/bin/python3 count_station_data.py --since 2026-02-01
```

#### `purge_empty_stations.py`
Identifies stations that have no rows in their hypertable and removes them from the metadata tables (`timestream_measurements` → `permissions` → `timestream_tables`) and drops the physical hypertable. Stations listed in `exempt_station_ids.txt` are never removed.

```bash
./venv/bin/python3 purge_empty_stations.py            # dry-run
./venv/bin/python3 purge_empty_stations.py --execute  # apply changes
```

#### `purge_non_exempt_stations.py`
Removes **all** stations whose MQTT topic does not contain a station ID listed in `exempt_station_ids.txt`. Exports a CSV report before applying any changes.

```bash
./venv/bin/python3 purge_non_exempt_stations.py            # dry-run
./venv/bin/python3 purge_non_exempt_stations.py --execute  # apply changes
```

#### `migrate_to_station_ids.py`
One-time migration that populated the `station_id` column on `timestream_tables` by inferring station IDs from topic paths and payload data. Also updated Grafana dashboard SQL to reference the new `station_id`. Safe to re-run — uses dry-run mode by default.

```bash
./venv/bin/python3 migrate_to_station_ids.py            # dry-run
./venv/bin/python3 migrate_to_station_ids.py --execute
```

#### `export_metadata_csv.py`
Dumps all relational metadata tables (`brokers`, `timestream_tables`, `timestream_measurements`, `users`, `groups`, `permissions`) to CSV files in `exports/`.

```bash
./venv/bin/python3 export_metadata_csv.py
```

#### `test_queries.py`
Ad-hoc script for manually verifying raw SQL queries against the database. Not intended for automation.

### Grafana Management

#### `rebuild_dashboards.py`
Iterates every `timestream_table` record and calls Grafana helpers to recreate each dashboard. Use after bulk schema changes or after a Grafana reset.

```bash
./venv/bin/python3 rebuild_dashboards.py
```

#### Grafana snapshot / panel scripts
A collection of scripts used to export or mirror Grafana dashboard state:

| Script                       | Purpose                                                   |
|------------------------------|-----------------------------------------------------------|
| `fetch_dashboards.py`        | Download all dashboard JSON from the Grafana API          |
| `get_dashboards_info.py`     | Fetch dashboard metadata (title, uid, folder)             |
| `format_dashboards_list.py`  | Pretty-print the dashboards list                          |
| `fix_all_dashboards.py`      | Batch-fix SQL or panel config across all dashboards       |
| `create_timescale_dashboard.py` | Create a new dashboard wired to a TimescaleDB datasource |
| `create_live_dashboard.py`   | Create a live-updating dashboard for a topic             |
| `create_live_snapshot.py`    | Produce a shareable snapshot of a live dashboard         |
| `create_static_snapshot.py`  | Produce a static snapshot                                |
| `create_test_snapshot.py`    | Test snapshot generation                                 |
| `create_panels_270.py`       | Build panels for station 270                             |

Output artefacts (`all_dashboards.json`, `dashboards_info.json`, `dashboards_raw.json`, `dashboards_list.txt`, `results.json`) are persisted in the project root after running these scripts.

---

## `wiz2box_forward/` — External Data Forwarding

Scripts that download weather data from EUMETSAT / WIS2BOX and publish it into the local MQTT broker so the subscriber can ingest it.

```
wiz2box_forward/
├── download.py              # Download .dat files from a remote source; report metrics
├── import.py                # Import downloaded data into TimescaleDB directly
├── publish.py               # Re-publish saved .dat files as GeoJSON over MQTT
├── migrate_to_public_schema.py  # One-time: migrate data to the public schema
├── test_dryrun.py           # Dry-run test for import logic
├── test_import_single.py    # Import a single file for testing
├── stations.csv             # Station list with IDs and metadata
└── EUMETSAT/                # Downloaded raw data files (one subdirectory per station)
```

#### `download.py`
Downloads station `.dat` files, reporting download progress to a shared metrics endpoint. Authenticates with basic credentials and saves files to `EUMETSAT/`.

#### `publish.py`
Reads saved `.dat` files and publishes them as GeoJSON messages to the MQTT broker. Supports filtering by station name and time window.

```bash
./venv/bin/python3 wiz2box_forward/publish.py                         # all stations, all time
./venv/bin/python3 wiz2box_forward/publish.py --hours 24              # last 24 hours only
./venv/bin/python3 wiz2box_forward/publish.py --station LusakaAirport # one station
```

#### `import.py`
Imports data directly into TimescaleDB (bypassing MQTT) using `timescaleUtil` from the subscriber package. Useful for backfilling historical data.

---

## `mqtt_subscriber_publisher/` — Test Publisher

A minimal MQTT publisher used during development to inject synthetic or replayed messages into the broker.

```
mqtt_subscriber_publisher/
├── __main__.py   # Publishes test payloads from data.json
├── config.ini    # MQTT broker credentials
└── data.json     # Sample message payload
```

Run with:
```bash
./venv/bin/python3 -m mqtt_subscriber_publisher
```

---

## `backups/` — Database Backups

Point-in-time database dumps. See [backups/README.md](backups/README.md) for restoration instructions.

```
backups/
├── mqtt_dashboard_backup_20260205_192137.dump    # pg_dump custom format
├── mqtt_dashboard_full_backup_20260205_192317.sql # plain SQL backup
├── pre_migration_20260301_234137.dump            # pre-migration snapshot
└── create_complete_backup.sh                     # backup creation script
```

Restore a custom-format dump:
```bash
pg_restore -h localhost -U postgres -d mqtt_dashboard \
  backups/mqtt_dashboard_backup_20260205_192137.dump
```

---

## Supporting Data Files

| File                    | Purpose                                                    |
|-------------------------|------------------------------------------------------------|
| `exempt_station_ids.txt`| Station serial IDs that purge scripts must never delete    |
| `inactiveStations.txt`  | Historical record of stations removed from service         |
| `station_contacts.csv`  | Contact details linked to station IDs                      |
| `requirements.txt`      | Python dependencies for the whole project                  |
