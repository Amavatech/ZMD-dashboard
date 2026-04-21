# Web Dashboard (`mqtt_dashboard`)

A Flask-based administrative and visualization interface for the MQTT data pipeline. It manages broker configurations, station metadata, user access control, and proxies Grafana dashboards.

## Package Structure

```
mqtt_dashboard/
├── __init__.py          # App factory, shared memory init, CORS, logging
├── models.py            # SQLAlchemy ORM models
├── grafana_helpers.py   # Grafana HTTP API integration
├── create_mqtt_user.py  # CLI script for seeding an initial user
├── config.ini           # Flask, database, and Grafana configuration
├── auth/
│   └── auth.py          # Authentication blueprint (login / logout / signup)
├── main/
│   └── main.py          # Core blueprint — all data and admin routes
├── static/              # CSS, JavaScript, images
├── templates/           # Jinja2 HTML templates
└── settings/
    └── threshold_settings.json  # Per-measurement alert thresholds
```

---

## Application Factory (`__init__.py`)

`create_app()` initialises:
- **Flask-SQLAlchemy** — connects to TimescaleDB using credentials from `config.ini`
- **Flask-Login** — session-based authentication
- **Flask-CORS** — restricted to localhost and the known server IP
- **Shared memory** — creates (or attaches to) the `messages` ShareableList for IPC with the subscriber

### IPC via Shared Memory

The dashboard communicates configuration changes to the MQTT subscriber without a service restart by writing to a `multiprocessing.shared_memory.ShareableList` named `"messages"`:

| Index | Type    | Purpose                                              |
|-------|---------|------------------------------------------------------|
| `[0]` | `bool`  | Flag — set `True` to signal a change; subscriber resets to `False` |
| `[1]` | `int`   | ID of the modified entity (e.g. `brokerID`)          |
| `[2]` | `char`  | Action: `'N'` new, `'E'` edit, `'D'` delete, `'X'` none |

---

## Configuration (`config.ini`)

| Section      | Key fields                                              |
|--------------|---------------------------------------------------------|
| `[Flask]`    | `Secret Key`                                            |
| `[Timescale]`| `Host`, `Port`, `UserName`, `Password`, `DataBase`, `Schema` |
| `[Grafana]`  | `Address`, `Port`, `Subpath`, `API_Key`                 |
| `[App]`      | `ApiBaseUrl`                                            |

---

## Data Models (`models.py`)

All models use Flask-SQLAlchemy and map to the PostgreSQL metadata schema.

| Model                    | Table                    | Purpose                                              |
|--------------------------|--------------------------|------------------------------------------------------|
| `User`                   | `users`                  | Dashboard users (email, hashed password, name)       |
| `broker`                 | `brokers`                | MQTT broker connection details                       |
| `timestream_table`       | `timestream_tables`      | Registry of MQTT topics / weather stations           |
| `timestream_measurement` | `timestream_measurements`| Per-topic sensor definitions (units, graph type, visibility) |
| `permission`             | `permissions`            | RBAC linking users to topics or groups               |
| `group`                  | `groups`                 | Named collections of topics                          |

### Key relationships
- A `broker` has many `timestream_table` records.
- A `timestream_table` has many `timestream_measurement` records and belongs to one `group`.
- A `User` has many `permission` records; each permission is either `TOPIC`, `GROUP`, `ALL_TOPIC`, or `ADMIN`/`GADMIN`.

---

## Blueprints & Routes

### Auth blueprint (`/`)

| Route              | Method | Description               |
|--------------------|--------|---------------------------|
| `/login`           | GET    | Login page                |
| `/login`           | POST   | Authenticate and redirect |
| `/signup`          | GET    | Registration page         |
| `/signup`          | POST   | Create new user           |
| `/logout`          | GET    | Invalidate session        |

Admin status is determined by the presence of an `ADMIN`, `GADMIN`, or `GROUP_ADMIN` permission type on the user.

### Main blueprint (`/`)

#### Station data (read)

| Route                              | Method | Description                                             |
|------------------------------------|--------|---------------------------------------------------------|
| `/`                                | GET    | Home — redirects to the appropriate dashboard view      |
| `/topic/<tid>`                     | GET    | View all measurements for a topic                       |
| `/group/<gid>`                     | GET    | View all topics in a group                              |
| `/combined_data/<table_name>`      | GET    | JSON: all measurements from a topic table               |
| `/airport_data/<table_name>`       | GET    | JSON: airport-specific data view                        |
| `/airport_data_fetch`              | GET    | JSON: latest readings for airport UI                    |
| `/airport_data_fetch_10m`          | GET    | JSON: last 10-minute readings                           |
| `/station_time/<table_name>`       | GET    | JSON: most recent timestamp for a station               |
| `/topic_stations`                  | GET    | JSON: all stations accessible to the current user       |
| `/get_all_tables`                  | GET    | JSON: all topic tables                                  |
| `/groups_with_topics`              | GET    | JSON: all groups and their member topics                |

#### User views

