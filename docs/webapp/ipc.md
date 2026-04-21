# Shared Memory IPC (Inter-Process Communication)

The Flask dashboard and the MQTT subscriber are two separate OS processes. They communicate synchronously using a `multiprocessing.shared_memory.ShareableList` named `"messages"`.

---

## Why IPC?

When an operator adds, edits, or deletes an MQTT broker through the dashboard, the subscriber needs to:
- Disconnect from a removed broker
- Connect to a new broker
- Update credentials for an existing broker

Without IPC the operator would need to manually restart the `mqtt_subscriber` service. The shared memory mechanism allows live reconfiguration.

---

## The `messages` ShareableList

A `ShareableList` is a fixed-length list of primitive values stored in shared POSIX memory. It is created under the name `"messages"` so both processes can attach to the same block.

### Slots

| Index | Type | Description |
|-------|------|-------------|
| `messages[0]` | `bool` | **Flag.** Set to `True` by the dashboard to signal a pending change. The subscriber polls this and resets it to `False` after handling. |
| `messages[1]` | `int` | **Entity ID.** The `brokerID` of the affected broker. (`-1` = no pending action.) |
| `messages[2]` | `str` (1 char) | **Action.** `'N'` = new broker, `'E'` = edited, `'D'` = deleted, `'X'` = none |

---

## Lifecycle

### On dashboard startup (`mqtt_dashboard/__init__.py`)

```python
try:
    messages = shared_memory.ShareableList([False, int(-1), 'X'], name="messages")
except FileExistsError:
    messages = shared_memory.ShareableList(name="messages")
```

- If the segment does not exist yet (first boot), it is **created** with default values.
- If it already exists (subscriber started first, or dashboard restarted), it **attaches** to the existing segment.

### On subscriber startup (`mqtt_subscriber_timestream_output/__main__.py`)

```python
try:
    messages = shared_memory.ShareableList(name="messages")
except FileNotFoundError:
    messages = shared_memory.ShareableList([False, int(-1), 'X'], name="messages")
```

- If the dashboard is already running, the segment exists → **attach**.
- If the dashboard has not started yet → **create** so the subscriber can start independently.

### On broker mutation (dashboard routes in `main.py`)

When `/create_broker`, `/edit_broker`, or `/delete_broker` succeeds:

```python
messages[1] = broker_id     # which broker
messages[2] = 'N'           # or 'E' or 'D'
messages[0] = True          # signal: something changed
```

The flag is set **last** to ensure the ID and action are already written when the subscriber reads them.

### Subscriber polling (`broker_change_worker` thread)

The subscriber runs a dedicated `broker_change_worker` daemon thread:

```python
def broker_change_worker():
    while True:
        if messages[0]:
            messages[0] = False          # acknowledge
            broker_id = messages[1]
            action    = messages[2]
            # TODO: act on broker_id / action
```

> **Known limitation:** As of this documentation, `broker_change_worker` reads the flag and prints the change but does **not yet** dynamically add/remove broker connections. A full subscriber restart (`sudo systemctl restart mqtt_subscriber`) is still required to pick up broker changes. The IPC plumbing is correct but the handler body needs to call `add_broker()` / disconnect logic.

---

## Resource Tracker Monkey-Patch

Python's `multiprocessing.resource_tracker` automatically tracks shared memory segments and cleans them up when the process exits. This causes problems because:

- Both processes share the **same** segment.
- When one process exits, the tracker would destroy the segment, breaking the other process.

The subscriber applies a monkey-patch at startup:

```python
def remove_shm_from_resource_tracker():
    def fix_register(name, rtype):
        if rtype == "shared_memory":
            return
        ...
    resource_tracker.register = fix_register
    resource_tracker.unregister = fix_unregister
    if "shared_memory" in resource_tracker._CLEANUP_FUNCS:
        del resource_tracker._CLEANUP_FUNCS["shared_memory"]
```

This removes shared memory from the tracker so the segment persists across process restarts. See the [Python bug reference](https://bugs.python.org/issue38119) in the source.

**Result:** The shared memory segment persists for the lifetime of the OS, not the process. It must be manually cleaned only if you want to fully reset IPC state (`ipcrm -M`).

---

## Checking IPC State

```bash
# Check shared memory segments on the system
ipcs -m

# Expected: one segment named "messages"
# The "messages" ShareableList is backed by a file in /dev/shm/
ls /dev/shm/
# Should see: psm_messages (or similar)
```

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
