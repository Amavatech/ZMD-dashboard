# MQTT to TimescaleDB Data Pipeline

A comprehensive MQTT subscriber service that ingests weather and sensor data from multiple MQTT brokers and stores it in TimescaleDB for time-series analysis and Grafana visualization.

## Table of Contents
- [Overview](#overview)
- [Data Pipeline Architecture](#data-pipeline-architecture)
- [Database Interactions](#database-interactions)
- [Data Truncation & Normalization](#data-truncation--normalization)
- [Function Reference](#function-reference)
- [Configuration](#configuration)
- [Logging System](#logging-system)

---

## Overview

This service continuously monitors MQTT brokers for weather/sensor data messages, processes them in two supported formats (GeoJSON and CSIJSON), and persists them to TimescaleDB. It automatically manages database schemas, creates Grafana dashboards, and handles multi-broker configurations with automatic reconnection.

**Key Features:**
- Multi-broker MQTT subscription with auto-reconnection
- Dual-database architecture (TimescaleDB for time-series + PostgreSQL for metadata)
- Auto-discovery of new measurements and dynamic schema creation
- Automatic Grafana dashboard generation
- Asynchronous message processing with queue management
- Timezone-aware timestamp handling (UTC normalization)
- Comprehensive logging with hourly rotation

---

## Data Pipeline Architecture

### High-Level Flow

```
MQTT Brokers → Message Queue → Processing Worker → Dual Database Write → Grafana Integration
```

### Detailed Pipeline Stages

#### 1. MQTT Connection Layer
- **Multi-broker support**: Connects to all brokers configured in the `brokers` table
- **Fallback to config.ini**: If no brokers exist in DB, uses config.ini settings
- **Auto-reconnection**: Each broker runs in a separate thread with exponential backoff (1-12s delays)
- **Universal subscription**: Subscribe to all topics using `#` wildcard
- **Authentication**: Supports username/password authentication per broker

#### 2. Message Reception & Queuing
- **Queue type**: LIFO (Last-In-First-Out) queue with max 1000 messages
- **Overflow handling**: When full, discards oldest message and adds new one
- **Async processing**: Separate worker thread processes queued messages
- **Topic filtering**: 
  - Ignores `state/` topics
  - Filters out hourly data (listens for 5/10 minute intervals)
  - Strips format suffixes (`/cj`, `/5_min`, `/Table10m`)

#### 3. Message Format Detection & Parsing

**Format A: GeoJSON**
```json
{
  "geometry": {
    "coordinates": [longitude, latitude]
  },
  "properties": {
    "observationNames": ["Temp", "Humidity", ...],
    "observationUnits": ["C", "%", ...],
    "observations": {
      "2026-02-18T10:30:00Z": [23.5, 65.2, ...]
    }
  }
}
```

**Format B: CSIJSON (Campbell Scientific)**
```json
{
  "head": {
    "fields": [
      {"name": "Temp", "units": "C"},
      {"name": "Humidity", "units": "%"}
    ]
  },
  "data": [
    {
      "time": "2026-02-18T10:30:00Z",
      "vals": [23.5, 65.2]
    }
  ]
}
```

#### 4. Data Processing & Transformation

**Station ID Inference:**
1. Check payload for `Station_Name` or `Station_ID` in observations
2. Fallback: Extract from topic path (rightmost non-generic component)
3. Default: Use topic name or "unknown"

**Timestamp Handling:**
- **Config option**: `UseCurrentTimeAsTimestamp` in config.ini
  - `True`: Use server time (UTC)
  - `False`: Use timestamp from payload
- **Normalization**: All times converted to UTC regardless of source
- **Storage format**: Unix timestamp in milliseconds

**Data Type Detection:**
- **DOUBLE**: Numeric values (stored in `measure_value_double`)
- **VARCHAR**: String values (stored in `measure_value_varchar`)
- Auto-detected per measurement based on payload content

#### 5. Database Write Operations

**Dual Write Strategy:**
1. **Per-topic tables** (e.g., `weather_station_233`): Original format preservation
2. **Unified weather_data table**: Normalized cross-station analysis

**Write sequence:**
```
1. Check if topic table exists → Create if missing
2. Check if measurements exist → Add to metadata if new
3. Write to topic-specific TimescaleDB table
4. Write to unified weather_data table
5. Update coordinates if changed
6. Create/update Grafana dashboard if schema changed
7. Commit metadata transaction
```

---

## Database Interactions

### Database Architecture

The service uses a **dual-database strategy**:

1. **TimescaleDB** (Time-series data storage)
   - Per-topic hypertables
   - Unified weather_data hypertable
   - Automatic partitioning by time

2. **PostgreSQL** (Metadata & configuration)
   - Topic registry
   - Measurement definitions
   - Broker configurations
   - Grafana dashboard mappings

### TimescaleDB Schema

#### Per-Topic Tables
**Naming convention**: Topic path with `/` replaced by `_`

Example: Topic `weather/station/233` → Table `weather_station_233`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS public.<topic_name> (
    time TIMESTAMPTZ NOT NULL,              -- Measurement timestamp
    measure_name TEXT NOT NULL,              -- Measurement name (e.g., "Temperature")
    measure_value_double DOUBLE PRECISION,   -- Numeric value
    measure_value_varchar TEXT,              -- String value
    unit TEXT,                               -- Unit of measurement
    measurement_type TEXT                    -- Data type (DOUBLE/VARCHAR)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('<topic_name>', 'time', if_not_exists => TRUE);

-- Index for efficient queries
CREATE INDEX <topic_name>_measure_time_idx 
ON <topic_name> (measure_name, time DESC);
```

**Hypertable benefits:**
- Automatic time-based partitioning (chunks)
- Compression support
- Continuous aggregates
- Fast time-range queries

#### Unified Weather Data Table
**Purpose**: Cross-station queries and analysis

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS public.weather_data (
    time TIMESTAMPTZ NOT NULL,        -- Measurement timestamp
    station_id TEXT NOT NULL,         -- Station identifier
    metric TEXT NOT NULL,             -- Measurement name
    value DOUBLE PRECISION            -- Numeric value only
);

SELECT create_hypertable('weather_data', 'time', if_not_exists => TRUE);

CREATE INDEX weather_data_station_metric_time_idx 
ON weather_data (station_id, metric, time DESC);
```

**Key differences from per-topic tables:**
- Only stores DOUBLE values (filters out VARCHAR)
- Includes station_id for cross-station queries
- Denormalized for query performance

### PostgreSQL Metadata Schema

#### Table: `brokers`
**Purpose**: MQTT broker connection details

```sql
CREATE TABLE brokers (
    brokerid SERIAL PRIMARY KEY,
    url VARCHAR(100),                 -- Broker hostname/IP
    port INTEGER,                     -- MQTT port
    authentication BOOLEAN DEFAULT TRUE,
    username VARCHAR(100),
    password VARCHAR(100),
    name VARCHAR(100)                 -- Friendly name
);
```

#### Table: `timestream_tables`
**Purpose**: Topic registry and metadata

```sql
CREATE TABLE timestream_tables (
    tableid SERIAL PRIMARY KEY,
    brokerid INTEGER REFERENCES brokers(brokerid),
    topic VARCHAR(255) UNIQUE,        -- MQTT topic path
    db_uid VARCHAR(15),               -- Grafana database UID
    ss_key VARCHAR(32),               -- Additional identifier
    longitude FLOAT,                  -- Station location
    latitude FLOAT,
    groupid INTEGER
);
```

#### Table: `timestream_measurements`
**Purpose**: Measurement definitions per topic

```sql
CREATE TABLE timestream_measurements (
    measurementid SERIAL PRIMARY KEY,
    name VARCHAR(255),                -- Measurement name
    directionname VARCHAR(255),       -- Optional wind direction
    tableid INTEGER REFERENCES timestream_tables(tableid),
    unit VARCHAR(255) DEFAULT 'unitless',
    nickname VARCHAR(100),            -- Display name
    type VARCHAR(10) DEFAULT 'DOUBLE', -- DOUBLE or VARCHAR
    visible INTEGER DEFAULT 1,        -- Show in dashboard
    status INTEGER DEFAULT 0,         -- State tracking
    graph VARCHAR(10) DEFAULT 'LINE'  -- Graph type
);
```

### Database Operations

#### Connection Management
- **Connection pooling**: SimpleConnectionPool (1-10 connections)
- **Schema enforcement**: `search_path=public` set on every connection
- **Auto-reconnect**: Session restart on connection loss
- **Separate admin connection**: For database creation operations

#### Transaction Handling
- **Metadata commits**: Only when schema changes occur (new topic/measurement)
- **Data writes**: Auto-commit for time-series inserts
- **Rollback protection**: IntegrityError handling for duplicate entries
- **Error recovery**: Session restart on SQLAlchemy errors

#### Write Performance Optimizations
- **Batch inserts**: `execute_values()` for multi-row inserts
- **Connection reuse**: Pooled connections
- **Index strategy**: Covering indexes on (measure_name, time)
- **Minimal commits**: Metadata commits only on schema changes

---

## Data Truncation & Normalization

### Table Name Truncation

**Location**: `timescaleUtil._normalize_table_name()`

**Rules:**
- Convert to lowercase
- Replace hyphens (`-`) with underscores (`_`)
- **Truncate to 63 characters** (PostgreSQL identifier limit)
- Log warning if truncation occurs

**Example:**
```python
Input:  "weather/very-long-station-name-that-exceeds-the-postgresql-limit-significantly"
Output: "weather_very_long_station_name_that_exceeds_the_postgresql_lim"
```

### Topic Path Normalization

**Location**: `__main__.message_to_timescale()`

**Transformations:**
1. Strip leading slash: `/weather/station` → `weather/station`
2. Strip trailing slash: `weather/station/` → `weather/station`
3. Remove time interval suffixes: `weather/station/5_min` → `weather/station`
4. Remove format suffixes: `weather/station/data/cj` → `weather/station`

### Measurement Name Handling

**No truncation applied** - Full measurement names preserved

**Character restrictions:** None applied (PostgreSQL TEXT type)

**Case sensitivity:** Preserved as received from payload

### Unit Standardization

**Default value**: `"unitless"` when:
- No `observationUnits` field in GeoJSON
- No `units` field in CSIJSON
- Empty string provided

**No other normalization** - Units stored exactly as received

### Value Conversions

#### Numeric Values (DOUBLE)
- **Storage**: `measure_value_double` column (DOUBLE PRECISION)
- **Conversion**: Python `float()` cast
- **NULL handling**: Failed conversions → `measure_value_varchar`
- **NAN handling**: Payload preprocessing replaces `,NAN` → `,null`

#### String Values (VARCHAR)
- **Storage**: `measure_value_varchar` column (TEXT)
- **Conversion**: Python `str()` cast
- **Empty values**: Converted to `'0'`

### Timestamp Normalization

**Critical behavior**: All timestamps normalized to UTC

**Process:**
1. Parse timestamp (if from payload): `dateutil.parser.isoparse()`
2. Convert to UTC: `.astimezone(pytz.UTC)`
3. Get Unix timestamp: `int(dt.timestamp())`
4. Convert to milliseconds: `timestamp * 1000`
5. Store as string: `str(timestamp_ms)`

**Server time fallback:**
```python
if config.timescale.use_current_time:
    dt = datetime.datetime.now(datetime.timezone.utc)
else:
    dt = parser.isoparse(cur_time).astimezone(pytz.UTC)
```

### Coordinate Precision

**Storage type**: FLOAT (PostgreSQL)

**Extraction from GeoJSON:**
```python
longitude = payload["geometry"]["coordinates"][1]  # Second element
latitude = payload["geometry"]["coordinates"][0]   # First element
```

**Default values**: `0.0` if missing or error

**No rounding applied** - Full precision preserved

---

## Function Reference

### Core Entry Point

#### `message_to_timescale(msg, brokerID=1)`
Main message processing function.

**Parameters:**
- `msg`: MQTT message object with `.payload` and `.topic`
- `brokerID`: Integer identifier for source broker

**Process:**
1. Decode and parse JSON payload
2. Detect format (GeoJSON vs CSIJSON)
3. Normalize topic path
4. Filter state messages
5. Extract coordinates (if GeoJSON)
6. Process all timepoints in message
7. Write to TimescaleDB (both tables)
8. Update metadata if schema changed
9. Trigger Grafana dashboard update

**Error handling:**
- JSON parse errors: Log and return
- Database errors: Log exception, restart session, continue
- Grafana errors: Log warning, continue without dashboard update

**Returns:** None

---

### MQTT Connection Functions

#### `Connect(client, broker, port, keepalive, run_forever=False)`
Establish connection with retry logic.

**Parameters:**
- `client`: Paho MQTT client instance
- `broker`: Broker hostname/IP
- `port`: MQTT port number
- `keepalive`: Seconds between keepalive packets
- `run_forever`: If True, retry indefinitely; if False, max 15 attempts

**Retry behavior:**
- Initial delay: 5 seconds
- Max attempts: 15 (unless `run_forever=True`)
- Sets `client.badconnection_flag` on failure

**Returns:**
- `0`: Success
- `-1`: All retries exhausted

---

#### `wait_for(client, msgType, period=1, wait_time=10, running_loop=False)`
Wait for specific MQTT event.

**Parameters:**
- `client`: MQTT client instance
- `msgType`: Event type (`"CONNACK"`, `"SUBACK"`, `"MESSAGE"`, `"PUBACK"`)
- `period`: Seconds between checks
- `wait_time`: Maximum wait iterations
- `running_loop`: Whether loop_start/forever is active

**Process:**
- Polls for event flag every `period` seconds
- Manually calls `client.loop()` if not running background loop
- Timeout after `period * wait_time` seconds

**Returns:**
- `True`: Event received
- `False`: Timeout or bad connection

---

#### `client_loop(client, broker, port, keepalive=60, loop_function=None, loop_delay=1, run_forever=False)`
Main broker connection loop (runs per thread).

**Parameters:**
- `client`: MQTT client instance
- `broker`: Broker hostname
- `port`: MQTT port
- `keepalive`: Keepalive interval
- `loop_function`: Optional callback function
- `loop_delay`: Callback interval
- `run_forever`: Infinite retry flag

**Lifecycle:**
1. Set reconnect delay range (1-12 seconds)
2. Connection attempt loop
3. Wait for CONNACK
4. Run `client.loop(1)` continuously
5. Call `loop_function` if provided
6. Auto-reconnect on disconnect
7. Clean disconnect on `client.run_flag=False`

**Thread safety:** Each broker runs in separate thread

---

### Data Processing Functions

#### `_infer_station_id(payload: dict, topic: str) -> str`
Extract station identifier from payload or topic.

**Strategy (priority order):**
1. Check `properties.observations.<time>` for `Station_Name` value
2. Check `properties.observations.<time>` for `Station_ID` value
3. Parse topic path - use rightmost non-generic component
4. Return topic or `"unknown"`

**Generic terms filtered**: `data`, `cr1000x`, `synop`

**Example:**
```python
Topic: "weather/station/233/data"
Result: "233"

Topic: "weather/unknown_format"
Result: "weather/unknown_format"
```

---

### Message Queue Functions

#### `message_worker()`
Worker thread for processing queued messages.

**Behavior:**
- Infinite loop with 1-second timeout
- Pulls from `message_queue` (LIFO)
- Calls `message_to_timescale()` for each message
- Marks task as done for queue tracking

**Thread type:** Daemon thread (exits when main thread exits)

---

#### `on_message(client, userdata, msg)`
MQTT callback for received messages.

**Process:**
1. Attempt to add message to queue (`put_nowait`)
2. If queue full:
   - Remove oldest message (`get_nowait`)
   - Add new message
   - Silently discard on race condition

**Queue item structure:**
```python
{
    "msg": mqtt.MQTTMessage,
    "brokerID": int
}
```

---

### MQTT Callbacks

#### `on_connect(client, userdata, flags, rc)`
Connection acknowledgment callback.

**Response codes:**
- `rc=0`: Success → Subscribe to `#` (all topics)
- `rc≠0`: Error → Stop client loop

**Side effects:**
- Sets `client.connected_flag = True`
- Logs connection status

---

#### `on_subscribe(client, userdata, mid, granted_qos)`
Subscription confirmation callback.

**Action:** Log subscription confirmation

---

### Database Functions (mySqlUtil.py)

#### `get_all_brokers() -> List[broker]`
Retrieve all broker configurations.

**Query:** `SELECT * FROM brokers`

**Returns:** List of `broker` ORM objects

---

#### `get_broker_by_id(brokerID: int) -> broker`
Get specific broker by ID.

**Query:** `SELECT * FROM brokers WHERE brokerid = ?`

**Returns:** Single `broker` object or `None`

---

#### `get_broker_by_url_port(url: str, port: int) -> broker`
Find broker by connection details.

**Query:** `SELECT * FROM brokers WHERE url = ? AND port = ?`

**Returns:** Existing `broker` or `None`

---

#### `add_broker_record(...) -> broker`
Create new broker entry.

**Parameters:**
- `url`, `port`, `authentication`, `username`, `password`, `name`

**Behavior:**
- Check for existing broker (duplicate prevention)
- Insert new record
- Auto-commit transaction

**Returns:** Broker object (new or existing)

---

#### `get_timestream_table(tblName: str) -> timestream_table`
Retrieve topic metadata.

**Normalization:**
- Strip leading slash
- Strip trailing slash

**Query:** `SELECT * FROM timestream_tables WHERE topic = ?`

**Returns:** `timestream_table` object or `None`

---

#### `get_timestream_tables_substring(subStr: str) -> List[timestream_table]`
Find topics matching substring.

**Query:** `SELECT * FROM timestream_tables WHERE topic LIKE %?%`

**Use case:** State message processing (finding related topics)

---

#### `does_timestream_table_exist(tblName: str) -> bool`
Check if topic registered.

**Query:** `SELECT COUNT(*) FROM timestream_tables WHERE topic = ?`

**Returns:** `True` if count > 0

---

#### `does_timestream_measurement_exist(tblName: str, measurement: str) -> bool`
Check if measurement exists for topic.

**Process:**
1. Verify topic exists
2. Get topic tableID
3. Query measurements for tableID + name

**Returns:** `True` if found

---

#### `add_timestream_table(tblName: str, brokerID=1, commit=True)`
Register new topic.

**Fields:**
- `topic`, `brokerID`
- Default: `db_uid=""`, `longitude=0`, `latitude=0`

**Error handling:** Catches IntegrityError (duplicate), performs rollback

---

#### `add_timestream_measurement(tblName, name, unit, type, commit, status)`
Register new measurement.

**Parameters:**
- `tblName`: Topic name
- `name`: Measurement name
- `unit`: Unit of measure (default `"unitless"`)
- `type`: Data type (`"DOUBLE"` or `"VARCHAR"`)
- `commit`: Whether to commit transaction
- `status`: State flag (converted to 0/1)

**Prerequisites:** Topic must exist

**Behavior:** Inserts into `timestream_measurements` with defaults

---

#### `create_dashboard_table(table: timestream_table)`
Trigger Grafana dashboard creation.

**Delegation:** Calls `grafana_helpers.create_dashboard_table()`

**Purpose:** Generate dashboard JSON from measurements

---

#### `restart_session()`
Recover from database connection errors.

**Process:**
1. Close current session
2. Create new session from Session factory
3. Retry until successful

**Use case:** Connection timeouts, authentication errors

---

### TimescaleDB Functions (timescaleUtil.py)

#### `ensure_database()`
Create TimescaleDB database if missing.

**Connection:** Uses `admin_database` (typically `postgres`)

**Query:**
```sql
SELECT 1 FROM pg_database WHERE datname = ?
CREATE DATABASE <database_name> -- if not exists
```

**Error handling:** Logs warning, continues

---

#### `ensure_extension()`
Enable TimescaleDB extension.

**Query:**
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

**Required:** TimescaleDB package installed

---

#### `create_table(dbName: str, tblName: str)`
Create hypertable for topic.

**Process:**
1. Ensure database and extension exist
2. Normalize table name (lowercase, truncate)
3. Create table with schema
4. Convert to hypertable
5. Create covering index

**Table schema:** See [TimescaleDB Schema](#timescaledb-schema)

**Idempotent:** `IF NOT EXISTS` clauses

---

#### `ensure_weather_data_table(schema: str = None)`
Create unified weather_data hypertable.

**Process:**
1. Create table (if not exists)
2. Convert to hypertable
3. Create composite index

**Schema:** See [Unified Weather Data Table](#unified-weather-data-table)

**Called:** Automatically before first write

---

#### `write_records(dbName: str, tblName: str, records: List[dict])`
Write measurements to topic table.

**Process:**
1. Normalize table name
2. Ensure table exists
3. Transform records to row tuples
4. Batch insert with `execute_values()`
5. Commit transaction

**Record transformation:**
- Extract dimensions (unit, measurement_type)
- Parse timestamp (ms → datetime)
- Separate DOUBLE vs VARCHAR values
- Handle type conversion errors

**Batch size:** All records in single insert

---

#### `write_weather_data(rows: List[Tuple[datetime, str, str, float]])`
Write to unified weather_data table.

**Row format:** `(timestamp, station_id, metric, value)`

**Process:**
1. Ensure weather_data table exists
2. Batch insert all rows
3. Commit transaction

**Filter:** Only numeric (DOUBLE) values included

---

#### `_normalize_table_name(name: str) -> str`
Normalize table identifiers.

**Transformations:**
1. Convert to lowercase
2. Replace `-` with `_`
3. Truncate to 63 characters

**Logging:** Warns if truncation occurs

---

#### `_parse_dimensions(dimensions: List[dict]) -> Tuple[str, str]`
Extract metadata from record dimensions.

**Searches for:**
- `Name="unit"` → `unit` value
- `Name="Measurement Type"` → `measurement_type` value

**Returns:** `(unit, measurement_type)` tuple

**Default:** `(None, None)` if not found

---

### Grafana Integration (grafana_helpers.py)

#### `create_dashboard_table(table, session)`
Generate Grafana dashboard for topic.

**Process:**
1. Query all measurements for topic
2. Generate panel JSON for each visible measurement
3. Calculate panel grid positions
4. Create/update dashboard via Grafana API
5. Store dashboard UID in database

**API calls:**
- `POST /api/dashboards/db` - Create/update dashboard
- `GET /api/datasources` - Get PostgreSQL datasource UID

**Panel types:** Time-series line graphs

---

### Broker Management Functions

#### `add_broker(broker: mySqlUtil.broker)`
Initialize MQTT client for broker.

**Process:**
1. Create MQTT client with broker ID
2. Configure authentication (if enabled)
3. Set event callbacks
4. Add to global `clients[]` list
5. Start connection thread

**Thread lifecycle:** Runs `client_loop()` indefinitely

---

#### `broker_change_worker()`
Monitor shared memory for broker updates.

**Behavior:**
- Daemon thread checking `messages` shared memory
- Reads flags: `messages[0]` (has_message), `messages[1]` (ID), `messages[2]` (type)
- Resets flag after processing

**Use case:** Hot-reload broker configuration changes

---

### Utility Functions

#### `remove_shm_from_resource_tracker()`
Prevent shared memory cleanup on exit.

**Purpose:** Avoid resource tracker warnings

**Patches:** `multiprocessing.resource_tracker`

**Called:** Once at module initialization

---

### Logging Classes

#### `HourlyDirHandler(logging.Handler)`
Custom log handler with hourly rotation.

**Directory structure:**
```
logs/
  2026-02/
    13/
      00.log
      01.log
      ...
      23.log
    14/
      00.log
      ...
```

**Filename format:** `logs/YYYY-MM/DD/HH.log`

**Behavior:**
- Creates directories automatically
- Appends to hourly file
- UTF-8 encoding

---

#### `StreamToLogger(object)`
Redirect stdout/stderr to logger.

**Features:**
- Thread-safe with lock
- Line buffering
- Preserves newlines
- Flushable

**Use case:** Capture all print() and exceptions

---

### Lifecycle Hooks

#### `on_exit()`
Cleanup handler (atexit).

**Actions:**
1. Close shared memory
2. Flush stdout
3. Flush stderr

**Registration:** `atexit.register(on_exit)`

---

## Configuration

### config.ini Structure

**Required sections:**

```ini
[MQTT]
Authentication = True
UserName = mqtt_user
Password = mqtt_pass
Address = broker.example.com
Port = 1883

[Timescale]
DataBase = mqtt_dashboard
Schema = public                    # Optional, default: public
UserName = postgres
Password = db_password
Host = localhost
Port = 5432
AdminDatabase = postgres           # For DB creation
UseCurrentTimeAsTimestamp = False  # True = server time, False = payload time

[Grafana]
Address = http://localhost
Port = 3000
API_Key = <grafana_api_token>
```

**Backward compatibility:**
- Falls back to `[Timestream]` section if `[Timescale]` missing
- Falls back to `[MySQL]` section for credentials

---

## Logging System

### Log Levels
- **INFO**: Normal operations (connections, writes, schema changes)
- **WARNING**: Non-fatal issues (Grafana failures, truncations)
- **ERROR**: Failures requiring attention (connection errors, parse errors)
- **EXCEPTION**: Critical errors with stack traces

### Log Destinations
1. **Hourly files**: `logs/YYYY-MM/DD/HH.log`
2. **Console**: Original stdout (for systemd journal)

### Key Log Messages

**Connection events:**
```
Connected OK to broker 1 Returned code=0
Subscribed #
```

**Data ingestion:**
```
GeoJSON observations=15 timepoints=12
Derived station_id=233
GeoJSON time window UTC: min=2026-02-18 10:00:00+00:00 max=2026-02-18 10:55:00+00:00 (count=12)
Wrote 15 records to Timescale table weather_station_233 (topicID=42 time_source=payload record_time=2026-02-18T10:55:00+00:00)
Wrote 15 records to weather_data (topicID=42 station_id=233 time_source=payload record_time=2026-02-18T10:55:00+00:00)
```

**Schema changes:**
```
Timescale table missing, creating for topic=weather/station/233
Creating new timestream table
```

**Errors:**
```
Timescale ingest failed for topic=weather/station/233: <exception>
Grafana update failed for topic=weather/station/233; continuing without dashboard update: <exception>
```

---

## Performance Considerations

### Bottlenecks
1. **Grafana API calls**: Disabled after initial dashboard creation
2. **Database commits**: Minimized (only on schema changes)
3. **Queue size**: Limited to 1000 messages (tune for high-volume)

### Optimizations
- Connection pooling (10 connections max)
- Batch inserts (all records per timepoint)
- Async message processing
- Index on (measure_name, time DESC)
- Hypertable automatic partitioning

### Scaling Recommendations
- Increase queue size for high-volume topics
- Add more connection pool workers
- Use continuous aggregates for common queries
- Enable TimescaleDB compression for old data

---

## Error Recovery

### Connection Failures
- **MQTT**: Auto-reconnect with backoff (up to 15 attempts)
- **Database**: Session restart on any SQLAlchemy error
- **Grafana**: Continue without dashboard update

### Data Loss Prevention
- LIFO queue favors recent messages
- Database transactions committed per write
- Metadata rollback on constraint violations

### Monitoring
- Check log files for connection errors
- Monitor queue size (not exposed, add metrics if needed)
- Watch for table creation failures

---

## Deployment

### Systemd Service
Typically runs as `mqtt_subscriber.service`

**Recommended configuration:**
```ini
[Unit]
Description=MQTT to TimescaleDB Subscriber
After=network.target postgresql.service

[Service]
Type=simple
User=mqtt
WorkingDirectory=/home/ubuntu/mqtt_dashboard/mqtt_subscriber_timestream_output
ExecStart=/usr/bin/python3 -m mqtt_subscriber_timestream_output
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Dependencies
```bash
pip install paho-mqtt psycopg2 sqlalchemy pytz python-dateutil requests
```

### Database Setup
```sql
-- Create tables (run once)
CREATE TABLE brokers (...);
CREATE TABLE timestream_tables (...);
CREATE TABLE timestream_measurements (...);

-- Add initial broker
INSERT INTO brokers (url, port, authentication, username, password, name)
VALUES ('broker.example.com', 1883, true, 'user', 'pass', 'Main Broker');
```

---

## Troubleshooting

### No messages received
1. Check broker connection: `systemctl status mqtt_subscriber.service`
2. Verify credentials in config.ini
3. Check firewall rules (port 1883)
4. Review logs: `tail -f logs/$(date +%Y-%m/%d/%H).log`

### Database write failures
1. Check PostgreSQL service: `systemctl status postgresql`
2. Verify credentials in config.ini
3. Check disk space
4. Review table permissions

### Missing measurements
1. Check JSON format matches GeoJSON/CSIJSON spec
2. Verify `observationNames` array exists
3. Check for empty observation values (default to '0')

### Grafana dashboards not creating
1. Verify API key in config.ini
2. Check Grafana service running
3. Review datasource UID detection
4. Check logs for API errors

---

## License

[Add your license information]

## Contact

[Add contact information]
