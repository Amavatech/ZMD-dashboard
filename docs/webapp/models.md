# Database Models (ORM Reference)

**File:** `mqtt_dashboard/models.py`  
**ORM:** Flask-SQLAlchemy  
**Database:** PostgreSQL / TimescaleDB

The models define the *relational metadata* schema — the configuration and access-control tables. Time-series data lives in separate hypertables and is accessed via raw SQL (see [database/hypertables.md](../database/hypertables.md)).

---

## Model Overview

```
brokers ──────────────────────┐
                               │ (1 broker → many tables)
                               ▼
                      timestream_tables ────────────────────┐
                               │                             │ (1 table → many measurements)
                               │                             ▼
groups ────────────────────────┘              timestream_measurements
(groupID FK on timestream_tables)
                               │
permissions ───────────────────┤ (links users → tables or groups)
     │
users ────────────────────────┘
```

---

## `User` — `users` table

Represents a person who can log in to the dashboard.

| Column | DB name | Type | Description |
|--------|---------|------|-------------|
| `userID` | `userid` | Integer PK | Auto-incrementing ID |
| `email` | `email` | String(100) UNIQUE | Login credential |
| `password` | `password` | String(100) | Bcrypt hash — **never plain text** |
| `name` | `name` | String(100) | Display name |
| `db_uid` | `db_uid` | String(15) | Grafana user UID (legacy, rarely used) |
| `ss_key` | `ss_key` | String(32) | Grafana snapshot key for this user |

**Relationships:** `User.permissions` → list of `permission` objects

**Notes:**
- `get_id()` returns `userID` (Flask-Login convention; it stores this in the session).
- `ss_key` stores the most recently created Grafana snapshot key. Updated by `grafana_helpers.update_snapshot_user()`.

---

## `broker` — `brokers` table

An MQTT broker the subscriber connects to.

| Column | DB name | Type | Description |
|--------|---------|------|-------------|
| `brokerID` | `brokerid` | Integer PK | Auto-incrementing ID |
| `URL` | `url` | String(100) | Hostname or IP address of the broker |
| `port` | `port` | Integer | MQTT port (typically 1883 or 8883 for TLS) |
| `authentication` | `authentication` | Integer / Boolean | 1 = username/password required |
| `username` | `username` | String(100) | MQTT username |
| `password` | `password` | String(100) | MQTT password (stored in plain text) |
| `name` | `name` | String(100) | Friendly label for the UI |

**Relationships:** `broker.tables` → list of `timestream_table` objects

**Notes:**
- When a broker is created/edited/deleted via `/create_broker`, `/edit_broker`, or `/delete_broker`, the `messages` shared memory list is updated so the subscriber reacts immediately.
- Passwords are stored plain text in the database. This is a known limitation — brokers in this deployment are internal network equipment.

---

## `timestream_table` — `timestream_tables` table

Represents a single data source: an MQTT topic that maps to a weather station.

| Column | DB name | Type | Description |
|--------|---------|------|-------------|
| `tableID` | `tableid` | Integer PK | Auto-incrementing ID |
| `topic` | `topic` | String(255) UNIQUE | The primary MQTT topic path (e.g. `data-incoming/zmb/campbell-v1/0-894-2-LusakaAirport/data`) |
| `brokerID` | `brokerid` | Integer FK → `brokers` | Which broker this station reports through |
| `db_uid` | `db_uid` | String(15) | Grafana dashboard UID for this station |
| `ss_key` | `ss_key` | String(32) | Grafana snapshot key for this station |
| `longitude` | `longitude` | Float | Station longitude (updated from payload) |
| `latitude` | `latitude` | Float | Station latitude (updated from payload) |
| `groupID` | `groupid` | Integer FK → `groups` | Display group assignment (0 = ungrouped) |
| `station_id` | `station_id` | String(64) | Canonical station identifier (e.g. `LusakaAirport`, `60790`) |
| `topics` | `topics` | Array(String) | All topic variants seen for this station (SYNOP, HOUR, etc.) |

**Relationships:**
- `timestream_table.broker` → the associated `broker`
- `timestream_table.measurements` → list of `timestream_measurement` objects

