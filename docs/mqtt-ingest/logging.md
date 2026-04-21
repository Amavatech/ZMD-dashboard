# Logging — Subscriber Service

The subscriber uses a custom logging setup that organises log files by hour and also reports runtime statistics and monitors for silent periods.

---

## Log File Location

```
logs/
└── YYYY-MM/
    └── DD/
        └── HH.log
```

**Example:** A message processed at 14:32 on 2026-04-17 is written to:
```
logs/2026-04/17/14.log
```

This keeps log files manageable — each file covers exactly one hour, so even high-throughput systems produce files of predictable size.

### Accessing Logs

```bash
# Today's current hour
cat logs/$(date +%Y-%m/%d/%H).log

# Last 24 hours
ls logs/$(date +%Y-%m)/$(date +%d)/

# Follow in real time (via systemd)
journalctl -u mqtt_subscriber -f

# Follow the file directly
tail -f logs/$(date +%Y-%m/%d/%H).log
```

---

## `HourlyDirHandler`

A custom `logging.FileHandler` subclass defined in `__main__.py`.

```python
class HourlyDirHandler(logging.FileHandler):
    def emit(self, record):
        now = datetime.utcnow()
        new_path = f"logs/{now.strftime('%Y-%m/%d/%H')}.log"
        if new_path != self.baseFilename:
            self.close()
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            self.baseFilename = new_path
            self.stream = self._open()
        super().emit(record)
```

On every log write, it checks if the clock has moved to a new hour. If so, it closes the current log file and opens a new one. This happens automatically without any scheduler or cron job.

---

## stdout/stderr Redirection — `StreamToLogger`

Because the subscriber runs as a systemd service with output captured by journald, a `StreamToLogger` adapter redirects Python's `sys.stdout` and `sys.stderr` into the logging system:

```python
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)
```

This means print statements and uncaught tracebacks appear in the hourly log files as normal log entries.

---

## Stats Reporter — `stats_reporter()`

A background thread that runs every 2 minutes (120 seconds):

```python
def stats_reporter():
    while True:
        time.sleep(120)
        with stats_lock:
            r = received_counter
            p = processed_counter
            received_counter = 0
            processed_counter = 0
        logger.info(f"[STATS] Received: {r}, Processed: {p} (last 120s)")
```

**What it tells you:**
- If `Received` is large and `Processed` is small → the processing thread is falling behind (unlikely but indicates a problem).
- If both are 0 → no messages arrived in the last 2 minutes (normal at night; alarming during business hours).
- If `Received` exceeds 1000 in 2 minutes → messages may be getting dropped from the queue.

The `stats_lock` is a `threading.Lock()` to prevent a race condition where the counter is being incremented at the same moment the reporter reads it.

---

## Silence Watchdog — `silence_watchdog()`

A background thread that monitors for periods where no messages arrive. If no new message is processed for 15 minutes (900 seconds), it logs a warning:

```python
def silence_watchdog():
    while True:
        time.sleep(60)
        if time.time() - last_message_time > 900:
            logger.warning("[WATCHDOG] No messages received in 15 minutes!")
```

`last_message_time` is updated (to `time.time()`) every time `on_message()` is called.

This watchdog is important for detecting:
- Network partition between the server and the MQTT broker.
- MQTT broker going offline.
- Stations all going silent simultaneously (power outage, etc.).

The watchdog does **not** attempt automatic reconnection. It only logs. The actual reconnection is handled by paho-mqtt's built-in reconnect logic in `loop_start()`.

---

## Log Level Configuration

The log level is set in code (not in `config.ini`). The default level is `INFO`. To debug a specific issue:

1. Edit `__main__.py`:
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```
2. Restart the subscriber: `sudo systemctl restart mqtt_subscriber`
3. Check logs in `logs/$(date +%Y-%m/%d/%H).log`

Common DEBUG-level messages include: raw payload strings, individual fields parsed, hypertable `CREATE TABLE` SQL, Grafana API response bodies.

---

## Crash Tracking

Unhandled exceptions in the main thread will be caught by the `sys.stderr` redirect and appear as ERROR-level log entries with full tracebacks. Systemd's `Restart=always` setting then restarts the subscriber automatically.

To check for recent crashes:
```bash
journalctl -u mqtt_subscriber --since "1 hour ago" | grep -i error
```

---

## Navigation

← [mqtt-ingest/README.md](README.md) | [docs/README.md](../README.md)
