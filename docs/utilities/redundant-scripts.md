# Redundant and Obsolete Scripts

This document catalogues files that are no longer needed, are outdated versions of current code, or serve no operational purpose. They are kept in the repository for historical reference but should not be used in normal operation.

---

## Deprecated Modules

### `mqtt_subscriber_timestream_output/TimeStreamUtil.py`

**Status: DEPRECATED — DO NOT USE**

This file is the remnant of the original AWS Timestream integration (the system's name derives from this). It contains a stub that raises `RuntimeError` if any of its functions are called:

```python
raise RuntimeError(
    "TimeStreamUtil is deprecated and no longer functional. "
    "Use timescaleUtil.py instead."
)
```

**Why it still exists:** Historical reference — shows what the original data store was.  
**Action:** Safe to delete. The live code uses `timescaleUtil.py`.

---

## Obsolete Admin UI Templates

The `mqtt_dashboard/templates/` folder contains several superseded versions of the admin template:

| File | Status | Notes |
|------|--------|-------|
| `admin-previous.html` | **OBSOLETE** | An older version of the admin UI kept for reference. Not served by any route. |
| `admin-working.html` | **OBSOLETE** | An intermediate "working" version during development. Not served. |
| `admin-gideons-original.html` | **OBSOLETE** | The original template before customisation. Not served. |

These files are large HTML templates that take up space and can confuse future developers. **They are safe to delete** once the current `admin.html` is confirmed to be working correctly.

### Broken Route

The Flask blueprint in `mqtt_dashboard/main/main.py` contains an `/admin_v2` route that references a template `admin-official.html`:

```python
@main.route('/admin_v2')
def admin_v2():
    return render_template('admin-official.html', ...)
```

This file does **not exist** in `templates/`. Accessing `/admin_v2` will raise a `TemplateNotFound` error.

**Action:** Either create `admin-official.html` as an alias for `admin.html`, or remove the `/admin_v2` route entirely.

---

## Duplicate Files

### `mqtt_dashboard/sub_admin.html`

A copy of the admin template sits inside the package root at `mqtt_dashboard/sub_admin.html`. This is separate from the `templates/` subfolder. The Flask template loader looks in `templates/` by default; this file is never loaded.

**Action:** Safe to delete.

---

## Dead Code in `__main__.py`

### `if False:` State Topic Block

In `mqtt_subscriber_timestream_output/__main__.py`, there is a block wrapped in `if False:`:

```python
if False:
    # State topic handler — disabled
    # This was an attempt to handle a 'state' topic from WIS2Box
    # that indicated broker connectivity status.
    def on_state_message(client, userdata, msg):
        ...
```

This block **never executes**. It was a partial implementation of a feature that was not completed.

**Action:** Remove the `if False:` block to clean up the file. Does not affect any functionality.

---

## One-Off / Single-Station Scripts

### `create_panels_270.py`

A one-off script that hardcodes `table_id = 270` to rebuild Grafana panels for a specific station:

```python
if __name__ == "__main__":
    create_panels_for_topic(270)   # hard-coded table ID
```

This was written to fix one station's dashboard during a specific incident. It has no general utility and will fail if the station with `tableid=270` no longer exists.

**Action:** Safe to delete. Use `rebuild_dashboards.py` for rebuilding all dashboards.

---

## Development / Test Artifacts

### `create_static_snapshot.py`

A development script for creating non-live Grafana snapshots. Used during initial development to test the snapshot API. Not part of the operational workflow.

**Action:** Low priority. Keep for reference or delete.

### `create_test_snapshot.py`

A throwaway test script used to verify the snapshot endpoint. Hard-codes temporary values.

**Action:** Safe to delete.

### `wiz2box_forward/test_dryrun.py` and `test_import_single.py`

Development test scripts for `import.py`. Useful for debugging the import pipeline on a single station without running the full import.

**Action:** Keep — useful for debugging but should be moved to a `tests/` subdirectory.

### `wiz2box_forward/migrate_to_public_schema.py`

A one-time migration script that moved hypertables from a custom schema to `public`. Already executed during the 2026-03 migration period.

**Action:** Safe to delete (the migration is complete). Keep if you want a historical record.

---

## Legacy Directory: `mqtt_subscriber_publisher/`

This folder is named "publisher" but is actually a **development test publisher** — a script that generates and publishes fake MQTT messages to test the subscriber pipeline.

```
mqtt_subscriber_publisher/
└── __main__.py   # Generates test messages and publishes to MQTT
```

**It is NOT a production service.** It is not managed by systemd. The name is misleading — it will never process or forward real sensor data.

**Action:** Clearly document this as a dev tool. If it is no longer needed for development, it can be removed.

---

## Old Export Files

The `exports/` folder accumulates CSV files from every run of the database maintenance scripts. Old exports from the 2026-02 and 2026-03 migration period are no longer needed:

```
exports/
├── non_exempt_stations_20260301_*.csv    # Pre-migration analysis
├── station_counts_20260301_*.csv         # Pre-migration analysis
└── no_data_stations_20260302_*.csv       # Post-migration cleanup
```

**Action:** Delete any `exports/*.csv` file older than 30 days. They are not referenced by any code.

---

## Summary Table

| Item | Location | Risk if Deleted | Recommended Action |
|------|----------|----------------|-------------------|
| `TimeStreamUtil.py` | subscriber | None (raises error if used) | Delete |
| `admin-previous.html` | templates/ | None | Delete |
| `admin-working.html` | templates/ | None | Delete |
| `admin-gideons-original.html` | templates/ | None | Delete |
| `sub_admin.html` | mqtt_dashboard/ | None | Delete |
| `/admin_v2` route | main.py | 500 error if hit | Remove or fix template |
| `if False:` block | __main__.py | None | Remove |
| `create_panels_270.py` | root | None | Delete |
| `create_static_snapshot.py` | root | None | Delete or keep as reference |
| `create_test_snapshot.py` | root | None | Delete |
| `migrate_to_public_schema.py` | wiz2box_forward/ | None | Delete |
| Old exports (>30 days) | exports/ | None | Delete |

---

## Navigation

← [utilities/README.md](README.md) | [docs/README.md](../README.md)
