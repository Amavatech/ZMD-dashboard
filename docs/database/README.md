# Database — Overview

**Engine:** PostgreSQL with the TimescaleDB extension  
**Database name:** `mqtt_dashboard`  
**Schema:** `public`  
**Host:** `localhost:5432` (co-located with the application server)

---

## Contents

- [schema.md](schema.md) — All relational tables and columns
- [hypertables.md](hypertables.md) — Time-series hypertables explained
- [connection.md](connection.md) — How to connect, credentials, and psql commands
- [maintenance.md](maintenance.md) — Backups, restore, and migrations

---

## Two Layers in One Database

The `mqtt_dashboard` PostgreSQL database holds two fundamentally different kinds of data:

### 1. Relational Metadata (configuration and access control)

Fixed tables managed by the Flask application. These rarely change and are small in size.

| Table | Rows (approx.) | Purpose |
|-------|---------------|---------|
| `brokers` | 1–20 | MQTT broker connection details |
| `timestream_tables` | 1–500 | One row per weather station / MQTT topic |
| `timestream_measurements` | 10–10,000 | One row per measurable quantity per station |
| `groups` | 1–50 | Named collections of stations |
| `permissions` | 1–1,000 | User access control |
| `users` | 1–100 | Dashboard login accounts |

### 2. Time-Series Data (hypertables)

Dynamically-created tables, one per station, managed by the subscriber. These grow continuously and can become very large.

| Table | Type | Purpose |
|-------|------|---------|
| `st_<station_id>` (e.g. `st_60790`) | TimescaleDB hypertable | All measurements for one station |
| `weather_data` | TimescaleDB hypertable | Unified cross-station numeric values |

---

## TimescaleDB Extension

TimescaleDB adds time-series superpowers to PostgreSQL:

- **Hypertables:** Automatically partition large time-series tables into time-based chunks for fast range queries.
- **Continuous aggregates:** Pre-computed rollups (not currently used but available).
- **Compression:** Older chunks can be compressed.
- **Retention policies:** Auto-drop old data (not currently configured).

The extension must be installed and enabled. The subscriber creates it automatically if missing:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

Check it is installed:
```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
```

---

## Key Principles for Maintainers

1. **Never drop a hypertable manually without also removing the `timestream_tables` row.** The relational row and the physical table must stay in sync. Use `purge_empty_stations.py` for safe cleanup.

2. **Both the Flask app and the subscriber write to the same database.** The Flask app only writes to the relational metadata tables (via Flask-SQLAlchemy). The subscriber writes to both relational (new topics/measurements) and hypertables (time-series rows).

3. **The `search_path` is always set to `public`.** Both application connection strings include `options=-csearch_path=public` or similar. All objects live in `public` schema.

4. **`station_id` is the canonical station identifier.** The hypertable for a station is named `st_<station_id>`. The `timestream_tables.station_id` column is the link between the relational row and the physical hypertable.

---

## Navigation

← [docs/README.md](../README.md)
