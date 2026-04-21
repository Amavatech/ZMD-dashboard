# Broker Management

This document covers how MQTT broker connections are configured, started, and updated at runtime.

---

## How Brokers Are Stored

Broker connection details live in the `brokers` relational table:

| Column | Example | Purpose |
|--------|---------|---------|
| `brokerid` | `1` | Primary key |
| `name` | `"Main WMO Broker"` | Display name in the UI |
| `url` | `"3.124.208.185"` | Hostname or IP address |
| `port` | `1883` | MQTT port (1883 = plain, 8883 = TLS) |
| `authentication` | `True` | Whether to send a username/password |
| `username` | `"camp_user"` | MQTT username |
| `password` | `"s3cr3t"` | MQTT password (stored plain text) |

Managed via the admin UI at `/broker_admin`.

---

## Startup: `add_broker(brokerid)`

On process start, the subscriber calls `add_broker()` for every row in the `brokers` table:

```python
def add_broker(brokerid):
    broker = mySqlUtil.get_broker(brokerid)
    client = mqtt.Client()
    if broker.authentication:
        client.username_pw_set(broker.username, broker.password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker.url, broker.port, keepalive=60)
    client.loop_start()   # Starts a background thread for this broker
    broker_clients[brokerid] = client
```

Each broker runs in its own `paho-mqtt` network thread. All threads share the same `on_message()` callback and the same `message_queue` deque.

---

## Subscription Topics

In `on_connect()`, the client subscribes to all configured topics for that broker:

```python
def on_connect(client, userdata, flags, rc):
    tables = mySqlUtil.get_tables_for_broker(broker_id)
    for table in tables:
        for topic in table.topics:
            client.subscribe(topic, qos=0)
    # Also subscribe to wildcard if configured:
    client.subscribe("data-incoming/#", qos=0)
```

QoS 0 = "at most once" — messages may be lost if the broker or subscriber restarts during a burst. QoS 1 would guarantee delivery but is not currently used.

---

## Live Reload via IPC

When an admin adds, edits, or deletes a broker via the web UI, the Flask app writes to the shared memory `messages` list:

```python
messages[1] = broker_id     # Which broker changed
messages[2] = 'N'           # 'N' (new), 'E' (edit), 'D' (delete)
messages[0] = True          # Set last (triggers the subscriber)
```

The subscriber's main loop polls `messages[0]` every second:

```python
while True:
    if messages[0]:
        broker_id = messages[1]
        action    = messages[2]
        messages[0] = False  # Acknowledge
        broker_change_worker(broker_id, action)
    time.sleep(1)
```

### `broker_change_worker(broker_id, action)`

| Action | Behaviour |
|--------|-----------|
| `'N'` (New) | Calls `add_broker(broker_id)` to connect and subscribe |
| `'D'` (Delete) | Calls `remove_broker(broker_id)`: `client.loop_stop()`, `client.disconnect()`, removes from `broker_clients` dict |
| `'E'` (Edit) | Calls `remove_broker()` then `add_broker()` (disconnect and reconnect with new settings) |
| `'X'` (None) | No action (used when the signal is cleared) |

> **Known limitation:** The `broker_change_worker` is implemented, but depending on version, the reconnection on 'E' action may not re-subscribe to the existing topic list. If a broker edit doesn't take effect immediately, restart the subscriber service.

---

## Managing Subscriptions for New Topics

When a new `timestream_tables` row is created (either from the UI or automatically by the subscriber on first message), the subscriber needs to subscribe to the new topic.

Currently this is handled by:
1. The wildcard subscription `"data-incoming/#"` catches new topics automatically if they share the same prefix.
2. For non-wildcard topics, a broker reload (via IPC action `'E'`) causes `on_connect` to resubscribe all topics.

---

## Broker Connection Resilience

paho-mqtt's `loop_start()` runs a background thread that:
- Automatically sends MQTT PINGREQ keepalives every 60 seconds.
- Reconnects on connection drop using an exponential backoff.
- Calls `on_connect` again after a successful reconnect, which triggers re-subscription.

If a broker is unreachable at startup, paho-mqtt attempts to connect in the background and logs connection errors. The subscriber continues processing messages from other brokers.

---

## Multiple Brokers

All broker clients share:
- The same `on_message()` handler.
- The same `message_queue` deque.
- The same ingestion worker thread.

There is no per-broker routing in the queue. The `topic` string in each queued item implicitly identifies which broker sent it, but the ingestion function doesn't need to know which broker was the source.

---

## Adding a Broker from Scratch

1. Log in as an admin and go to `/broker_admin`.
2. Click "Add Broker" and fill in the URL, port, and credentials.
3. Save. The Flask app writes to the IPC shared memory.
4. The subscriber receives the signal and calls `add_broker()`.
5. The new broker connects and subscribes.

No service restart required.

---

## Navigation

← [mqtt-ingest/README.md](README.md) | [docs/README.md](../README.md)
