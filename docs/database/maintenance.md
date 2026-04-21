# Database Maintenance — Backups, Restore & Migrations

---

## Backups

Pre-made backups are stored in `backups/`. See `backups/README.md` for details on each file.

| File | Format | Date | Notes |
|------|--------|------|-------|
| `mqtt_dashboard_backup_20260205_192137.dump` | pg_dump custom | 2026-02-05 | Recommended for restore |
| `mqtt_dashboard_full_backup_20260205_192317.sql` | Plain SQL | 2026-02-05 | Human-readable |
| `pre_migration_20260301_234137.dump` | pg_dump custom | 2026-03-01 | Pre-station_id migration snapshot |

---

## Creating a New Backup

### Option 1 — Custom format (recommended for restore)
```bash
pg_dump -h localhost -U postgres -Fc mqtt_dashboard \
  > backups/mqtt_dashboard_$(date +%Y%m%d_%H%M%S).dump
```

### Option 2 — Plain SQL (human-readable, useful for auditing)
```bash
PGPASSWORD=campDashSQL pg_dump -h localhost -U postgres \
  --no-owner --no-privileges mqtt_dashboard \
  > backups/mqtt_dashboard_full_$(date +%Y%m%d_%H%M%S).sql
```

### Automated backup script
```bash
./backups/create_complete_backup.sh
```

---

## Restoring from Backup

> **Warning:** Restoring from a dump will overwrite existing data. Stop both services first.

```bash
sudo systemctl stop mqtt_dashboard mqtt_subscriber

# Drop and recreate the database
PGPASSWORD=campDashSQL psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS mqtt_dashboard;"
PGPASSWORD=campDashSQL psql -h localhost -U postgres -c "CREATE DATABASE mqtt_dashboard;"

# Restore
PGPASSWORD=campDashSQL pg_restore -h localhost -U postgres \
  -d mqtt_dashboard --no-owner \
  backups/mqtt_dashboard_backup_20260205_192137.dump

sudo systemctl start mqtt_dashboard mqtt_subscriber
```

If restoring from a plain SQL file:
```bash
PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard \
  < backups/mqtt_dashboard_full_backup_20260205_192317.sql
```

---

## Schema Migrations

The application does not use a formal migration tool (like Alembic). Schema changes are applied manually via psql or via migration scripts in the project root.

### Significant Migration: `station_id` column (`2026-03-01`)

A `station_id` column was added to `timestream_tables`. The physical TimescaleDB hypertables were also renamed from topic-based names to `st_<station_id>` format.

**Migration script:** `migrate_to_station_ids.py`  
See [utilities/database-maintenance.md](../utilities/database-maintenance.md) for details.

**Snapshot before migration:** `backups/pre_migration_20260301_234137.dump`

### Adding a Column Manually

```sql
-- Example: add a column to timestream_tables
ALTER TABLE timestream_tables ADD COLUMN IF NOT EXISTS new_column TEXT;
```

### Current Schema Version

There is no version table. The current schema is defined implicitly by the SQLAlchemy model classes in `mqtt_dashboard/models.py` and `mqtt_subscriber_timestream_output/mySqlUtil.py`. Compare these against the live database to detect drift:

```sql
-- Check all columns on timestream_tables
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'timestream_tables'
ORDER BY ordinal_position;
```

---

## Purging Unused Stations

Over time, stations may send data once and then go offline permanently. Their hypertables accumulate empty storage. Use the purge scripts to clean up:

```bash
# Remove stations with no data (dry-run first)
./venv/bin/python3 purge_empty_stations.py
./venv/bin/python3 purge_empty_stations.py --execute

# Remove all non-exempt stations (drastic — read docs first)
./venv/bin/python3 purge_non_exempt_stations.py
./venv/bin/python3 purge_non_exempt_stations.py --execute
```

See [utilities/database-maintenance.md](../utilities/database-maintenance.md) for full documentation on these scripts.

---

## Checking Database Size

```sql
-- Total database size
SELECT pg_size_pretty(pg_database_size('mqtt_dashboard'));

-- Size of each hypertable
SELECT
    hypertable_name,
    pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass)) AS total_size
FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'public'
ORDER BY hypertable_size(format('%I', hypertable_name)::regclass) DESC;

-- Top 10 largest tables
SELECT
    table_name,
    pg_size_pretty(pg_total_relation_size('public.' || table_name)) AS size
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY pg_total_relation_size('public.' || table_name) DESC
LIMIT 10;
```

---

## Enabling TimescaleDB Compression (Optional)

For very large hypertables, compression can reduce storage significantly:

```sql
-- Enable compression on a hypertable (compress chunks older than 7 days)
ALTER TABLE public.weather_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'station_id'
);

SELECT add_compression_policy('public.weather_data', INTERVAL '7 days');
```

> Compression is not currently enabled. Enabling it requires testing with the current query patterns to ensure no compatibility issues.

---

## Navigation

← [database/README.md](README.md) | [docs/README.md](../README.md)
