# Message Formats

The subscriber handles two different payload formats: **GeoJSON** (the primary format used by most stations) and **CSIJSON** (Campbell Scientific datalogger format). Both are JSON-over-MQTT.

---

## GeoJSON Format

Used by most WMO/WIS2BOX-compatible stations. The root object is either a `FeatureCollection` or a single `Feature`.

### FeatureCollection Example

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [28.323, -15.408, 1280.5]
      },
      "properties": {
        "wigos_station_identifier": "0-894-2-LusakaAirport",
        "station_name": "Lusaka International Airport",
        "phenomenon_time": "2026-04-17T09:00:00Z",
        "resultTime": "2026-04-17T09:00:00Z",
        "observationNames": ["AirTemp", "WSpd", "WDir", "QFE"],
        "observationUnits": ["Celsius", "m/s", "Degrees", "hPa"],
        "observations": [24.3, 3.1, 270.0, 1013.2]
      }
    }
  ]
}
```

### Single Feature Example

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [28.323, -15.408]
  },
  "properties": {
    "station_id": "60790",
    "phenomenon_time": "2026-04-17T09:00:00Z",
    "observationNames": ["Temp_Avg", "Hum_Avg"],
    "observationUnits": ["C", "%"],
    "observations": [22.1, 68.5]
  }
}
```

### Parsing Logic (`_parse_geojson()`)

1. If `type == "FeatureCollection"`, iterate through `features[]`.
2. For a single `Feature`, process directly.
3. Extract coordinates: `geometry.coordinates` → `[longitude, latitude, (altitude)]`
4. From `properties`:
   - `observationNames` + `observations` + `observationUnits` → zip into records
   - `phenomenon_time` or `resultTime` → parse as timestamp using `dateutil.parser.isoparse()`
5. If `UseCurrentTimeAsTimestamp=True` in config, override with `datetime.utcnow()`
6. For each `(name, value, unit)`:
   - Try `float(value)` → type `DOUBLE`
   - If it fails → type `VARCHAR`
7. Return list of normalised records.

### Station ID Fields Parsed from GeoJSON

The following `properties` fields are checked for station identity (in order of priority — see [station-tracking.md](station-tracking.md)):
- `wigos_station_identifier`
- `station_id`
- `station_name`

---

## CSIJSON Format

Used by Campbell Scientific CR-series dataloggers. The structure has a `head` section describing columns and a `data` section with arrays of values.

### Example

```json
{
  "head": {
    "transaction": 0,
    "signature": 12345,
    "environment": {
      "station_name": "KitweStation",
      "table_name": "Hourly",
      "model": "CR1000X",
      "serial_no": "32891",
      "os_version": "CR1000X.Std.08.01",
      "prog_name": "CPU:HoursTable.CR1X"
    },
    "fields": [
      {"name": "TIMESTAMP", "type": "xsd:dateTime", "processing": ""},
      {"name": "RECORD",    "type": "xsd:integer",  "processing": ""},
      {"name": "AirTemp_Avg","type": "xsd:float",   "processing": "Avg", "units": "Celsius"},
      {"name": "WSpd_Avg",  "type": "xsd:float",   "processing": "Avg", "units": "m/s"},
      {"name": "WDir_D1_WVT","type":"xsd:float",   "processing": "WVT", "units": "Degrees"}
    ]
  },
  "data": [
    {
      "time": "2026-04-17T09:00:00",
      "no": 4821,
      "vals": [24.3, 3.1, 270.0]
    }
  ]
}
```

### How Field Names Map to Columns

- `head.fields[0]` = TIMESTAMP (skipped)
- `head.fields[1]` = RECORD number (skipped)
- `head.fields[2..]` = actual measurement fields

The `vals` array in each `data` row maps positionally to `head.fields[2..]`.

### Parsing Logic (`_parse_csijson()`)

1. Extract `head.environment.station_name` (used for station ID inference).
2. Build a field map: `{field_name: {"unit": ..., "type": ...}}` from `head.fields[2:]`.
3. For each row in `data[]`:
   - Parse `data[i].time` as the measurement timestamp.
   - Zip `data[i].vals` with field names from `head.fields[2:]`.
   - For each `(name, value)`:
     - Look up `unit` from the field map.
     - Try `float(value)` → type `DOUBLE`; otherwise → `VARCHAR`.
4. Return normalised records list.

---

## Normalised Record Format

Both parsers produce records in the same shape, which is then consumed uniformly by the ingestion pipeline:

```python
{
    "name":  "AirTemp_Avg",      # Sensor/field name (str)
    "value": 24.3,               # Numeric for DOUBLE, str for VARCHAR
    "unit":  "Celsius",          # Unit string (may be empty)
    "type":  "DOUBLE",           # "DOUBLE" or "VARCHAR"
    "time":  datetime(2026, 4, 17, 9, 0, 0, tzinfo=utc)
}
```

---

## Handling Unexpected Formats

If the payload matches neither format:

```python
logger.warning(f"[{topic}] Unknown payload format, skipping")
return
```

The message is dropped. No error is raised and the subscriber continues processing.

---

## Common Payload Issues

| Issue | Symptom | Resolution |
|-------|---------|-----------|
| Non-UTF8 payload | Decode error logged | Station firmware bug; check encoding |
| Empty `observations` array | No records inserted, no error | Verify station data is being collected |
| `observationNames` / `observations` length mismatch | Shorter array is used; extra entries dropped | Station firmware bug |
| Timestamp format not ISO 8601 | `dateutil.parser` raises exception; message dropped | Enable `UseCurrentTimeAsTimestamp=True` |
| `values` are `null` JSON | Type becomes VARCHAR with value `"null"` | Expected for missing sensors; filter in queries |

---

## Navigation

← [mqtt-ingest/README.md](README.md) | [docs/README.md](../README.md)
