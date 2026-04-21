# TimescaleDB Hypertables

This document explains how time-series data is stored in the `mqtt_dashboard` database.

---

## What Is a Hypertable?

A TimescaleDB hypertable is a regular PostgreSQL table that is automatically partitioned into time-based "chunks". From the application's point of view it behaves like a normal table — you INSERT and SELECT from it normally. Under the hood, TimescaleDB routes data to the appropriate chunk based on the timestamp, making time-range queries orders of magnitude faster on large datasets.

Every `INSERT` goes to the chunk covering the current time window. Queries like `WHERE time > NOW() - INTERVAL '24 hours'` only scan recent chunks.

---

## Per-Station Hypertables (`st_<station_id>`)

### Naming Convention

Each weather station gets its own hypertable:

```
MQTT topic:   data-incoming/zmb/campbell-v1/0-894-2-LusakaAirport/data
station_id:   LusakaAirport
Hypertable:   public.st_LusakaAirport

MQTT topic:   something/60790/data
station_id:   60790
Hypertable:   public.st_60790
```

The name is determined by `station_id` on the `timestream_tables` row, **not** from the raw topic string directly.

> **PostgreSQL identifier limit:** Table names are truncated to 63 characters. `timescaleUtil._normalize_table_name()` enforces this. Long station IDs will be truncated at 63 chars minus the `st_` prefix (effectively 60 chars total).

### Schema

```sql
CREATE TABLE public.st_<station_id> (
    time                  TIMESTAMPTZ      NOT NULL,
    measure_name          TEXT             NOT NULL,  -- e.g. "AirTemp_Avg"
    measure_value_double  DOUBLE PRECISION NULL,      -- for numeric sensors
    measure_value_varchar TEXT             NULL,       -- for string sensors
    unit                  TEXT             NULL,       -- e.g. "Celsius"
    measurement_type      TEXT             NULL        -- "DOUBLE" or "VARCHAR"
);

SELECT create_hypertable('public.st_<station_id>', 'time', if_not_exists => TRUE);

CREATE INDEX st_<station_id>_measure_time_idx
    ON public.st_<station_id> (measure_name, time DESC);
```

### Columns Explained

| Column | Purpose |
|--------|---------|
| `time` | UTC timestamp of the measurement. All timestamps are normalised to UTC regardless of source timezone. |
| `measure_name` | Sensor/field name exactly as received in the MQTT payload (e.g. `AirTemp_Avg`, `WSpd_Max`, `QFE_Avg`). |
| `measure_value_double` | Numeric value, NULL for string sensors. |
| `measure_value_varchar` | String value, NULL for numeric sensors. |
| `unit` | Unit string as received (e.g. `Celsius`, `%`, `hPa`, or `unitless`). |
| `measurement_type` | Redundant with the NULL pattern but stored explicitly: `"DOUBLE"` or `"VARCHAR"`. |

### One Row Per Measurement Per Timestamp

There is **one row per measurement name per timestamp**. A station sending 20 sensor values at 10:00 UTC produces 20 rows all with `time = 2026-04-17T10:00:00+00`.

To query the latest temperature:
```sql
SELECT time, measure_value_double AS temperature
FROM public."st_LusakaAirport"
WHERE measure_name = 'AirTemp_Avg'
ORDER BY time DESC
LIMIT 1;
```

To query all sensors at last contact:
```sql
SELECT DISTINCT ON (measure_name)
    time, measure_name,
    COALESCE(measure_value_double::text, measure_value_varchar) AS value
FROM public."st_LusakaAirport"
ORDER BY measure_name, time DESC;
```

---

## Unified Weather Data Hypertable (`weather_data`)

### Purpose

A single table accumulating *numeric* readings from all stations. Designed for:
- Cross-station comparison queries
- Fallback when a per-station table does not exist
- Grafana queries that need multi-station data

### Schema

```sql
CREATE TABLE public.weather_data (
    time       TIMESTAMPTZ      NOT NULL,
    station_id TEXT             NOT NULL,  -- e.g. "LusakaAirport"
    metric     TEXT             NOT NULL,  -- e.g. "AirTemp_Avg"
    value      DOUBLE PRECISION NULL        -- numeric only; VARCHAR values are excluded
);

SELECT create_hypertable('public.weather_data', 'time', if_not_exists => TRUE);

CREATE INDEX weather_data_station_metric_time_idx
    ON public.weather_data (station_id, metric, time DESC);
```

### Key Differences from Per-Station Tables

- Only numeric (`DOUBLE`) values are written; string measurements are silently dropped.
- `station_id` travels with every row, enabling cross-station JOINs.
- Has no `unit` or `measurement_type` columns.

### Fallback Behaviour

When the Flask API can't find a per-station hypertable for a requested `table_name`, it falls back to `weather_data`:

```sql
SELECT time, metric AS measure_name, value::text AS value
FROM public.weather_data
WHERE station_id = :station_id
ORDER BY time DESC
LIMIT 8;
```

---

## Hypertable Management

### List all hypertables
```sql
SELECT hypertable_name, num_chunks, compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'public'
ORDER BY hypertable_name;
```

### Check chunk count and data range for a station
```sql
SELECT
    c.chunk_name,
    c.range_start,
    c.range_end,
    pg_size_pretty(pg_total_relation_size(c.chunk_schema || '.' || c.chunk_name)) AS chunk_size
FROM timescaledb_information.chunks c
WHERE c.hypertable_name = 'st_60790'
ORDER BY c.range_start;
```

### Count rows across all per-station hypertables
```sql
SELECT
    t.station_id,
    t.topic,
    (SELECT COUNT(*) FROM public."st_" || t.station_id) AS row_count
FROM timestream_tables t;
-- Note: the above is pseudocode; use count_station_data.py for the real query
```

Use `count_station_data.py` in the project root for a proper cross-station count (see [utilities/database-maintenance.md](../utilities/database-maintenance.md)).

### Check the most recent data for a station
```sql
SELECT MAX(time) AS last_seen
FROM public."st_LusakaAirport";
```

### Drop an empty hypertable (after removing the metadata row)
```sql
DROP TABLE IF EXISTS public."st_OldStation";
```

> Always remove the `timestream_tables` row first. Use `purge_empty_stations.py` for safe automated cleanup.

---

## Timestamp Handling

All timestamps are stored as `TIMESTAMPTZ` (timestamp with time zone) in UTC. The subscriber normalises:
1. Parses the ISO 8601 string from the payload using `dateutil.parser.isoparse()`.
2. Converts to UTC: `.astimezone(pytz.UTC)`.
3. Stores as a Python `datetime` object.

If `UseCurrentTimeAsTimestamp=True` in `config.ini`, the server clock is used instead of the payload timestamp. This is useful when station clocks drift or are unreliable.

---

## Navigation

← [database/README.md](README.md) | [docs/README.md](../README.md)
