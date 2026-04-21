# Configuration Reference — `mqtt_dashboard/config.ini`

The web application reads a single `config.ini` file located at `mqtt_dashboard/config.ini`. **Neither** the Flask app nor the subscriber will function without it.

---

## Full File Reference

```ini
[Flask]
Secret Key = <random string>
```

| Key | Purpose | What happens if wrong |
|-----|---------|----------------------|
| `Secret Key` | Signs session cookies and CSRF tokens | All user sessions become invalid on restart; change it to force a global logout |

---

```ini
[App]
ApiBaseUrl = http://41.72.104.142:2543
```

| Key | Purpose |
|-----|---------|
| `ApiBaseUrl` | Base URL injected into every Jinja2 template as `api_base_url`. Used by JavaScript when it constructs API calls. Update this if the server IP or port changes. |

---

```ini
[Timescale]
DataBase   = mqtt_dashboard
Schema     = public
UserName   = postgres
Password   = campDashSQL
Host       = localhost
Port       = 5432
AdminDatabase = postgres
UseCurrentTimeAsTimestamp = False
```

| Key | Purpose |
|-----|---------|
| `DataBase` | PostgreSQL database name |
| `Schema` | Search path applied to every connection (`public` is standard) |
| `UserName` | PostgreSQL role |
| `Password` | PostgreSQL password |
| `Host` | Hostname/IP of the Postgres server (`localhost` if co-located) |
| `Port` | Default PostgreSQL port — change only if Postgres is on a non-standard port |
| `AdminDatabase` | Used by the subscriber to create the application database if it does not exist. Usually `postgres`. |
| `UseCurrentTimeAsTimestamp` | `False` = use the timestamp from the MQTT payload (recommended). `True` = use the server clock at the moment the message is processed. |

> **Important:** Both the Flask dashboard and the MQTT subscriber each have their own `config.ini` copy. They should have identical `[Timescale]` sections. If credentials differ, the subscriber will write data that the dashboard cannot read.

---

```ini
[MySQL]
UserName = postgres
Password = campDashSQL
Address  = localhost
DataBase = mqtt_dashboard
Port     = 5432
```

> **Note:** Despite the section name, this is **not** MySQL. This is a **legacy section name** from an earlier version of the project. The database is PostgreSQL. The `mySqlUtil.py` module in the subscriber also reads from this section as a fallback. These values should mirror the `[Timescale]` section.

---

```ini
[Grafana]
API_Key  = eyJr...
Address  = http://127.0.0.1
Port     = 3000
Subpath  = /grafana
```

| Key | Purpose |
|-----|---------|
| `API_Key` | Grafana service account token. Used for creating/deleting dashboards via the HTTP API. Found in Grafana → Configuration → API Keys. If expired, dashboard auto-creation will silently fail. |
| `Address` | URL (without port) of the Grafana instance. Always `http://127.0.0.1` unless Grafana is on a separate host. |
| `Port` | Grafana's HTTP port (default `3000`). |
| `Subpath` | The path prefix Grafana was configured to serve from. Set to `/grafana` if Grafana's `root_url` includes `/grafana`. Leave blank if Grafana is at root. |

> The subscriber's own config.ini has an equivalent `[Grafana]` section but with no `Subpath` key (it accesses Grafana directly on localhost and doesn't need the prefix).

---

## The Subscriber's `config.ini`

Located at `mqtt_subscriber_timestream_output/config.ini`. It has one additional section:

```ini
[MQTT]
Authentication = True
UserName       = ZMD
Password       = camp
Address        = 0.0.0.0
Port           = 2541
```

| Key | Purpose |
|-----|---------|
| `Authentication` | Whether the fallback broker requires a username/password |
| `UserName` / `Password` | Credentials for the fallback broker |
| `Address` | Broker IP used **only** if no brokers exist in the database |
| `Port` | Broker port for the fallback broker |

This fallback is used when no `brokers` rows exist in the database. Once at least one broker is added via the dashboard, these values are ignored.

---

## Where Config Values Are Read

| Section | Read by |
|---------|---------|
| `[Flask]` | `mqtt_dashboard/__init__.py` |
| `[App]` | `mqtt_dashboard/__init__.py` |
| `[Timescale]` | `mqtt_dashboard/__init__.py`, `mqtt_subscriber_timestream_output/configUtil.py` |
| `[MySQL]` | `mqtt_subscriber_timestream_output/configUtil.py` (fallback) |
| `[Grafana]` | `mqtt_dashboard/grafana_helpers.py`, `mqtt_subscriber_timestream_output/grafana_helpers.py` |
| `[MQTT]` | `mqtt_subscriber_timestream_output/configUtil.py` |
| `[Timestream]` | `mqtt_dashboard/__init__.py` — **legacy alias** for `[Timescale]`; kept for backward compatibility |

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
