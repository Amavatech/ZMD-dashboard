# Database Schema Reference

This document covers every relational table in the `mqtt_dashboard` PostgreSQL database.

For time-series hypertables, see [hypertables.md](hypertables.md).

---

## `brokers`

Stores MQTT broker connection details. The subscriber reads this table on startup and connects to every active broker.

```sql
CREATE TABLE brokers (
    brokerid      SERIAL PRIMARY KEY,
    url           VARCHAR(100),        -- Hostname or IP (e.g. "3.124.208.185")
    port          INTEGER,             -- MQTT port (usually 1883)
    authentication BOOLEAN DEFAULT TRUE, -- True = requires username/password
    username      VARCHAR(100),
    password      VARCHAR(100),        -- Plain text
    name          VARCHAR(100)         -- Friendly label shown in the UI
);
```

**Managed via:** `/broker_admin` UI, `/create_broker`, `/edit_broker`, `/delete_broker` routes.  
**On change:** IPC `messages` list signals the subscriber.

---

## `timestream_tables`

One row per weather station. The `topic` column maps to the MQTT subscription topic the data arrives on. The physical TimescaleDB hypertable is named `st_<station_id>`.

```sql
CREATE TABLE timestream_tables (
    tableid    SERIAL PRIMARY KEY,
    brokerid   INTEGER REFERENCES brokers(brokerid),
    topic      VARCHAR(255) UNIQUE,   -- Primary MQTT topic path
    db_uid     VARCHAR(15),           -- Grafana dashboard UID (empty = not yet created)
    ss_key     VARCHAR(32) DEFAULT '', -- Grafana snapshot key
    longitude  FLOAT,
    latitude   FLOAT,
    groupid    INTEGER,               -- FK to groups.groupid (0 = ungrouped)
    station_id VARCHAR(64),           -- Canonical ID (maps to physical table st_<id>)
    topics     VARCHAR(255)[]         -- All topic variants for this station
);
```

**Hypertable link:** `station_id` → physical table `public.st_<station_id>`  
**Created by:** subscriber on first message from an unknown topic  
**Managed via:** admin UI, `remove_topic` route

**Important columns:**
- `topic` — the "canonical" topic the station was first seen on
- `topics` — array of all variants (e.g. both `HOUR` and `SYNOP` suffixes)
- `station_id` — set during the `migrate_to_station_ids.py` migration; determines the hypertable name

---

## `timestream_measurements`

One row per sensor per station. Defines how each measurement is displayed in Grafana.

```sql
CREATE TABLE timestream_measurements (
    measurementid SERIAL PRIMARY KEY,
    name          VARCHAR(255),           -- Raw field name from MQTT payload
    directionname VARCHAR(255),           -- Wind direction field (ROSE graphs only)
    tableid       INTEGER REFERENCES timestream_tables(tableid),
    unit          VARCHAR(255) DEFAULT 'unitless',
    nickname      VARCHAR(100) DEFAULT '', -- Display name (override for `name`)
    type          VARCHAR(10)  DEFAULT 'DOUBLE',  -- 'DOUBLE' or 'VARCHAR'
    graph         VARCHAR(10)  DEFAULT 'LINE',    -- 'LINE', 'ROSE', or '' for table
    visible       INTEGER      DEFAULT 1,  -- 1=shown in Grafana, 0=hidden
    status        INTEGER      DEFAULT 0   -- 1=show as latest-value table, 0=time series
);
```

**Created by:** subscriber when a new measurement name appears in a payload  
**Managed via:** `/edit_measurement` route (admin UI)  
**After editing:** Grafana dashboard is automatically regenerated

---

## `groups`

Named collections of stations for display grouping on the map and in the UI.

```sql
CREATE TABLE groups (
    groupid SERIAL PRIMARY KEY,
    name    VARCHAR(100)
);
```

**Examples:** `"Zambia Met Stations"`, `"Airport AWOS"`, `"GEOSS Network"`  
**Managed via:** `/group_admin` UI, `/create_group`, `/delete_group` routes

> **Group 3 is special:** Users whose permission points to `groupID=3` are automatically redirected to the GEOSS stations map view (`/geoss_stations`).

---

## `users`

Dashboard login accounts.

```sql
CREATE TABLE users (
    userid   SERIAL PRIMARY KEY,
    email    VARCHAR(100) UNIQUE,
    password VARCHAR(100),      -- Werkzeug bcrypt hash
    name     VARCHAR(100),
    db_uid   VARCHAR(15),       -- Legacy Grafana UID (rarely used)
    ss_key   VARCHAR(32) DEFAULT '' -- User's current Grafana snapshot key
);
```

**Managed via:** `/create_user`, `/delete_user`, `/signup` routes  
**Never store plain-text passwords** — always use `generate_password_hash()`.

---

## `permissions`

Access control linking users to topics or groups.

```sql
CREATE TABLE permissions (
    permissionid SERIAL PRIMARY KEY,
    type         VARCHAR(10),           -- 'TOPIC', 'GROUP', 'ALL_TOPIC', 'ADMIN', ...
    userid       INTEGER REFERENCES users(userid),
    tableid      INTEGER REFERENCES timestream_tables(tableid),  -- for TOPIC type
    groupid      INTEGER REFERENCES groups(groupid)              -- for GROUP type
);
```

**Valid type values:**

| Type | `tableid` | `groupid` | Access granted |
|------|-----------|-----------|----------------|
| `TOPIC` | set | NULL | One specific station |
| `GROUP` | NULL | set | All stations in a group |
| `ALL_TOPIC` | NULL | NULL | All stations (technician) |
| `ADMIN` | NULL | NULL | Full admin access |
| `GROUP_ADMIN`, `GADMIN`, `GDMIN`, `GROUP_ADMI` | NULL | NULL | Admin (variant spellings) |

---

## Entity Relationship Diagram

```
brokers (1) ──────────────────────────────── (N) timestream_tables
                                                        │
                                                        │ (1 table → N measurements)
                                                        ▼
                                              timestream_measurements

groups (1) ────────────────────────────────── (N) timestream_tables
                                                   (via groupid FK)

users (1) ──── (N) permissions (N) ──────────── (1) timestream_tables
                      │                               (TOPIC type)
                      └─────────────────────────── (1) groups
                                                       (GROUP type)
```

---

## Useful Administrative Queries

```sql
-- List all stations with their station_id and group
SELECT t.tableid, t.topic, t.station_id, g.name AS group_name
FROM timestream_tables t
LEFT JOIN groups g ON t.groupid = g.groupid
ORDER BY t.tableid;

-- Count measurements per station
SELECT t.station_id, t.topic, COUNT(m.measurementid) AS measurement_count
FROM timestream_tables t
LEFT JOIN timestream_measurements m ON m.tableid = t.tableid
GROUP BY t.tableid, t.station_id, t.topic;

-- Find stations with no group assigned
SELECT tableid, topic, station_id
FROM timestream_tables
WHERE groupid IS NULL OR groupid = 0;

-- List all admin users
SELECT u.name, u.email, p.type
FROM users u JOIN permissions p ON p.userid = u.userid
WHERE p.type IN ('ADMIN','GROUP_ADMIN','GADMIN','GDMIN','GROUP_ADMI');

-- Check which brokers are configured
SELECT brokerid, name, url, port, authentication FROM brokers;
```

---

## Navigation

← [database/README.md](README.md) | [docs/README.md](../README.md)
