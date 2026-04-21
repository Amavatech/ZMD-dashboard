# Message Processing Pipeline

This document traces the complete path a message takes from arriving at the MQTT broker to being stored in TimescaleDB.

---

## Stage 1: MQTT Receive — `on_message()`

Each broker runs in its own thread. When a message arrives on any subscribed topic, paho-mqtt calls `on_message()`:

```
topic:   "data-incoming/zmb/campbell-v1/LusakaAirport/data"
payload: b'{"type":"FeatureCollection",...}'
```

`on_message()` does **minimal work** to avoid blocking the network thread:
1. Increments the `received_counter` (for stats reporting).
2. Appends `(topic, payload_string)` to the left side of the `message_queue` deque.
3. Returns immediately.

### Queue Design

```python
message_queue = collections.deque(maxlen=1000)
```

- **LIFO (Last-In-First-Out):** Appended to the **left**, also popped from the **left** (`popleft()`). The newest messages are processed first during spikes.
- **Maximum size 1000:** If the queue fills up (subscriber is falling behind), the oldest messages are silently dropped from the right end. This protects memory.
- **Why 1000?** A burst of 1000 messages at once is assumed to be transient. In steady state the queue should be near-empty.

---

## Stage 2: Ingestion Worker — `process_messages()`

A dedicated background thread runs in a loop:

```python
while True:
    if message_queue:
        topic, payload = message_queue.popleft()
        message_to_timescale(topic, payload)
    else:
        time.sleep(0.01)  # 10ms sleep to avoid CPU spin
```

This is single-threaded by design: avoids concurrent writes to the same hypertable and keeps the logic simple. The 10ms sleep burns very little CPU when idle.

---

## Stage 3: `message_to_timescale(topic, payload)`

This is the main ingestion function (~200 lines). It orchestrates all subsequent stages.

### 3a: Payload Parsing

Two payload formats are supported; the function detects which is present:

```python
if "FeatureCollection" in payload or "Feature" in payload:
    records = _parse_geojson(topic, payload)
elif "head" in payload and "data" in payload:
    records = _parse_csijson(topic, payload)
else:
    logger.warning(f"Unknown payload format on {topic}")
    return
```

See [message-formats.md](message-formats.md) for full schema details.

Parsing produces a normalised list of dicts:
```python
[
    {"name": "AirTemp_Avg", "value": 24.3, "unit": "Celsius", "type": "DOUBLE", "time": datetime(...)},
    {"name": "WSpd_Avg",    "value": 3.1,  "unit": "m/s",     "type": "DOUBLE", "time": datetime(...)},
    {"name": "StationName", "value": "Lusaka Airport", "unit": "", "type": "VARCHAR", "time": datetime(...)},
]
```

### 3b: Station ID Resolution

```python
station_id = _infer_station_id(topic, records, payload)
```

A 4-priority algorithm determines the canonical station identifier. See [station-tracking.md](station-tracking.md) for the full algorithm.

### 3c: Metadata Sync (relational tables)

Using `mySqlUtil.py`:

1. **`does_timestream_table_exist(topic)`** — checks if a row exists for this topic in `timestream_tables`.
2. If **new topic:** calls `add_timestream_table(topic, broker_id, station_id, ...)` to create the metadata row.
3. For each measurement name in the records: checks `timestream_measurements`; if new, calls `add_timestream_measurement(name, table_id, unit, type)`.

### 3d: Hypertable Creation

```python
timescaleUtil.create_table(station_id)
```

This calls `CREATE TABLE IF NOT EXISTS public."st_<station_id>" (...)` and then `create_hypertable(...)`. Actually creates the table on first data from a station. The `IF NOT EXISTS` makes it idempotent.

### 3e: Write Time-Series Rows

```python
timescaleUtil.write_records(station_id, records)
timescaleUtil.write_weather_data(station_id, records)
```

**`write_records()`** — INSERT into `public."st_<station_id>"`:
```sql
INSERT INTO public."st_<station_id>"
    (time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
```
Uses `ON CONFLICT DO NOTHING` to safely handle duplicate timestamps for the same sensor.

**`write_weather_data()`** — INSERT into `public.weather_data` (numeric only):
```sql
INSERT INTO public.weather_data (time, station_id, metric, value)
VALUES (%s, %s, %s, %s)
ON CONFLICT DO NOTHING;
```

Both functions use the psycopg2 connection pool: `get_connection()` / `release_connection()` in a `try/finally` block.

### 3f: Grafana Dashboard Creation (first-time only)

If the station is new and Grafana is configured:
```python
grafana_helpers.create_dashboard_table(station_id, measurements, ...)
```

This calls the Grafana HTTP API to create a dashboard with panels for each measurement. If it fails (Grafana down, etc.) the ingestion still succeeds; the dashboard can be created manually later.

---

## Error Handling

| Error | Response |
|-------|----------|
| Malformed JSON | `logger.error(...)`, message dropped |
| Missing required field in payload | `logger.warning(...)`, message dropped |
| TimescaleDB connection failure | psycopg2 connection pool retries; if it fails, the row is lost |
| Grafana API failure | Logged as a warning; ingestion continues uninterrupted |
| Queue overflow (>1000 msgs) | Oldest messages silently evicted from right end of deque |

---

## Counters and Stats

The subscriber maintains two thread-safe counters:

```python
received_counter = 0   # incremented in on_message()
processed_counter = 0  # incremented in message_to_timescale()
```

A background thread (`stats_reporter`) logs both values every 2 minutes:
```
[STATS] Received: 47, Processed: 47 (last 120s)
```

Counters are reset to 0 after each report. If `received` >> `processed`, the processing thread is falling behind.

See [logging.md](logging.md) for the full stats and watchdog system.

---

## Navigation

← [mqtt-ingest/README.md](README.md) | [docs/README.md](../README.md)
