# MQTT Dashboard and Data Ingestion System

A real-time weather and sensor data pipeline. MQTT messages are ingested from multiple brokers, stored in TimescaleDB, and presented through a Flask administrative dashboard with Grafana visualisation.

## Full Documentation

Comprehensive documentation for this system lives in the [`docs/`](docs/README.md) folder.

**→ [docs/README.md](docs/README.md) — Start here**

The documentation tree covers:

| Section | Link | What's inside |
|---------|------|--------------|
| Web Application | [docs/webapp/](docs/webapp/README.md) | Routes, models, auth, IPC, Grafana integration |
| Database | [docs/database/](docs/database/README.md) | Schema, hypertables, backups, connections |
| MQTT Ingest | [docs/mqtt-ingest/](docs/mqtt-ingest/README.md) | Pipeline, message formats, broker management, logging |
| Satellite Ingest | [docs/satellite-ingest/](docs/satellite-ingest/README.md) | EUMETSAT download, direct import, re-publish |
| Utilities | [docs/utilities/](docs/utilities/README.md) | Maintenance scripts, Grafana tools, redundant files |

---

## Data Flow

```
MQTT Brokers → MQTT Subscriber → TimescaleDB ← Flask Dashboard ← User Browser
                                              ↑
                                         Grafana
```

---

## System Components

### 1. MQTT Subscriber (`mqtt_subscriber_timestream_output`)
A persistent background service that subscribes to all configured MQTT brokers, parses incoming GeoJSON and CSIJSON messages, and writes time-series data to TimescaleDB. It auto-creates hypertables and Grafana dashboards when new topics are discovered, and live-reloads broker configuration via shared memory without restarting.

See → [mqtt_subscriber_timestream_output/README.md](mqtt_subscriber_timestream_output/README.md)

### 2. Web Dashboard (`mqtt_dashboard`)
A Flask application (served by Gunicorn) providing the administrative UI and a JSON API. Manages broker records, station metadata, user accounts, RBAC permissions, and group assignments. Communicates configuration changes to the subscriber via a `multiprocessing.shared_memory` IPC channel.

See → [mqtt_dashboard/README.md](mqtt_dashboard/README.md)

### 3. Reverse Proxy (Nginx)
Routes HTTPS traffic to the Gunicorn Unix socket.

### 4. Grafana
Visualisation layer. Dashboards are created and updated automatically by both the subscriber (when new topics arrive) and the dashboard (via `grafana_helpers.py`). The Flask app also proxies Grafana API calls from the browser at `/grafana/<path>`.

---

## Service Management

Two `systemd` services run the long-lived processes:

| Service | Description |
|---------|-------------|
| `mqtt_dashboard` | Gunicorn serving the Flask web app |
| `mqtt_subscriber` | MQTT subscriber and TimescaleDB ingestion worker |

```bash
# Common operations — replace <service> with mqtt_dashboard or mqtt_subscriber
sudo systemctl status  <service>
sudo systemctl start   <service>
sudo systemctl stop    <service>
sudo systemctl restart <service>
journalctl -u <service> -f           # follow live logs
journalctl -u <service> -n 50        # last 50 lines
```

Stop both at once:
```bash
sudo systemctl stop mqtt_dashboard mqtt_subscriber
```

---

## Installation (Ubuntu)

### 1. System dependencies
```bash
sudo apt update
sudo apt install python3-pip python3-venv nginx postgresql libpq-dev -y
```

### 2. Virtual environment
```bash
cd /home/ubuntu/mqtt_dashboard
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

### 3. Systemd service files

#### `/etc/systemd/system/mqtt_dashboard.service`
```ini
[Unit]
Description=Gunicorn instance to serve mqtt_dashboard
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/mqtt_dashboard
Environment="PATH=/home/ubuntu/mqtt_dashboard/venv/bin"
ExecStart=/home/ubuntu/mqtt_dashboard/venv/bin/gunicorn --workers 3 --bind unix:mqtt_dashboard.sock -m 007 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

#### `/etc/systemd/system/mqtt_subscriber.service`
```ini
[Unit]
Description=MQTT Subscriber Timestream Output
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/mqtt_dashboard
Environment="PATH=/home/ubuntu/mqtt_dashboard/venv/bin"
ExecStart=/home/ubuntu/mqtt_dashboard/venv/bin/python3 /home/ubuntu/mqtt_dashboard/mqtt_subscriber_timestream_output/__main__.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mqtt_dashboard.service mqtt_subscriber.service
sudo systemctl start  mqtt_dashboard.service mqtt_subscriber.service
```

### 4. Nginx

Create `/etc/nginx/sites-available/mqtt_dashboard`:

```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/mqtt_dashboard/mqtt_dashboard.sock;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/mqtt_dashboard /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `mqtt_dashboard/config.ini` | Flask secret key, TimescaleDB URI, Grafana address and API key |
| `mqtt_subscriber_timestream_output/config.ini` | MQTT broker defaults, TimescaleDB connection, timestamp mode |

### Database connection (defaults)
```bash
PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard
```

---

## Troubleshooting

- **Service not starting**: `journalctl -u <service> -n 50` — check for import errors or missing config keys.
- **Gunicorn socket permissions**: The `Group=www-data` and `-m 007` flag ensure Nginx can read the `.sock` file.
- **Subscriber not picking up new brokers**: Verify the shared memory segment exists (`ipcs -m`) and that `messages[0]` is being set by the dashboard route handler.
- **Subscriber log files**: Written under `mqtt_subscriber_timestream_output/logs/YYYY-MM/DD/HH.log` with hourly rotation.


#### MQTT Credentials
The system supports multiple MQTT brokers configured in the database. The subscriber connects to all configured brokers simultaneously.

**Default/Fallback Settings** (from `mqtt_subscriber_timestream_output/config.ini`):
- **Username**: `ZMD`
- **Password**: `camp`
- **Broker**: `0.0.0.0`
- **Port**: `2541`

**Active Brokers** (configured in database):
- **MAIN**: `13.246.171.60:1883` - Username: `user1`, Password: `123456`
- **ZAMBIA**: `3.124.208.185:1883` - Username: `wis2box`, Password: `Wh00mqtt!`
- **ZIMBABWE**: `136.156.88.41:1883` - Username: `wis2box`, Password: `jaGJJHkh246`
- **ESWATINI**: `3.77.214.70:1883` - Username: `wis2box`, Password: `Eswatini123!!`
- **NAMIBIA**: `52.59.143.117:1883` - Username: `wis2box`, Password: `79739NBDGS`

To view current brokers:
```bash
PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard -c "SELECT name, url, port, username FROM brokers;"
```

#### Timestream Layout (Database Schema)
The system uses the following core tables to manage data routing and measurements:

1.  **`brokers`**: Configuration for MQTT brokers (URL, port, authentication).
2.  **`timestream_tables`**: Maps MQTT topics to specific data tables.
    *   `topic`: The subscribed MQTT topic.
    *   `latitude`/`longitude`: Station coordinates.
3.  **`timestream_measurements`**: Defines specific metrics (e.g., Temperature, Humidity) within a topic.
    *   `name`: The key in the incoming JSON message.
    *   `unit`: The unit of measurement.
    *   `type`: Data type (e.g., `DOUBLE`).
4.  **`users`**: Administrative accounts for the dashboard.
5.  **`permissions`**: Link users to specific station groups or topics.

### Static Assets and PWA
The `ekland_pwa/` directory contains files for the Progressive Web App version of the dashboard, which can be served independently or integrated into the main web service.