| Route             | Method | Description                           |
|-------------------|--------|---------------------------------------|
| `/user`           | GET    | Current user info                     |
| `/standard_user`  | GET    | Standard user dashboard               |
| `/group_user`     | GET    | Group-scoped user dashboard           |
| `/admin_user`     | GET    | Admin user management view            |
| `/admin_user_data`| GET    | JSON: user and permission data        |
| `/sub_admin`      | GET    | Sub-admin view                        |
| `/airport_ui`     | GET    | Airport-specific dashboard            |
| `/ekland_ui`      | GET    | Ekland-specific dashboard             |
| `/ekland_pwa`     | GET    | Ekland PWA                            |
| `/geoss_stations` | GET    | GEOSS stations map view               |
| `/threshold_settings` | GET | Threshold configuration UI          |
| `/pwa`            | GET    | Progressive Web App shell             |

#### Admin routes

| Route                   | Method | Description                                          |
|-------------------------|--------|------------------------------------------------------|
| `/admin`                | GET    | Main admin panel                                     |
| `/admin_v2`             | GET    | Admin panel v2                                       |
| `/admin_endpoint`       | GET    | JSON: admin data endpoint                            |
| `/dashboard_admin`      | GET    | Grafana dashboard management                         |
| `/broker_admin`         | GET    | Broker management view                               |
| `/group_admin`          | GET    | Group management view                                |
| `/group_admin_route`    | GET    | JSON: group admin data                               |
| `/admin_group_data`     | GET    | JSON: group + topic assignments                      |

#### Mutation routes (POST)

| Route                     | Description                                      |
|---------------------------|--------------------------------------------------|
| `/create_broker`          | Add a new MQTT broker (signals subscriber via IPC) |
| `/edit_broker`            | Update broker details (signals subscriber via IPC) |
| `/delete_broker`          | Remove a broker (signals subscriber via IPC)     |
| `/create_user`            | Create a new user account                        |
| `/delete_user`            | Delete a user                                    |
| `/create_group`           | Create a topic group                             |
| `/delete_group`           | Delete a group                                   |
| `/add_table_to_group`     | Assign a topic to a group                        |
| `/remove_table_from_group`| Remove a topic from a group                      |
| `/add_perm`               | Grant a user a permission                        |
| `/remove_perm` / `/delete_perm` | Revoke a permission                      |
| `/remove_topic`           | Delete a topic and its measurements              |
| `/edit_measurement`       | Update measurement name, unit, graph type, etc.  |
| `/search`                 | Search topics                                    |
| `/search_brokers`         | Search brokers                                   |
| `/perms`                  | Query permissions for a user                     |
| `/unadded` / `/added`     | Topics not yet / already in a group              |
| `/save_threshold`         | Persist threshold settings to `threshold_settings.json` |
| `/get_threshold_settings` | Read threshold settings                          |

#### Grafana proxy

| Route                   | Methods                               | Description                                          |
|-------------------------|---------------------------------------|------------------------------------------------------|
| `/grafana/<path:path>`  | GET, POST, PUT, DELETE, PATCH, OPTIONS | Transparent proxy to the Grafana HTTP API           |

---

## Grafana Integration (`grafana_helpers.py`)

Wraps the Grafana HTTP API to automate dashboard lifecycle management. Called by both the dashboard and the subscriber when new topics or measurements are discovered.

Key functions:
- `_get_datasource_uid()` — resolves the PostgreSQL datasource UID at runtime
- `_normalize_table_name(topic)` — converts a topic string to a valid hypertable name (matches subscriber logic)
- Panel template builders — construct time-series, bar-chart, and wind-barb panels from `timestream_measurement` records
- Dashboard create/update helpers — push JSON dashboard definitions to Grafana via the API

Configuration is read from `mqtt_dashboard/config.ini` under the `[Grafana]` section.

---

## Templates

Located in `mqtt_dashboard/templates/`. Key templates:

| Template             | Purpose                                       |
|----------------------|-----------------------------------------------|
| `base.html`          | Base layout with navigation                   |
| `login.html`         | Login form                                    |
| `signup.html`        | Registration form                             |
| `admin.html`         | Full admin panel                              |
| `broker_admin.html`  | Broker CRUD UI                                |
| `group_admin.html`   | Group management UI                           |
| `dashboard_admin.html` | Grafana dashboard trigger UI               |
| `standard_user.html` | Regular user station view                     |
| `group.html`         | Group view                                    |
| `airport_app.html`   | Airport-specific view                         |
| `ekland_pwa.html`    | Ekland PWA shell                              |
| `geoss_stations.html`| GEOSS map                                     |
| `index.html`         | Landing/home redirect                         |

---

## Service

The Flask app is served by **Gunicorn** via the `wsgi.py` entry point at the repo root.

```ini
# /etc/systemd/system/mqtt_dashboard.service
[Service]
ExecStart=/home/ubuntu/mqtt_dashboard/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:mqtt_dashboard.sock \
    -m 007 \
    wsgi:app
```

Follow live logs:
```bash
journalctl -u mqtt_dashboard -f
```
