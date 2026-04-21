"""
publish.py - Reads saved station .dat files and publishes them to the MQTT broker
             as GeoJSON messages, matching the format expected by __main__.py.

Usage:
    python3 publish.py                    # Publish all data from all stations
    python3 publish.py --hours 24         # Only publish records from the last N hours
    python3 publish.py --station LusakaAirport   # Only publish a specific station
    python3 publish.py --hours 6 --station LusakaAirport
"""

import os
import sys
import json
import time
import argparse
import pandas as pd
import paho.mqtt.client as mqtt
from datetime import datetime, timezone, timedelta

# MQTT Configuration
MQTT_BROKER   = "3.124.208.185"
MQTT_PORT     = 1883
MQTT_USERNAME = "wis2box"
MQTT_PASSWORD = "Wh00mqtt!"
MQTT_TOPIC_PREFIX = "data-incoming/zmb/campbell-v1"

# Paths
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
EUMETSAT_DIR  = os.path.join(BASE_DIR, "EUMETSAT")
STATIONS_CSV  = os.path.join(BASE_DIR, "stations.csv")

# Columns to skip when building the observations payload
SKIP_COLS = {
    'TIMESTAMP', 'RECORD', 'JobID', 'StationID',
    'WMO_Block', 'Station_ID', 'Station_Name', 'WMO_Station_Type',
    'M_Year', 'M_Month', 'M_DayOfMonth', 'M_HourOfDay', 'M_Minutes'
}


