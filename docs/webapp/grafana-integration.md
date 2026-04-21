# Grafana Integration

**Files:**  
- `mqtt_dashboard/grafana_helpers.py` (dashboard app version)  
- `mqtt_subscriber_timestream_output/grafana_helpers.py` (subscriber version)

---

## Overview

Both the Flask dashboard and the MQTT subscriber can create and update Grafana dashboards automatically. They call the Grafana HTTP API using a service account Bearer token.

The two files are separate because:
- The dashboard version imports Flask-SQLAlchemy models (`mqtt_dashboard.models`).
- The subscriber version imports the raw SQLAlchemy session from `mySqlUtil.py`.

Both files share the same JSON panel templates and dashboard-building logic.

---

## Configuration

In `config.ini`:

```ini
[Grafana]
API_Key  = eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0=
Address  = http://127.0.0.1
Port     = 3000
Subpath  = /grafana      # dashboard version only
```

The subscriber's `grafana_helpers.py` constructs:
```
grafana_url = "http://127.0.0.1:3000"
```

The dashboard's `grafana_helpers.py` constructs:
```
grafana_url = "http://127.0.0.1:3000/grafana"
```

> If the API key expires, dashboard auto-creation fails silently. Check that the key is still valid in Grafana → Configuration → API Keys.

---

## Datasource UID

Grafana requires a datasource UID when defining panel queries. The dashboard version resolves this at runtime:

```python
def _get_datasource_uid() -> str:
    r = requests.get(url=f"{grafana_url}/api/datasources", headers=header, timeout=5)
    for dsource in r.json():
        if dsource["type"] in ["postgres", "grafana-postgresql-datasource"]:
            return dsource['uid']
    return ""
```

The subscriber version resolves it at import time (module-level code) and caches the value.

> If Grafana is not running when the subscriber starts, `d_uid` will be empty string `""`. Any dashboards created in this state will not display data. Restart the subscriber after Grafana is running to fix this.

---

## Table Name Normalisation

Both files share (or replicate) the same logic to convert an MQTT topic to a PostgreSQL identifier:

```python
def _normalize_table_name(topic: str) -> str:
    name = topic.lower().replace('/', '_').replace('-', '_')
    return name[:63]
```

**Critical:** Both files must use the same normalisation so Grafana SQL queries reference the correct table names. If they differ, panels will show "no data".

---

## `create_dashboard_table(table, session)`

The primary function. Called whenever:
- A new topic is first seen (subscriber detects it)
- A measurement is edited, added, or made visible/hidden (dashboard routes)
- The user manually triggers a dashboard rebuild

### What it does:

1. If the topic already has a `db_uid`, delete the old Grafana dashboard first:
   ```
   DELETE /api/dashboards/uid/<old_uid>
   ```
2. Query all `timestream_measurement` rows for this topic where `visible=1`.
3. For each measurement, clone the appropriate panel template and fill in:
   - The SQL query (using the correct `st_<station_id>` table name)
   - The panel title (`nickname` if set, otherwise `name`)
   - The grid position (two-column layout, stacked vertically)
4. POST the complete dashboard JSON to `/api/dashboards/db`.
5. Save the returned `uid` back to `timestream_table.db_uid`.

### Panel Types

| `graph` column | Panel type | SQL generated |
|----------------|------------|---------------|
| `LINE` | Time series (`timeseries`) | `SELECT time, measure_value_double as value FROM ... WHERE measure_name='...' ORDER BY time` |
| `ROSE` | Wind rose (`fatcloud-windrose-panel`) | JOIN of direction + speed measurements over time |
| (any other, type=`VARCHAR`) | Table panel | `SELECT max(time) as time, measure_value_varchar as value FROM ... WHERE measure_name='...'` |
| (any other, status=1, type=`DOUBLE`) | Table panel | `SELECT max(time) as time, measure_value_double as value FROM ...` |

> The wind-rose panel requires the `fatcloud-windrose-panel` plugin installed in Grafana. If it is missing, the panel displays a configuration error but the dashboard loads otherwise.

---

## `update_snapshot_table(table, session)`

Creates a saved Grafana snapshot (a static copy of a dashboard). Used for the `/user` view.

1. If no dashboard exists yet, calls `create_dashboard_table` first.
2. If there is a previous snapshot (`ss_key`), deletes it: `DELETE /api/snapshots/<key>`.
3. Fetches the live dashboard JSON: `GET /api/dashboards/uid/<db_uid>`.
4. Posts it as a snapshot: `POST /api/snapshots`.
5. Returns the snapshot key and updates `timestream_table.ss_key`.

---

## `update_snapshot_user(user)`

Creates a combined snapshot for a user containing all their accessible stations.

---

## The Dashboard JSON Template

```python
dashboard_template = {
    "dashboard": {
        "editable": True,
        "panels": [...],        # filled with panel_template_* clones
        "title": "<topic>",
        "uid": None,            # Grafana assigns this on creation
        "refresh": False,       # auto-refresh disabled by default
        "timezone": "browser",
        ...
    }
}
```

The dashboard is posted to Grafana's `/api/dashboards/db` endpoint. Setting `"id": None` forces a new dashboard to be created.

---

## Debugging Grafana Integration

**Symptom: "No data" in panels**
1. Check the Grafana datasource: Grafana → Configuration → Data Sources → PostgreSQL. Test the connection.
2. Check `db_uid` on the topic row: empty string means no dashboard was ever created.
3. Check the API key in `config.ini` → `[Grafana]` → `API_Key`.
4. Run `rebuild_dashboards.py` to force-recreate all dashboards.
5. Check the subscriber logs for "Grafana update failed" warnings.

**Symptom: Wind rose panel shows error**
- The `fatcloud-windrose-panel` Grafana plugin is not installed. Install via `grafana-cli plugins install fatcloud-windrose-panel` and restart Grafana.

**Symptom: Dashboard created but title is wrong**
- The topic is stored with slashes `data/incoming/...` but the dashboard title replaces `_` with `/`. This is cosmetic only.

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
