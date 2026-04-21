# `download.py` — Download and Publish Satellite Data

**Script:** `wiz2box_forward/download.py`  
**Purpose:** Downloads `.dat` files from the EUMETSAT satellite relay for all registered stations, then publishes the data to MQTT as GeoJSON.

---

## What It Does (Step by Step)

1. **Reads `stations.csv`** — a CSV file in `wiz2box_forward/` listing every DCP station with its DCP ID, WIGOS ID, station name, and serial number.

2. **Downloads `.dat` files** — for each station in the CSV, makes an HTTP request to the EUMETSAT download endpoint authenticated with the Zambia Met credentials. Each station typically produces two files:
   - `<StationName>_TableHour.dat` — hourly averages
   - `<StationName>_TableSYNOP.dat` — SYNOP-format synoptic readings

3. **Saves files** to `EUMETSAT/<StationName>_DCP_<DCP_ID>/`

4. **Parses the TOA5 format** — `.dat` files use Campbell Scientific's TOA5 CSV format with 4 header rows:
   - Row 1: Environment header (station name, datalogger model, OS version)
   - Row 2: Column names
   - Row 3: Units
   - Row 4: Processing type (Avg, Max, Min, WVT, etc.)
   - Row 5+: Data rows

5. **Converts rows to GeoJSON** — each timestamp row in the file becomes one GeoJSON Feature message.

6. **Publishes to MQTT** — connects to the MQTT broker and publishes each GeoJSON message to the topic:
   ```
   data-incoming/zmb/campbell-v1/<WIGOS_ID>/data
   ```

7. **Writes `station_run_log.txt`** — records which stations were contacted and which had new data.

8. **Records a metric to the reporting endpoint** — POSTs a count of stations with data to `REPORT_ENDPOINT` for operational monitoring.

---

## TOA5 File Format

```
"TOA5","LusakaAirport","CR1000X","32891","CR1000X.Std.08","CPU:HoursTable.CR1X","12345","TableHour"
"TIMESTAMP","RECORD","JobID","AirTemp_Avg","WSpd_Avg","WDir_D1_WVT","QFE_Avg"
"TS","RN","","Celsius","m/s","Degrees","hPa"
"","","Smp","Avg","Avg","WVT","Avg"
"2026-04-17 08:00:00",4821,1,24.3,3.1,270.0,1013.2
"2026-04-17 09:00:00",4822,1,24.8,2.9,265.0,1013.0
```

The data rows start at row 5 (index 4 in pandas `skiprows=4`).

---

## GeoJSON Output Format

Each data row is converted to a GeoJSON Feature:

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [28.323, -15.408]
  },
  "properties": {
    "observationNames": ["AirTemp_Avg", "WSpd_Avg", "WDir_D1_WVT", "QFE_Avg", "Station_Name", "Station_ID"],
    "observationUnits": ["Celsius", "m/s", "Degrees", "hPa", "", ""],
    "observations": {
      "2026-04-17T09:00:00Z": [24.8, 2.9, 265.0, 1013.0, "Lusaka Airport", "LusakaAirport"]
    }
  }
}
```

Fields skipped when building observations:
```python
SKIP_COLS = {'TIMESTAMP', 'RECORD', 'JobID', 'StationID', 'WMO_Block', 'Station_ID', 
             'Station_Name', 'WMO_Station_Type', 'M_Year', 'M_Month', ...}
```
These metadata columns are excluded from the observations array, but `Station_Name` and `Station_ID` are appended back as string observations so the subscriber can use them for station ID inference.

---

## `stations.csv` Format

```csv
WMO_Station_Name,WMO_Station_ID(WIGOS ID),DCP ID,Serial
Lusaka Airport,0-894-2-LusakaAirport,12AB34CD,32891
Kitwe Station,0-894-2-KitweStation,56EF78GH,45902
```

---

## Incremental Downloads

The script checks the last timestamp in the database for each station (via `timescaleUtil.get_latest_timestamp`) and only publishes rows newer than that timestamp. This prevents re-ingestion of historical data on repeated runs.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Station not in download endpoint | Logged, station skipped |
| .dat file missing or empty | Skipped |
| Not a valid TOA5 file | Skip warning logged |
| MQTT publish failure | Error logged, script continues |
| Reporting endpoint unreachable | Warning logged, script continues |

---

## Running on a Schedule

To run every hour via cron:

```bash
crontab -e

# Add this line:
0 * * * * cd /home/ubuntu/mqtt_dashboard && ./venv/bin/python3 wiz2box_forward/download.py >> wiz2box_forward/download.log 2>&1
```

---

## Navigation

← [satellite-ingest/README.md](README.md) | [docs/README.md](../README.md)
