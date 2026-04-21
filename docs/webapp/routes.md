# Route Reference

**File:** `mqtt_dashboard/main/main.py` (main blueprint) and `mqtt_dashboard/auth/auth.py` (auth blueprint)

All routes require `@login_required` unless explicitly marked as **public**.

---

## Auth Routes

| Method | URL | Template / Response | Notes |
|--------|-----|---------------------|-------|
| GET | `/login` | `login.html` | Public |
| POST | `/login` | Redirect → `/` | Authenticates user |
| GET | `/signup` | `signup.html` | Public |
| POST | `/signup` | Redirect → `/login` | Creates user account |
| GET | `/logout` | Redirect → `/login` | Ends session |

---

## Landing / User Views

### `GET /`  
Inspects the logged-in user's permissions and redirects to the appropriate dashboard. See [auth.md — Login Redirect](auth.md) for the full decision tree.

### `GET /user`  
Renders `index.html` with a Grafana snapshot URL. Creates/refreshes a Grafana snapshot for the current user's stations.

### `GET /standard_user`  
Returns JSON: list of topic `tableID`s the user has `TOPIC` permission for.  
Used by `standard_user.html` JavaScript to load the map.

### `GET /group_user`  
Returns JSON: list of `tableID`s for all topics in the user's `GROUP`.  
Used by `group_user.html` JavaScript.

### `GET /admin_user`  
Renders `admin_user.html` — admin's user management view.

### `GET /admin_user_data`  
Returns JSON: all users with their assigned tables, coordinates, group names.  
Admin only (403 otherwise).

### `GET /sub_admin`  
Renders `company_admin.html` — a sub-admin view with users, tables, and groups listed. Admin only.

### `GET /geoss_stations`  
Renders `geoss_stations.html` — a Leaflet map showing all GEOSS stations. Login required.

### `GET /airport_ui`  
Renders `wind-barb.html` — the aviation-specific display (Polokwane AWOS).

### `GET /ekland_ui`  
Renders `layout.html` for the Ekland-specific view.

### `GET /ekland_pwa`  
Renders `ekland_pwa.html` — the Ekland Progressive Web App shell.

### `GET /threshold_settings`  
Renders `group_accordion.html` — the per-measurement alert threshold configuration UI.

### `GET /pwa` *(public)*  
Serves `static/pwa/index.html` directly. No auth required.

---

## Station Data API

### `GET /combined_data/<table_name>`  
Returns JSON with merged data from both:
- The relational database (station metadata, group, coordinates)
- TimescaleDB (latest `measure_value_double`/`varchar` per measurement)

`table_name` can be a numeric `tableID` or a topic string. If the per-station hypertable does not exist, it falls back to the shared `weather_data` table.

**Response shape:**
```json
{
  "data": {
    "relational_data": { "name": "...", "longitude": ..., ... },
    "timescale_data": [[null, null, "measure_name", "timestamp", "value"], ...]
  }
}
```

### `GET /airport_data/<table_name>`  
Same as `combined_data` but does not include `latest_per_measure`; returns the last 8 records per query.

### `GET /airport_data_fetch`  
Hardcoded query for Polokwane AWOS airport station (`56192`). Returns last 15 minutes of specific aviation measurements (QFE, QNH, wind speed/direction, cloud layers, etc.).

### `GET /airport_data_fetch_10m`  
Same station as above but returns last 28 records of 10-minute wind/temp/pressure readings.

### `GET /station_time/<table_name>`  
Returns the single most recent record from a table. Used by the UI to show "last seen" times.

### `GET /groups_with_topics` *(public-ish — no admin check)*  
Returns JSON: all groups mapped to their list of station/table names.

### `GET /topic_stations`  
Admin only. Returns JSON: all topics with their ID and group assignment.

---

## Topic and Group Views

### `GET /topic/<tid>`  
Renders `index.html` embedding the Grafana live dashboard for the topic identified by `tableID = tid`. Checks that the current user has permission (GROUP, TOPIC, ALL_TOPIC, or ADMIN). The Grafana URL is proxied through `/grafana/...`.

### `GET /group/<gid>`  
Renders `group.html` — shows all topics in the group. Checks GROUP, ALL_TOPIC, or ADMIN permission.

---

## Admin Panel Views

All require ADMIN or GROUP_ADMIN permission.

