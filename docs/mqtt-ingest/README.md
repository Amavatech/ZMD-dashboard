# MQTT Ingest — Overview

The MQTT subscriber is a long-running background service that connects to one or more MQTT brokers, receives weather station messages, and writes them to TimescaleDB.

---

## Contents

- [pipeline.md](pipeline.md) — End-to-end message processing pipeline
- [message-formats.md](message-formats.md) — GeoJSON and CSIJSON payload formats
- [broker-management.md](broker-management.md) — Broker configuration and live reload
- [station-tracking.md](station-tracking.md) — Station ID inference and contact records
- [logging.md](logging.md) — Log files, stats reporting, and silence watchdog

---

## Service Basics

**Location:** `mqtt_subscriber_timestream_output/`  
**Entry point:** `mqtt_subscriber_timestream_output/__main__.py`  
**Config file:** `mqtt_subscriber_timestream_output/config.ini`  
**Systemd service name:** `mqtt_subscriber`

```bash
# Start/stop the subscriber
sudo systemctl start mqtt_subscriber
sudo systemctl stop mqtt_subscriber
sudo systemctl restart mqtt_subscriber

# Follow logs
journalctl -u mqtt_subscriber -f

# Check status
sudo systemctl status mqtt_subscriber
```

---

## Key Files

| File | Purpose |
|------|---------|
| `__main__.py` | Main process: broker threads, message queue, ingestion workers |
| `timescaleUtil.py` | Low-level TimescaleDB INSERT/CREATE operations via psycopg2 |
| `mySqlUtil.py` | Reads/writes relational metadata via SQLAlchemy |
| `configUtil.py` | Parses `config.ini` into typed dataclasses |
| `grafana_helpers.py` | Creates/updates Grafana dashboards for each station |
| `TimeStreamUtil.py` | ⚠️ DEPRECATED — do not use (raises RuntimeError) |
| `config.ini` | Runtime configuration (see [webapp/configuration.md](../webapp/configuration.md)) |

---

## High-Level Data Flow

```
MQTT Broker
    │
    │  (paho-mqtt subscribe, one thread per broker)
    ▼
on_message() callback
    │  topic + raw JSON payload
    │  no blocking here → fast enqueue
    ▼
message_queue (LIFO deque, max 1000)
    │
    │  background ingestion thread
    ▼
message_to_timescale(topic, payload)
    │
    ├── Parse format (GeoJSON / CSIJSON)
    ├── Resolve station_id (4-priority algorithm)
    ├── Ensure hypertable exists (create if not)
    ├── Ensure metadata rows exist (broker, table, measurements)
    ├── Write rows to st_<station_id>
    ├── Write rows to weather_data
    └── Trigger Grafana dashboard creation if new station
```

---

## Startup Sequence

1. Load `config.ini` via `configUtil.py`
2. Monkey-patch the multiprocessing resource tracker (shared memory workaround — see [webapp/ipc.md](../webapp/ipc.md))
3. Configure `HourlyDirHandler` logging (see [logging.md](logging.md))
4. Attach (or create) the `"messages"` ShareableList for IPC
5. Start the message processing thread
6. Query the `brokers` table; start one MQTT thread per broker
7. Start the stats reporter thread (every 2 minutes)
8. Start the silence watchdog thread (15-minute inactivity alert)
9. Enter the main IPC polling loop

---

## Navigation

← [docs/README.md](../README.md)
