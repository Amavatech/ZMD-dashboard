# Station Tracking

Weather stations are identified by a `station_id` — a short string that also forms the name of the station's TimescaleDB hypertable (`st_<station_id>`).

---

## Why Station IDs Matter

MQTT topic paths are long and contain slashes (e.g. `data-incoming/zmb/campbell-v1/0-894-2-LusakaAirport/data`). They cannot be used directly as PostgreSQL table names. A stable, short, normalised `station_id` is derived from the message content or topic to serve as:

- The hypertable name: `st_LusakaAirport`
- The `station_id` column in `weather_data`
- The foreign key link from `timestream_tables.station_id`

---

## Station ID Inference — `_infer_station_id()`

The function tries 4 sources in priority order, using the first one that produces a usable value:

### Priority 1: Explicit `station_id` in Payload

```python
# GeoJSON properties
properties.get("station_id")
```

If the payload contains a `station_id` field that is a non-empty string, it is used directly.

### Priority 2: WIGOS Station Identifier

```python
properties.get("wigos_station_identifier")
```

WMO WIGOS identifiers look like `"0-894-2-LusakaAirport"`. The function extracts the last segment after the final `-`:

```
"0-894-2-LusakaAirport"  →  "LusakaAirport"
```

### Priority 3: Station Name from CSIJSON

```python
head["environment"].get("station_name")
```

Campbell Scientific loggers include the station name in the `head.environment.station_name` field. This string is used directly (after normalisation).

### Priority 4: Topic Segment Extraction

If no payload field provides an ID, the topic path is parsed:

```
data-incoming/zmb/campbell-v1/LusakaAirport/data
                               ^^^^^^^^^^^^
                               take the 4th segment (index 3)
```

The segment at position 3 (0-indexed) is extracted. If the topic has fewer segments, a different index may be used.

### Normalisation

All candidate station IDs go through `_normalize_station_id()`:
- Convert to lowercase (for consistent table naming).
- Replace spaces and hyphens with underscores.
- Strip any characters that are not alphanumeric or underscores.
- Truncate to 60 characters (PostgreSQL table names max 63 chars; `st_` prefix uses 3).

---

## Station Contacts — `station_contacts.csv`

The subscriber maintains an in-memory CSV-like record of all known stations and their last contact time. This file is saved to disk periodically and also written/updated on each new message.

**File location:** `mqtt_subscriber_timestream_output/station_contacts.csv` (or configured path)

**Columns:**
```
station_id, topic, latitude, longitude, last_seen
```

**Example row:**
```
LusakaAirport,data-incoming/zmb/campbell-v1/LusakaAirport/data,-15.408,28.323,2026-04-17T09:00:00Z
```

### How It Is Used

- **Loaded at startup:** Builds the `known_stations` dict `{station_id: contact_info}`.
- **Updated on every message:** `_update_station_contact(station_id, topic, lat, lon, timestamp)`.
- **Written at shutdown** (and periodically): saved to disk so the list survives restarts.
- **Read by the Flask dashboard:** `/station_contacts` route returns this data for the map view.

### Inspecting the Contact File

```bash
# See all known stations and when they last transmitted
cat mqtt_subscriber_timestream_output/station_contacts.csv
```

---

## `station_contacts` in the Dashboard

The Flask API endpoint `/station_contacts` reads the same CSV (or queries the database) and returns station locations and last-seen timestamps. The admin map uses this to show green/yellow/red indicators.

---

## Deduplication

If the same physical station sends data on multiple topics (e.g. `../HOUR/data` and `../SYNOP/data`), the subscriber:

1. Resolves the same `station_id` for both topics (because the WIGOS identifier or station name matches).
2. Writes all measurements to the same hypertable `st_<station_id>`.
3. Stores both topic strings in the `timestream_tables.topics` array.

Only one metadata row (`timestream_tables`) exists per station, regardless of how many topics it sends on.

---

## Adding a Station With a Known ID

If you need to pre-register a station (before it sends any data):

1. Go to the admin UI → "Add Topic".
2. Enter the MQTT topic and optionally the station_id.
3. Save. The `timestream_tables` row is created.
4. The hypertable `st_<station_id>` will be created when the first message arrives.

---

## Troubleshooting Wrong Station IDs

If a station ended up with the wrong `station_id` (e.g. it used a topic segment instead of the WIGOS identifier):

1. Stop the subscriber: `sudo systemctl stop mqtt_subscriber`
2. Find the row: `SELECT tableid, topic, station_id FROM timestream_tables WHERE topic = '...';`
3. Rename the hypertable:
   ```sql
   ALTER TABLE public."st_old_id" RENAME TO "st_new_id";
   ```
4. Update the metadata: `UPDATE timestream_tables SET station_id = 'new_id' WHERE tableid = X;`
5. Start the subscriber: `sudo systemctl start mqtt_subscriber`

---

## Navigation

← [mqtt-ingest/README.md](README.md) | [docs/README.md](../README.md)