**Notes:**
- `station_id` is authoritative. The physical TimescaleDB hypertable is named `st_<station_id>`.
- `topics` is a PostgreSQL array holding all MQTT topic variants that have been aggregated into this row (e.g. both a 5-minute and hourly topic from the same station).
- If `db_uid` is empty string `""`, no Grafana dashboard has been created yet.

---

## `timestream_measurement` — `timestream_measurements` table

One measurable quantity (sensor reading type) for a station.

| Column | DB name | Type | Default | Description |
|--------|---------|------|---------|-------------|
| `measurementID` | `measurementid` | Integer PK | auto | Auto-incrementing ID |
| `name` | `name` | String(255) | | Raw measurement name from the MQTT payload (e.g. `AirTemp_Avg`) |
| `directionName` | `directionname` | String(255) | | Wind direction measurement name — only used when `graph='ROSE'` for wind-rose panels |
| `tableID` | `tableid` | Integer FK → `timestream_tables` | | Which station this belongs to |
| `unit` | `unit` | String(255) | `unitless` | Unit string (e.g. `Celsius`, `%`, `hPa`) |
| `nickname` | `nickname` | String(100) | `""` | Display name shown in Grafana panel title |
| `type` | `type` | String(10) | `DOUBLE` | `DOUBLE` for numeric values, `VARCHAR` for strings |
| `graph` | `graph` | String(10) | `LINE` | Grafana panel type: `LINE` (time series), `ROSE` (wind rose), or anything else for table panel |
| `visible` | `visible` | Integer | `1` | 1 = include in Grafana dashboard, 0 = hidden |
| `status` | `status` | Integer | `0` | 1 = "status" measurement (shows latest value as a table, not a time series) |

**Relationships:** `timestream_measurement.table` → the associated `timestream_table`

**When a measurement row is created:** The first time a measurement name appears in an MQTT payload for a topic, `mySqlUtil.add_timestream_measurement()` inserts a row. This also triggers Grafana dashboard regeneration.

**Editing measurements:** Use `/edit_measurement` in the dashboard UI or directly update the row in the database. After editing, the Grafana dashboard is automatically regenerated.

---

## `permission` — `permissions` table

Links a user to a scope of access.

| Column | DB name | Type | Description |
|--------|---------|------|-------------|
| `permissionID` | `permissionid` | Integer PK | Auto-incrementing ID |
| `type` | `type` | String(10) | Permission type (see below) |
| `userID` | `userid` | Integer FK → `users` | Which user |
| `tableID` | `tableid` | Integer FK → `timestream_tables` | For TOPIC permissions: which topic |
| `groupID` | `groupid` | Integer FK → `groups` | For GROUP permissions: which group |

**Permission types:** `TOPIC`, `GROUP`, `ALL_TOPIC`, `ADMIN`, `GROUP_ADMIN`, `GADMIN`, `GDMIN`, `GROUP_ADMI`  
(See [auth.md](auth.md) for the full description of each type.)

**Notes:**
- For `TOPIC` permissions: `tableID` is set, `groupID` is NULL.
- For `GROUP` permissions: `groupID` is set, `tableID` is NULL.
- For `ADMIN` / `ALL_TOPIC`: both `tableID` and `groupID` are NULL.
- A user can have multiple permissions of different types.

---

## `group` — `groups` table

A named collection of topics/stations for display grouping.

| Column | DB name | Type | Description |
|--------|---------|------|-------------|
| `groupID` | `groupid` | Integer PK | Auto-incrementing ID |
| `name` | `name` | String(100) | Display name (e.g. `"Zambia Met"`, `"Airport Stations"`) |

**Notes:**
- Topics are assigned to groups via `timestream_table.groupID`.
- Group 3 is treated specially: users in group 3 are redirected to the GEOSS stations map (`/geoss_stations`).
- Deleting a group sets all member stations' `groupID` to `0` (ungrouped).

---

## Subscriber-side ORM (`mySqlUtil.py`)

The MQTT subscriber has its own independent SQLAlchemy session in `mySqlUtil.py`. It defines near-identical model classes (`timestream_table`, `timestream_measurement`, `broker`) mapped to the same database tables. This means both the Flask app and the subscriber write to the same PostgreSQL database but through separate connection pools.

> **Important:** `Base.metadata.create_all(engine)` is commented out in `mySqlUtil.py`. The schema must be created via the Flask app's initial setup or manually — the subscriber will not create tables for the metadata schema.

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
