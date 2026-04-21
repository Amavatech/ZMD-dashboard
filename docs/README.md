# MQTT Dashboard — Documentation Index

This folder contains the full technical documentation for the MQTT Dashboard and Data Ingestion System. It is written for maintainers with no prior knowledge of the codebase.

---

## Documentation Tree

```
docs/
├── README.md                    ← you are here
│
├── webapp/                      Web-facing Flask application
│   ├── README.md                Overview & how the app boots
│   ├── configuration.md         config.ini reference
│   ├── auth.md                  Login, signup, roles & permissions
│   ├── routes.md                Every URL endpoint explained
│   ├── models.md                Database models (ORM) reference
│   ├── grafana-integration.md   How dashboards are created
│   └── ipc.md                   Shared memory IPC with the subscriber
│
├── database/                    PostgreSQL + TimescaleDB
│   ├── README.md                Overview of the database design
│   ├── schema.md                All tables, columns, and relationships
│   ├── hypertables.md           Time-series hypertables explained
│   ├── connection.md            Credentials, psql, and schema paths
│   └── maintenance.md          Backups, restore, and migrations
│
├── mqtt-ingest/                 MQTT subscriber / ingest service
│   ├── README.md                Service overview
│   ├── pipeline.md              Step-by-step message processing
│   ├── message-formats.md       GeoJSON and CSIJSON schemas
│   ├── broker-management.md     Broker config and live-reload
│   ├── station-tracking.md      Station ID inference and contact log
│   └── logging.md               Log file layout and rotation
│
├── satellite-ingest/            EUMETSAT / WIS2BOX data forwarding
│   ├── README.md                Overview of the forwarding pipeline
│   ├── download.md              download.py — fetching .dat files
│   ├── import.md                import.py — direct DB import
│   └── publish.md               publish.py — MQTT re-publish
│
└── utilities/                   Maintenance and operations scripts
    ├── README.md                Overview of all utility scripts
    ├── database-maintenance.md  purge, count, migrate scripts
    ├── grafana-tools.md         Dashboard rebuild and snapshot scripts
    ├── redundant-scripts.md     Old / redundant scripts identified
    └── testing.md               Developer test scripts
```

---

## Quick Navigation

### "I need to…"

| Task | Go to |
|------|-------|
| Add or edit a broker | [mqtt-ingest/broker-management.md](mqtt-ingest/broker-management.md) |
| Add a new user / permission | [webapp/auth.md](webapp/auth.md) |
| Understand the database schema | [database/schema.md](database/schema.md) |
| Check what a URL endpoint does | [webapp/routes.md](webapp/routes.md) |
| Understand how a message becomes database rows | [mqtt-ingest/pipeline.md](mqtt-ingest/pipeline.md) |
| Fix a broken Grafana dashboard | [webapp/grafana-integration.md](webapp/grafana-integration.md) |
| Restore from a database backup | [database/maintenance.md](database/maintenance.md) |
| Understand time-series storage | [database/hypertables.md](database/hypertables.md) |
| Delete empty / inactive stations | [utilities/database-maintenance.md](utilities/database-maintenance.md) |
| Run EUMETSAT satellite data | [satellite-ingest/README.md](satellite-ingest/README.md) |
| Know if a script is still needed | [utilities/redundant-scripts.md](utilities/redundant-scripts.md) |
| Debug why no data is arriving | [mqtt-ingest/logging.md](mqtt-ingest/logging.md) |

---

## System Architecture (Brief)

```
MQTT Brokers ─────────────────────────────────────────────────────┐
                                                                   ▼
EUMETSAT / WIS2BOX ──► wiz2box_forward/ ──► publish.py ──► MQTT Broker
                                                                   │
                                               mqtt_subscriber_timestream_output/
                                               __main__.py  (persistent service)
                                                     │  parses GeoJSON / CSIJSON
                                                     ▼
                                            TimescaleDB (PostgreSQL)
                                         ┌───────────────────────────┐
                                         │  per-station hypertables  │
                                         │  weather_data hypertable  │
                                         │  relational metadata      │
                                         └───────────────────────────┘
                                                     ▲
                                            Flask Dashboard (Gunicorn)
                                            mqtt_dashboard/
                                                     ▲
                                              Nginx (HTTPS proxy)
                                                     ▲
                                              User Browser
                                                     │
                                              Grafana (port 3000)
                                            (embedded via proxy)
```

Two systemd services run the long-lived processes:
- **`mqtt_subscriber`** — the ingest worker
- **`mqtt_dashboard`** — the Flask/Gunicorn web server

---

## Section Summaries

### [webapp/](webapp/README.md)
The Flask application users interact with. It manages MQTT brokers, station metadata, user accounts, groups, and permissions. It also serves as a transparent reverse-proxy for the Grafana visualisation tool. All web routes, database models, and authentication logic are documented here.

### [database/](database/README.md)
The storage layer. PostgreSQL with the TimescaleDB extension provides both relational metadata storage and high-performance time-series storage. This section explains every table, how hypertables work, how to connect, and how to perform backups and restores.

### [mqtt-ingest/](mqtt-ingest/README.md)
The `mqtt_subscriber_timestream_output` service. It runs continuously, connecting to one or more MQTT brokers, parsing incoming weather/sensor messages, and writing them to TimescaleDB. This section explains the full processing pipeline, supported message formats, how station IDs are inferred, and how the service logs its activity.

### [satellite-ingest/](satellite-ingest/README.md)
Scripts inside `wiz2box_forward/` that pull historical and live data from EUMETSAT via the WIS2BOX network, convert it to GeoJSON, and inject it into the MQTT broker so the subscriber can process it normally. This feeds data for stations that transmit via satellite rather than direct network.

### [utilities/](utilities/README.md)
One-off and periodic maintenance scripts at the repository root. These include tools for purging empty stations, counting data records, rebuilding Grafana dashboards, exporting metadata to CSV, and migrating the database schema. Redundant and outdated scripts are also identified here.