| Method | URL | Template | Description |
|--------|-----|----------|-------------|
| GET | `/admin` | `admin.html` | Main admin panel (users, tables, groups) |
| GET | `/admin_v2` | `admin-official.html` | **⚠ References missing template** (see [utilities/redundant-scripts.md](../utilities/redundant-scripts.md)) |
| GET | `/admin_endpoint` | JSON | Raw admin data as JSON |
| GET | `/dashboard_admin` | `dashboard_admin.html` | Trigger Grafana dashboard regeneration |
| GET | `/broker_admin` | `broker_admin.html` | MQTT broker management UI |
| GET | `/group_admin` | `group_admin.html` | Topic group management UI |
| GET | `/group_admin_route` | JSON | Group ID for current user |
| GET | `/admin_group_data` | JSON | All users with group assignments |

---

## Mutation Endpoints (POST)

All require admin permission unless noted.

### Broker Management

| URL | Body | Description |
|-----|------|-------------|
| `/create_broker` | `{url, port, authentication, username, password, name}` | Creates a new broker row and signals subscriber via IPC (`action='N'`) |
| `/edit_broker` | `{brokerID, url, port, ...}` | Updates broker and signals subscriber (`action='E'`) |
| `/delete_broker` | `{brokerID}` | Deletes broker and signals subscriber (`action='D'`) |

> All broker mutations write to the `messages` shared memory list so the subscriber reacts immediately without a restart. See [ipc.md](ipc.md).

### User Management

| URL | Body | Description |
|-----|------|-------------|
| `/create_user` | `{email, name, password}` | Creates user with hashed password |
| `/delete_user` | `{userID}` | Deletes user and all their permissions |

### Permission Management

| URL | Body | Description |
|-----|------|-------------|
| `/add_perm` | `{userID, type, tableID?, groupID?}` | Grants a permission |
| `/remove_perm` | `{permissionID}` | Revokes a permission |
| `/delete_perm` | `{permissionID}` | Alias for remove_perm |
| `/perms` | `{searchval: userID}` | Returns all permissions for a user |

### Group Management

| URL | Body | Description |
|-----|------|-------------|
| `/create_group` | `{name}` | Creates a new topic group |
| `/delete_group` | `{groupID}` | Deletes group; sets all members' groupID to 0 |
| `/groups` | `{}` | Returns all groups |
| `/add_table_to_group` | `{tableID, groupID}` | Assigns a topic to a group |
| `/remove_table_from_group` | `{tableID}` | Removes topic from its group (sets groupID=0) |
| `/unadded` | `{}` | Topics with no group assigned |
| `/added` | `{searchval: groupID}` | Topics in a specific group |

### Topic Management

| URL | Body | Description |
|-----|------|-------------|
| `/remove_topic` | `{tableID}` | Deletes topic row, measurements, and permissions from DB (does **not** drop hypertable) |
| `/edit_measurement` | `{measurementID, name?, unit?, graph?, visible?, nickname?}` | Updates measurement metadata; triggers Grafana dashboard refresh |

### Threshold Settings

| URL | Body | Description |
|-----|------|-------------|
| `/save_threshold` | `{station, sensorSettings, lowThreshold, highThreshold, timeDelay}` | Writes threshold to `settings/threshold_settings.json` |
| `/get_threshold_settings` (GET) | — | Reads `threshold_settings.json` and returns it as JSON |

### Search

| URL | Body | Description |
|-----|------|-------------|
| `/search` | `{searchval}` | Search users by name or email |
| `/search_brokers` | `{searchval}` | Search brokers by name or URL |

---

## Grafana Proxy

### `ANY /grafana/<path>`  
Transparently forwards all methods (GET, POST, PUT, DELETE, PATCH, OPTIONS) to `http://127.0.0.1:3000/grafana/<path>`. Rewrites `http://localhost:3000` strings in HTTP response bodies so browser API calls route back through this proxy instead of failing on the unreachable port.

This makes it possible for the browser to embed and interact with Grafana dashboards without the user needing direct access to port 3000.

---

## Data Flow for a Station View

1. User navigates to `/topic/42`.
2. Flask renders `index.html` with a Grafana URL like `/grafana/d/<uid>?kiosk=tv&...`.
3. Browser loads the page; JavaScript calls `/combined_data/42` for metadata + latest readings.
4. The Grafana iframe is loaded via the proxy at `/grafana/d/<uid>`.
5. Grafana queries TimescaleDB directly (it has its own data source configured).

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
