# `publish.py` — Re-Publish Downloaded Data to MQTT

**Script:** `wiz2box_forward/publish.py`  
**Purpose:** Reads `.dat` files from the `EUMETSAT/` folder and publishes them to MQTT as GeoJSON. Used for replaying historical data through the normal ingestion pipeline.

---

## Difference From `download.py`

| | `download.py` | `publish.py` |
|--|--------------|-------------|
| Downloads from EUMETSAT | Yes | No |
| Reads from local `.dat` files | Yes (after downloading) | Yes |
| Publishes to MQTT | Yes | Yes |
| Suited for | Regular scheduled runs | One-off replay / backfill |
| Filtering by time window | Implicit (checks DB) | `--hours N` argument |
| Station filter | All stations | `--station NAME` argument |

---

## Usage

```bash
# Publish all data from all stations
python3 wiz2box_forward/publish.py

# Only publish records from the last 24 hours
python3 wiz2box_forward/publish.py --hours 24

# Only publish a specific station
python3 wiz2box_forward/publish.py --station LusakaAirport

# Combine filters
python3 wiz2box_forward/publish.py --hours 6 --station LusakaAirport
```

---

## What It Does

1. Parses command-line arguments (`--hours`, `--station`).
2. Reads `stations.csv`.
3. For each station matching `--station` (or all stations if not filtered):
   - Finds `EUMETSAT/<StationName>_DCP_<DCP_ID>/`:
     - `<StationName>_TableHour.dat`
     - `<StationName>_TableSYNOP.dat`
   - Calls `read_dat_file()` to parse the TOA5 file into a DataFrame.
   - Calls `df_to_geojson_messages()` to convert each row to a GeoJSON dict (filtered to `--hours` if set).
   - Connects to the MQTT broker.
   - Publishes each GeoJSON to `data-incoming/zmb/campbell-v1/<WIGOS_ID>/data` with QoS 0.

---

## TOA5 File Reading (`read_dat_file()`)

The function handles the 4-header-row TOA5 format:

```python
# Read headers
header_df = pd.read_csv(filepath, skiprows=1, nrows=2, header=None)
headers = header_df.iloc[0].tolist()  # column names
units   = header_df.iloc[1].tolist()  # units

# Read data
df = pd.read_csv(filepath, skiprows=4, names=headers, low_memory=False)
df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], errors='coerce')
df = df.dropna(subset=['TIMESTAMP'])
```

---

## Time Filtering

If `--hours N` is given, `df_to_geojson_messages()` compares each row's timestamp against `datetime.now(UTC) - timedelta(hours=N)` and yields only rows newer than the cutoff.

---

## GeoJSON Format Published

Same format as `download.py` — see [download.md](download.md#geojson-output-format).

---

## Use Case: Re-Ingesting Lost Data

If the MQTT subscriber was offline for a period and messages were missed:

1. Ensure `download.py` has been run so `.dat` files in `EUMETSAT/` are up to date.
2. Run `publish.py --hours <gap_in_hours>` to re-publish the missed window.
3. The subscriber will receive and process the messages normally.
4. Duplicate rows are safely ignored by the `ON CONFLICT DO NOTHING` clause in the INSERT.

---

## Navigation

← [satellite-ingest/README.md](README.md) | [docs/README.md](../README.md)
