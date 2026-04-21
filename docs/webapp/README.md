# Web Application — Overview

**Location:** `mqtt_dashboard/` (Python package)  
**Entry point:** `wsgi.py` (Gunicorn loads this)  
**Framework:** Flask + Flask-SQLAlchemy + Flask-Login  
**Served by:** Gunicorn (Unix socket) behind Nginx

---

## Contents

- [configuration.md](configuration.md) — `config.ini` key reference
- [auth.md](auth.md) — Login, signup, roles, and permissions
- [routes.md](routes.md) — Every URL endpoint explained
- [models.md](models.md) — ORM models and database relationships
- [grafana-integration.md](grafana-integration.md) — Auto-generated dashboards
- [ipc.md](ipc.md) — Shared memory IPC with the subscriber

---

## What the Web App Does

The Flask application serves two distinct purposes:

1. **Administrative UI** — Allows operators to manage MQTT brokers, station groups, user accounts, and individual measurement settings through a browser.
2. **Data API** — Provides JSON endpoints that the front-end JavaScript calls to fetch the latest sensor readings from TimescaleDB and display them on maps and tables.
3. **Grafana Proxy** — Transparently forwards all `/grafana/...` requests to the locally-running Grafana instance, rewriting URLs so the browser never needs direct access to port 3000.

---

## Package Layout

```
mqtt_dashboard/
├── __init__.py           App factory: creates Flask app, DB, shared memory, CORS
├── models.py             SQLAlchemy ORM models for all relational tables
├── grafana_helpers.py    Grafana HTTP API wrapper for dashboard management
├── create_mqtt_user.py   CLI script to create the first admin user
├── config.ini            Runtime configuration (DB credentials, keys, URLs)
├── settings/
│   └── threshold_settings.json   Per-measurement alert thresholds
├── auth/
│   └── auth.py           Login / logout / signup blueprint
├── main/
│   └── main.py           All data and admin routes (main blueprint)
├── static/               Static assets (JS, CSS, images)
│   ├── index.js
│   └── pwa/
└── templates/            Jinja2 HTML templates (see routes.md for which template
                          each route renders)
```

---

## How the App Boots

1. **Gunicorn** reads `wsgi.py`, which calls `mqtt_dashboard.create_app()`.
2. `create_app()` (in `__init__.py`):
   - Reads `mqtt_dashboard/config.ini` for Flask secret key, DB URI, and Grafana settings.
   - Initialises Flask-SQLAlchemy against the TimescaleDB connection string.
   - Initialises Flask-Login with the `auth.login` endpoint as the redirect target.
   - Configures CORS to allow XHR from localhost and the known server IP.
   - Attaches or creates the `"messages"` shared memory segment (IPC with subscriber).
   - Registers the `auth` and `main` blueprints.
3. Gunicorn forks N worker processes. Each worker independently opens a connection pool to Postgres.

> **Caution:** The shared memory segment is created at module import time, before workers fork. If the dashboard is restarted while the subscriber is running the segment already exists, so the app attaches to it. If the subscriber is also restarted, `messages` is re-created.

---

## Running in Development

```bash
cd /home/ubuntu/mqtt_dashboard
./venv/bin/python -m flask --app mqtt_dashboard --debug run --port 5000
```

Or directly:
```bash
./venv/bin/python wsgi.py
```

---

## Service Management

```bash
sudo systemctl status  mqtt_dashboard
sudo systemctl restart mqtt_dashboard
journalctl -u mqtt_dashboard -f       # follow live logs
```

---

## Navigation

← [docs/README.md](../README.md)
