# Database Maintenance Scripts

---

## `purge_empty_stations.py`

**Purpose:** Identifies and removes stations that have never sent any data.

A station is considered empty when its physical hypertable either does not exist or contains zero rows.

### Safe by Default

The script is **dry-run by default** — it reports what it would delete without making any changes.

```bash
# See what would be deleted (safe to run any time)
python3 purge_empty_stations.py

# Actually delete empty stations
python3 purge_empty_stations.py --execute
```

### What It Deletes

In `--execute` mode, for each TO-PURGE station:
1. Deletes all `timestream_measurements` rows linked to that station.
2. Deletes all `permissions` rows linked to that station.
3. Deletes the `timestream_tables` row.
4. Drops the physical hypertable (`DROP TABLE IF EXISTS public."st_<station_id>"`).

### Exemption

Stations listed in `exempt_station_ids.txt` are never deleted, even if they have no data. Always review the exemption file before running.

### Output

A CSV report is saved to `exports/empty_stations_<timestamp>.csv` with columns:
```
tableid, topic, station_id, brokerid, hypertable_exists, row_count
```

---

## `purge_non_exempt_stations.py`

**Purpose:** Removes **all** stations that are NOT listed in `exempt_station_ids.txt`.

> **Warning: Destructive.** This script deletes stations regardless of whether they have data. Use only when you know exactly which stations to keep. All stations you want to keep MUST be in `exempt_station_ids.txt` before running.

```bash
# See what would be deleted (safe to run any time)
python3 purge_non_exempt_stations.py

# Actually delete all non-exempt stations
python3 purge_non_exempt_stations.py --execute
```

### Use Case

This was used to clean up the database after discovering hundreds of test/development stations had been auto-created during subscriber development. The legitimate production stations were added to `exempt_station_ids.txt` first, then the script was run to remove everything else.

### Output

A CSV report is saved to `exports/non_exempt_stations_<timestamp>.csv`.

---

## `count_station_data.py`

**Purpose:** Counts and summarises how much data each station has transmitted.

```bash
# All time
python3 count_station_data.py

# Last 7 days
python3 count_station_data.py --days 7

# Since a specific date
python3 count_station_data.py --since 2026-02-01
```

### Output Format

Printed to terminal and also saved to `exports/station_counts_<timestamp>.csv`:

```
station_id          | transmissions | first_seen          | last_seen
--------------------+---------------+---------------------+--------------------
LusakaAirport       |           847 | 2026-01-15 08:00:00 | 2026-04-17 09:00:00
KitweStation        |           312 | 2026-02-01 10:00:00 | 2026-04-17 08:00:00
```

**Transmissions** = distinct timestamps in `weather_data` for that station (not total rows). This counts message batches rather than individual sensor readings.

### Exemption Markers

Stations in `exempt_station_ids.txt` are marked with `[EXEMPT]` in the output so you can see which ones are protected.

---

## `export_metadata_csv.py`

**Purpose:** Exports all relational tables to CSV files in `exports/`.

```bash
python3 export_metadata_csv.py
```

Tables exported:
- `brokers`
- `timestream_tables`
- `timestream_measurements`
- `users`
- `groups`
- `permissions`

Each is saved as `exports/<table_name>_<timestamp>.csv`.

**Use case:** Creating a portable snapshot of configuration for review, sharing with a colleague, or as a lightweight backup of metadata only (not time-series data).

---

## `migrate_to_station_ids.py`

**Purpose:** One-time migration script adding the `station_id` column to `timestream_tables` and renaming hypertables from topic-based names to `st_<station_id>` format.

> **Already been run on 2026-03-01.** Do not run this again unless you are setting up a fresh database.

**Pre-migration snapshot:** `backups/pre_migration_20260301_234137.dump`

### What It Did

1. Added `station_id VARCHAR(64)` column to `timestream_tables`.
2. For each existing station, inferred `station_id` from the MQTT topic.
3. Updated `station_id` on each `timestream_tables` row.
4. Renamed each physical hypertable from the old topic-derived name to `st_<station_id>`.

If you need to add new stations manually (without the subscriber auto-creating them), mimic this process by setting `station_id` when inserting the `timestream_tables` row.

---

## `exports/` Folder

All utility scripts write their output to `exports/`. This folder is not cleaned automatically — old exports accumulate. Periodically review and purge old export files:

```bash
ls -lt exports/ | head -20      # most recent first
find exports/ -mtime +30 -name "*.csv" -delete   # delete CSVs older than 30 days
```

---

## Navigation

← [utilities/README.md](README.md) | [docs/README.md](../README.md)