def read_dat_file(filepath):
    """Read a TOA5 .dat file (4 header rows) and return (df, headers, units)."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return None, [], []
    try:
        with open(filepath, 'r') as f:
            first = f.readline()
        if not first.startswith('"TOA5"'):
            print(f"  [SKIP] Not a valid TOA5 file: {filepath}")
            return None, [], []

        header_df = pd.read_csv(filepath, skiprows=1, nrows=2, header=None)
        headers = header_df.iloc[0].tolist()
        units   = header_df.iloc[1].tolist()

        df = pd.read_csv(filepath, skiprows=4, names=headers, low_memory=False)
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], errors='coerce')
        df = df.dropna(subset=['TIMESTAMP'])
        return df, headers, units
    except Exception as e:
        print(f"  [ERROR] Failed to read {filepath}: {e}")
        return None, [], []


def df_to_geojson_messages(df, headers, units, station_id, station_name, since=None):
    """
    Convert each timestamp row in df into a GeoJSON dict.
    Yields (iso_time, geojson_dict) per row.
    If `since` (datetime, UTC-aware) is provided, only rows after that time are yielded.
    """
    if since:
        # Ensure df timestamps are UTC-aware for comparison
        if df['TIMESTAMP'].dt.tz is None:
            ts_col = df['TIMESTAMP'].dt.tz_localize('UTC')
        else:
            ts_col = df['TIMESTAMP'].dt.tz_convert('UTC')
        df = df[ts_col > since].copy()

    if df.empty:
        return

    # Build a map of column -> unit for quick lookup
    unit_map = {h: u for h, u in zip(headers, units)}

    for _, row in df.iterrows():
        observation_names = []
        observations      = []
        observation_units = []

        lon, lat = 0.0, 0.0

        for col in headers:
            if col in SKIP_COLS:
                continue
            val = row.get(col)

            # Skip NaN
            try:
                if pd.isna(val):
                    continue
            except TypeError:
                pass

            # Convert numpy scalars to native Python
            if hasattr(val, 'item'):
                val = val.item()

            observation_names.append(col)
            observations.append(val)
            observation_units.append(unit_map.get(col) or "unitless")

            # Capture coordinates if present
            if col == 'Longitude':
                try:
                    lon = float(val)
                except Exception:
                    pass
            if col == 'Latitude':
                try:
                    lat = float(val)
                except Exception:
                    pass

        # Append station identifiers so __main__.py can derive station_id
        observation_names.extend(["Station_Name", "Station_ID"])
        observations.extend([station_name, station_id])
        observation_units.extend(["", ""])

        ts = row['TIMESTAMP']
        if hasattr(ts, 'isoformat'):
            if ts.tzinfo is None:
                iso_time = ts.isoformat() + "Z"
            else:
                iso_time = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            iso_time = str(ts) + "Z"

        geojson = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "observationNames": observation_names,
                "observationUnits": observation_units,
                "observations": {
                    iso_time: observations
                }
            }
        }

        yield iso_time, geojson


def publish_dataframe(client, topic, df, headers, units, station_id, station_name, since=None):
    """Publish all rows from df to the given MQTT topic."""
    published = 0
    skipped   = 0

    for iso_time, geojson in df_to_geojson_messages(df, headers, units, station_id, station_name, since):
        try:
            payload = json.dumps(geojson)
            client.publish(topic, payload, qos=0)
            published += 1
            print(f"    Published {iso_time}")
        except Exception as e:
            print(f"    [ERROR] {iso_time}: {e}")
            skipped += 1

    return published, skipped


def connect_mqtt():
    """Create, authenticate and connect an MQTT client."""
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client


def main():
    parser = argparse.ArgumentParser(description="Publish saved station .dat files to MQTT broker.")
    parser.add_argument('--hours',   type=float, default=None,
                        help='Only publish records newer than this many hours ago')
    parser.add_argument('--station', type=str,   default=None,
                        help='Only publish a specific station by WMO_Station_Name')
    args = parser.parse_args()

    since = None
    if args.hours is not None:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        print(f"Filtering: only records after {since.isoformat()}")

    if not os.path.exists(STATIONS_CSV):
        print(f"ERROR: stations.csv not found at {STATIONS_CSV}")
        sys.exit(1)

    stations_df = pd.read_csv(STATIONS_CSV)

    # Connect once and reuse for all stations
    try:
        print(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT} ...")
        client = connect_mqtt()
        print("Connected.\n")
    except Exception as e:
        print(f"ERROR: Failed to connect to MQTT broker: {e}")
        sys.exit(1)

    total_published = 0
    total_skipped   = 0

    for _, row in stations_df.iterrows():
        station_name = str(row['WMO_Station_Name']).strip()
        dcp_id       = str(row['DCP ID']).strip()
        wigos_id     = str(row['WMO_Station_ID(WIGOS ID)']).strip()
        station_id   = str(row['Last reported on last sat comms (LoggerStationID)']).strip()

        if not dcp_id or dcp_id == 'nan':
            continue
        if args.station and station_name.lower() != args.station.lower():
            continue

        station_folder  = os.path.join(EUMETSAT_DIR, f"{station_name}_DCP_{dcp_id}")
        hourly_file     = os.path.join(station_folder, f"{station_name}_TableHour.dat")
        synop_file      = os.path.join(station_folder, f"{station_name}_TableSYNOP.dat")

        topic = f"{MQTT_TOPIC_PREFIX}/{wigos_id}/data"
        print(f"Station: {station_name}  →  {topic}")

        # --- Hourly ---
        df_h, hdrs_h, units_h = read_dat_file(hourly_file)
        if df_h is not None and not df_h.empty:
            print(f"  [Hourly] {len(df_h)} rows in file")
            p, s = publish_dataframe(client, topic, df_h, hdrs_h, units_h, station_id, station_name, since)
            print(f"  [Hourly] Published {p}, skipped {s}")
            total_published += p
            total_skipped   += s
        else:
            print(f"  [Hourly] No data")

        # --- SYNOP ---
        df_s, hdrs_s, units_s = read_dat_file(synop_file)
        if df_s is not None and not df_s.empty:
            print(f"  [SYNOP]  {len(df_s)} rows in file")
            p, s = publish_dataframe(client, topic, df_s, hdrs_s, units_s, station_id, station_name, since)
            print(f"  [SYNOP]  Published {p}, skipped {s}")
            total_published += p
            total_skipped   += s
        else:
            print(f"  [SYNOP]  No data")

        print()

    # Allow the outgoing queue to drain before disconnecting
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    print(f"Done. Total published: {total_published}, total skipped: {total_skipped}")


if __name__ == "__main__":
    main()
