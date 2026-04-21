import datetime
import logging
from typing import Iterable, List, Optional, Tuple

import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import execute_values

import configUtil as config

_pool: Optional[pool.SimpleConnectionPool] = None
_schema_name: str = getattr(config.timescale, "schema", "public")


def _normalize_table_name(name: str) -> str:
    if not name:
        return name
    normalized = name.lower().replace("-", "_")[:63]
    if normalized != name.lower().replace("-", "_"):
        logging.warning("Timescale table name truncated: requested=%s resolved=%s", name, normalized)
    return normalized


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            1,
            10,
            user=config.timescale.username,
            password=config.timescale.password,
            host=config.timescale.host,
            port=config.timescale.port,
            dbname=config.timescale.database,
        )
    return _pool


def _get_conn():
    return _get_pool().getconn()


def _put_conn(conn):
    _get_pool().putconn(conn)


def _exec_admin(sql_text: str, params: Optional[Iterable] = None) -> None:
    conn = psycopg2.connect(
        dbname=config.timescale.admin_database,
        user=config.timescale.username,
        password=config.timescale.password,
        host=config.timescale.host,
        port=config.timescale.port,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql_text, params)
    finally:
        conn.close()


def ensure_database() -> None:
    try:
        conn = psycopg2.connect(
            dbname=config.timescale.admin_database,
            user=config.timescale.username,
            password=config.timescale.password,
            host=config.timescale.host,
            port=config.timescale.port,
        )
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.timescale.database,))
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(config.timescale.database)))
        finally:
            conn.close()
    except Exception as err:
        logging.warning("Timescale database check/create failed: %s", err)


def ensure_extension() -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        conn.commit()
    finally:
        _put_conn(conn)


def create_table(dbName: str, tblName: str) -> None:
    ensure_database()
    ensure_extension()
    tblName = _normalize_table_name(tblName)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {table} (
                        time TIMESTAMPTZ NOT NULL,
                        measure_name TEXT NOT NULL,
                        measure_value_double DOUBLE PRECISION NULL,
                        measure_value_varchar TEXT NULL,
                        unit TEXT NULL,
                        measurement_type TEXT NULL
                    );
                    """
                ).format(table=sql.Identifier(_schema_name, tblName))
            )
            cur.execute(
                "SELECT create_hypertable(%s, %s, if_not_exists => TRUE);",
                (f"{_schema_name}.{tblName}", "time"),
            )
            cur.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {idx} ON {table} (measure_name, time DESC);"
                ).format(
                    idx=sql.Identifier(f"{tblName}_measure_time_idx"),
                    table=sql.Identifier(_schema_name, tblName),
                )
            )
        conn.commit()
    finally:
        _put_conn(conn)


def ensure_weather_data_table(schema: str = None) -> None:
    if not schema:
        schema = _schema_name
    ensure_database()
    ensure_extension()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {schema}.weather_data (
                        time TIMESTAMPTZ NOT NULL,
                        station_id TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        value DOUBLE PRECISION NULL
                    );
                    """
                ).format(schema=sql.Identifier(schema))
            )
            cur.execute(
                "SELECT create_hypertable(%s, %s, if_not_exists => TRUE);",
                (f"{schema}.weather_data", "time"),
            )
            cur.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {idx} ON {schema}.weather_data (station_id, metric, time DESC);"
                ).format(
                    idx=sql.Identifier("weather_data_station_metric_time_idx"),
                    schema=sql.Identifier(schema),
                )
            )
        conn.commit()
    finally:
        _put_conn(conn)


def write_weather_data(rows: List[Tuple[datetime.datetime, str, str, Optional[float]]], schema: str = None) -> None:
    if not rows:
        return
    if not schema:
        schema = _schema_name
    ensure_weather_data_table(schema=schema)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                sql.SQL(
                    "INSERT INTO {schema}.weather_data (time, station_id, metric, value) VALUES %s"
                ).format(schema=sql.Identifier(schema)),
                rows,
            )
        conn.commit()
        logging.info("Saved %s records to weather_data", len(rows))
    finally:
        _put_conn(conn)


def _parse_dimensions(dimensions: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    unit = None
    measurement_type = None
    for dim in dimensions or []:
        if dim.get("Name") == "unit":
            unit = dim.get("Value")
        elif dim.get("Name") == "Measurement Type":
            measurement_type = dim.get("Value")
    return unit, measurement_type


def write_records(dbName: str, tblName: str, records: List[dict]) -> None:
    if not records:
        return
    tblName = _normalize_table_name(tblName)
    # Ensure table exists in case metadata is out of sync
    create_table(dbName, tblName)

    rows = []
    for record in records:
        measure_name = record.get("MeasureName")
        measure_type = record.get("MeasureValueType")
        measure_value = record.get("MeasureValue")
        unit, measurement_type = _parse_dimensions(record.get("Dimensions", []))
        if measurement_type is None:
            measurement_type = measure_type

        ts_raw = record.get("Time")
        if ts_raw is None:
            dt = datetime.datetime.now(datetime.timezone.utc)
        else:
            ts_ms = int(ts_raw)
            dt = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=datetime.timezone.utc)

        value_double = None
        value_varchar = None
        if measure_type == "DOUBLE":
            try:
                value_double = float(measure_value)
            except (TypeError, ValueError):
                value_varchar = str(measure_value)
        else:
            value_varchar = str(measure_value)

        rows.append((dt, measure_name, value_double, value_varchar, unit, measurement_type))

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                sql.SQL(
                    "INSERT INTO {table} (time, measure_name, measure_value_double, measure_value_varchar, unit, measurement_type) VALUES %s"
                ).format(table=sql.Identifier(_schema_name, tblName)),
                rows,
            )
        conn.commit()
        logging.info("Saved %s records to Timescale table %s", len(rows), tblName)
    finally:
        _put_conn(conn)
