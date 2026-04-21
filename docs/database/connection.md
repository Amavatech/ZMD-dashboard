# Connecting to the Database

---

## Connection Details (Default)

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `mqtt_dashboard` |
| User | `postgres` |
| Password | `campDashSQL` |
| Schema | `public` |

> These defaults come from `config.ini`. If they have been changed on your installation, use the values from the file.

---

## Connect via Terminal (psql)

```bash
PGPASSWORD=campDashSQL psql -h localhost -U postgres -d mqtt_dashboard
```

Or set a persistent environment variable for the session:
```bash
export PGPASSWORD=campDashSQL
psql -h localhost -U postgres -d mqtt_dashboard
```

Once connected, you are in the `mqtt_dashboard` database. The search path defaults to `public`, so you can reference tables without a schema prefix.

---

## Useful psql Commands

```sql
-- List all tables (relational metadata)
\dt

-- List all hypertables (TimescaleDB time-series)
SELECT hypertable_name FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'public' ORDER BY hypertable_name;

-- Describe a table's columns
\d timestream_tables
\d "st_LusakaAirport"

-- Count rows
SELECT COUNT(*) FROM brokers;
SELECT COUNT(*) FROM timestream_tables;
SELECT COUNT(*) FROM timestream_measurements;

-- Exit psql
\q
```

---

## How the Application Connects

### Flask Dashboard (`mqtt_dashboard/__init__.py`)

```python
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
    f"?options=-csearch_path%3D{schema}"
)
```

Flask-SQLAlchemy maintains a connection pool (typically one connection per Gunicorn worker). The `search_path` is set to `public` via the connection string parameter.

### MQTT Subscriber (`mqtt_subscriber_timestream_output/timescaleUtil.py`)

Uses psycopg2's `SimpleConnectionPool` (1–10 connections):

```python
_pool = pool.SimpleConnectionPool(
    1, 10,
    user=config.timescale.username,
    password=config.timescale.password,
    host=config.timescale.host,
    port=config.timescale.port,
    dbname=config.timescale.database,
)
```

The subscriber also maintains a separate SQLAlchemy session (`mySqlUtil.py`) for reading/writing metadata.

### Schema Enforcement

Both connection methods set `search_path=public` explicitly. This ensures all `CREATE TABLE`, `SELECT`, and `INSERT` statements operate in the `public` schema regardless of the Postgres user's default.

---

## Connecting from Another Machine

By default, PostgreSQL on Ubuntu only accepts localhost connections. To connect remotely:

1. Edit `/etc/postgresql/<version>/main/pg_hba.conf` to add a host entry.
2. Edit `/etc/postgresql/<version>/main/postgresql.conf` → `listen_addresses = '*'`.
3. Open port 5432 in the firewall (`ufw allow 5432`).
4. Restart PostgreSQL: `sudo systemctl restart postgresql`.

> **Security note:** Only do this on a private network or with SSL. Use a firewall to restrict which IPs can reach port 5432.

---

## Connection String Formats

For external tools (pgAdmin, DBeaver, etc.):

```
Host:     localhost (or server IP)
Port:     5432
Database: mqtt_dashboard
User:     postgres
Password: campDashSQL
SSL:      disable (or prefer if SSL is configured)
```

SQLAlchemy URL format:
```
postgresql+psycopg2://postgres:campDashSQL@localhost:5432/mqtt_dashboard
```

---

## Navigation

← [database/README.md](README.md) | [docs/README.md](../README.md)
