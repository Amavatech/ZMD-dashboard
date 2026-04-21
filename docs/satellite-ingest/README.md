# Satellite Ingest — Overview

The `wiz2box_forward/` folder contains scripts that retrieve weather data from the EUMETSAT satellite relay (via a Zambia Met Department GOES/DCP receiver) and feed it into the same ingestion pipeline as the live MQTT subscriber.

---

## Contents

- [download.md](download.md) — `download.py`: Download .dat files, convert to GeoJSON, publish to MQTT
- [import.md](import.md) — `import.py`: Directly import .dat files into TimescaleDB (bypass MQTT)
- [publish.md](publish.md) — `publish.py`: Re-publish already-downloaded .dat files to MQTT

---

## What Is EUMETSAT / DCP?

The Zambia Meteorological Department uses **GOES/DCP (Data Collection Platforms)** — physical radio transmitters at each weather station that relay data to the EUMETSAT satellite downlink. Zambia Met receives the data dumps via an agreed download endpoint.

Each station's data arrives as a **TOA5 `.dat` file** — a CSV-like format produced by Campbell Scientific CR1000X dataloggers with 4 header rows describing column names, units, and processing methods.

---

## Relationship to the MQTT Pipeline

- `download.py` downloads `.dat` files → converts to GeoJSON → publishes to MQTT.
- The MQTT subscriber receives the GeoJSON messages on `data-incoming/zmb/campbell-v1/...` and processes them exactly like live station data.
- `import.py` bypasses MQTT entirely and writes directly to TimescaleDB using `timescaleUtil.py`. Used for bulk backfill or when MQTT is unavailable.
- `publish.py` reads already-downloaded `.dat` files and publishes them to MQTT. Used for replaying historical data.

---

## File Layout

```
wiz2box_forward/
├── download.py            # Main operational script
├── import.py              # Direct-to-DB importer
├── publish.py             # Re-publisher for downloaded .dat files
├── stations.csv           # Registry of stations (DCP ID, WIGOS ID, name)
├── station_run_log.txt    # Auto-generated during last download run
├── EUMETSAT/              # Downloaded .dat files, organised by station folder
├── migrate_to_public_schema.py  # One-time migration utility (legacy)
├── test_dryrun.py         # Development test script
└── test_import_single.py  # Development test for a single station
```

---

## Running the Download Script

`download.py` is typically run by a cron job or manually:

```bash
cd /home/ubuntu/mqtt_dashboard
source venv/bin/activate
python3 -m wiz2box_forward.download
# or
python3 wiz2box_forward/download.py
```

The script:
1. Reads `stations.csv` for the list of DCP IDs.
2. Downloads the latest `.dat` files from the EUMETSAT endpoint for each station.
3. Converts each row to a GeoJSON message.
4. Publishes each message to the MQTT broker.
5. Writes `station_run_log.txt` summarising which stations were contacted.

---

## Key Configuration Constants (Hard-coded in `download.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `username` | `"ZambiaMD"` | EUMETSAT download credential (username) |
| `password` | `"5PhzAHE3P4H1"` | EUMETSAT download credential |
| `MQTT_BROKER` | `"3.124.208.185"` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | `"wis2box"` | MQTT auth |
| `MQTT_PASSWORD` | `"Wh00mqtt!"` | MQTT auth |
| `MQTT_TOPIC_PREFIX` | `"data-incoming/zmb/campbell-v1"` | Topic prefix all messages are published under |

> **Security note:** These credentials are hard-coded as plain text in the source file. For a production system, move them to a config file or environment variables.

---

## Navigation

← [docs/README.md](../README.md)
