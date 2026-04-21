# Testing and Development Scripts

---

## `test_queries.py`

**Location:** `test_queries.py` (project root)  
**Purpose:** Ad-hoc database query testing. Used during development to verify query correctness without going through the web API.

```bash
python3 test_queries.py
```

This script connects directly to `mqtt_dashboard` and runs hardcoded queries — typically the same queries the Flask API uses. Modify it to test specific scenarios.

---

## `mqtt_subscriber_publisher/` — Test MQTT Publisher

**Location:** `mqtt_subscriber_publisher/__main__.py`  
**Purpose:** Generates fake weather station messages and publishes them to an MQTT broker. Used to test the subscriber pipeline without needing real station hardware.

```bash
python3 -m mqtt_subscriber_publisher
```

### What It Publishes

The script generates random or preset sensor values and publishes them as GeoJSON messages to the configured topic. This allows end-to-end testing of:

1. MQTT receive → queue → `message_to_timescale()` pipeline
2. New station creation (metadata + hypertable)
3. Grafana dashboard auto-creation
4. IPC reload behaviour

### Configuration

Uses its own `config.ini` (or falls back to the subscriber's config). The MQTT broker target and topic prefix are set at the top of `__main__.py`.

> **Do not run this against a production broker** unless you want test data in your production database. Use a local or dev broker.

---

## `wiz2box_forward/test_dryrun.py`

**Purpose:** Runs the `import.py` logic in dry-run mode — reads `.dat` files and prints what would be inserted without actually writing to the database.

```bash
python3 wiz2box_forward/test_dryrun.py
```

Useful for:
- Verifying that a new station's `.dat` file is parseable.
- Checking what timestamps would be inserted.
- Debugging TOA5 format issues before a real import.

---

## `wiz2box_forward/test_import_single.py`

**Purpose:** Runs the `import.py` logic for a single specified station, with full database writes. Used to test the import pipeline on one station without processing all stations.

```bash
python3 wiz2box_forward/test_import_single.py
```

Edit the station name / topic at the top of the script before running.

---

## Manual End-to-End Test

To manually test the full pipeline from MQTT to Grafana:

1. **Start services:**
   ```bash
   sudo systemctl start mqtt_dashboard mqtt_subscriber
   ```

2. **Publish a test message:**
   ```bash
   # Install mosquitto-clients if not present
   apt install mosquitto-clients
   
   mosquitto_pub -h 3.124.208.185 -p 1883 \
     -u wis2box -P Wh00mqtt! \
     -t "data-incoming/zmb/campbell-v1/TestStation/data" \
     -m '{"type":"Feature","geometry":{"type":"Point","coordinates":[28.0,-15.0]},"properties":{"station_id":"TestStation","phenomenon_time":"2026-04-17T10:00:00Z","observationNames":["Temp"],"observationUnits":["C"],"observations":[22.5]}}'
   ```

3. **Check it was ingested:**
   ```bash
   PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard \
     -c "SELECT * FROM public.\"st_TestStation\" ORDER BY time DESC LIMIT 5;"
   ```

4. **Check Grafana dashboard was created:**
   - Open `http://localhost:3000/grafana` (or via reverse proxy).
   - Look for a new dashboard named after the station.

5. **Clean up:**
   ```bash
   PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard \
     -c "DELETE FROM timestream_tables WHERE station_id = 'TestStation'; DROP TABLE IF EXISTS public.\"st_TestStation\";"
   ```

---

## Checking the IPC Shared Memory State

After triggering a broker change in the admin UI, verify the IPC signal was sent:

```bash
# List all shared memory segments
ipcs -m

# If the subscriber is running, "messages" should appear
# You can also check the subscriber logs:
journalctl -u mqtt_subscriber -f
```

---

## Navigation

← [utilities/README.md](README.md) | [docs/README.md](../README.md)
