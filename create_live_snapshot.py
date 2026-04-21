#!/usr/bin/env python3
"""
Create a Grafana snapshot with real data from PostgreSQL database for topic 1472.
"""
import requests
import json
import psycopg2
from datetime import datetime, timedelta

GRAFANA_URL = "http://localhost:3000"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="
DB_CONFIG = {
    'dbname': 'mqtt_dashboard',
    'user': 'postgres',
    'password': 'campDashSQL',
    'host': 'localhost',
    'port': 5432
}

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

def fetch_measure_data(measure_name, hours_back=24):
    """Fetch time series data for a specific measure from the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    query = """
        SELECT 
            EXTRACT(EPOCH FROM time) * 1000 as timestamp,
            measure_value_double
        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
        WHERE measure_name = %s
            AND time >= NOW() - INTERVAL '%s hours'
            AND measure_value_double IS NOT NULL
        ORDER BY time ASC
        LIMIT 1000
    """
    
    cur.execute(query, (measure_name, hours_back))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    # Convert to Grafana format: [value, timestamp]
    datapoints = [[float(row[1]), int(row[0])] for row in rows]
    return datapoints

def fetch_station_info():
    """Fetch station information."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    queries = {
        'Station_ID': "SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 WHERE measure_name='Station_ID' ORDER BY time DESC LIMIT 1",
        'Station_Name': "SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 WHERE measure_name='Station_Name' ORDER BY time DESC LIMIT 1"
    }
    
    info = {}
    for key, query in queries.items():
        cur.execute(query)
        result = cur.fetchone()
        info[key] = result[0] if result else 'N/A'
    
    cur.close()
    conn.close()
    return info

print("Fetching data from database...")

# Fetch key weather metrics
measures_to_fetch = [
    ('AirTempK', 'Air Temperature (K)'),
    ('RH', 'Relative Humidity (%)'),
    ('BP', 'Barometric Pressure (hPa)'),
    ('WSpeed', 'Wind Speed (m/s)')
]

panels_data = {}
for measure_name, display_name in measures_to_fetch:
    print(f"Fetching {display_name}...")
    datapoints = fetch_measure_data(measure_name, hours_back=24)
    print(f"  Got {len(datapoints)} data points")
    panels_data[measure_name] = datapoints

station_info = fetch_station_info()
print(f"\nStation: {station_info['Station_Name']} (ID: {station_info['Station_ID']})")

# Create panels with embedded data
panels = []

# Station info panel
panels.append({
    "type": "text",
    "gridPos": {"h": 4, "w": 24, "x": 0, "y": 0},
    "options": {
        "mode": "markdown",
        "content": f"# Weather Station Dashboard\n\n**Station:** {station_info['Station_Name']}  \n**Station ID:** {station_info['Station_ID']}  \n**Data Source:** Live PostgreSQL Data  \n**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    }
})

# Temperature panel
if panels_data['AirTempK']:
    panels.append({
        "type": "timeseries",
        "title": "Air Temperature (K)",
        "gridPos": {"h": 9, "w": 12, "x": 0, "y": 4},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "yellow"},
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "linear",
                    "lineWidth": 2,
                    "fillOpacity": 20,
                    "showPoints": "auto",
                    "spanNulls": False
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}]
                }
            }
        },
        "options": {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom"}
        },
        "targets": [{"refId": "A"}],
        "snapshotData": [{
            "fields": [
                {
                    "name": "Time",
                    "type": "time",
                    "values": [dp[1] for dp in panels_data['AirTempK']]
                },
                {
                    "name": "AirTempK",
                    "type": "number",
                    "values": [dp[0] for dp in panels_data['AirTempK']]
                }
            ]
        }]
    })

# Humidity panel
if panels_data['RH']:
    panels.append({
        "type": "timeseries",
        "title": "Relative Humidity (%)",
        "gridPos": {"h": 9, "w": 12, "x": 12, "y": 4},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "yellow"},
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "linear",
                    "lineWidth": 2,
                    "fillOpacity": 20,
                    "showPoints": "auto",
                    "spanNulls": False
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}]
                }
            }
        },
        "options": {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom"}
        },
        "targets": [{"refId": "A"}],
        "snapshotData": [{
            "fields": [
                {
                    "name": "Time",
                    "type": "time",
                    "values": [dp[1] for dp in panels_data['RH']]
                },
                {
                    "name": "RH",
                    "type": "number",
                    "values": [dp[0] for dp in panels_data['RH']]
                }
            ]
        }]
    })

# Pressure panel
if panels_data['BP']:
    panels.append({
        "type": "timeseries",
        "title": "Barometric Pressure (hPa)",
        "gridPos": {"h": 9, "w": 12, "x": 0, "y": 13},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "yellow"},
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "linear",
                    "lineWidth": 2,
                    "fillOpacity": 20,
                    "showPoints": "auto",
                    "spanNulls": False
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}]
                }
            }
        },
        "options": {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom"}
        },
        "targets": [{"refId": "A"}],
        "snapshotData": [{
            "fields": [
                {
                    "name": "Time",
                    "type": "time",
                    "values": [dp[1] for dp in panels_data['BP']]
                },
                {
                    "name": "BP",
                    "type": "number",
                    "values": [dp[0] for dp in panels_data['BP']]
                }
            ]
        }]
    })

# Wind Speed panel
if panels_data['WSpeed']:
    panels.append({
        "type": "timeseries",
        "title": "Wind Speed (m/s)",
        "gridPos": {"h": 9, "w": 12, "x": 12, "y": 13},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "yellow"},
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "linear",
                    "lineWidth": 2,
                    "fillOpacity": 20,
                    "showPoints": "auto",
                    "spanNulls": False
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}]
                }
            }
        },
        "options": {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom"}
        },
        "targets": [{"refId": "A"}],
        "snapshotData": [{
            "fields": [
                {
                    "name": "Time",
                    "type": "time",
                    "values": [dp[1] for dp in panels_data['WSpeed']]
                },
                {
                    "name": "WSpeed",
                    "type": "number",
                    "values": [dp[0] for dp in panels_data['WSpeed']]
                }
            ]
        }]
    })

# Create snapshot
snapshot_data = {
    "dashboard": {
        "title": f"Weather Station - {station_info['Station_Name']}",
        "panels": panels,
        "editable": False,
        "hideControls": False,
        "time": {
            "from": "now-24h",
            "to": "now"
        },
        "timepicker": {},
        "timezone": "browser",
        "schemaVersion": 16,
        "version": 0
    },
    "name": f"Weather Station {station_info['Station_ID']}",
    "expires": 0  # Never expires
}

print("\nCreating snapshot...")
response = requests.post(
    f"{GRAFANA_URL}/api/snapshots",
    headers=headers,
    data=json.dumps(snapshot_data)
)

if response.status_code == 200:
    result = response.json()
    snapshot_key = result.get('key')
    snapshot_url = result.get('url')
    delete_key = result.get('deleteKey')
    
    print(f"\n✓ Snapshot created successfully!")
    print(f"  Key: {snapshot_key}")
    print(f"  URL: {GRAFANA_URL}{snapshot_url}?kiosk=tv&orgId=1")
    print(f"  Delete Key: {delete_key}")
    
    # Update database with new snapshot key
    print("\nUpdating database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "UPDATE timestream_tables SET ss_key = %s WHERE tableID = 1472",
        (snapshot_key,)
    )
    conn.commit()
    cur.close()
    conn.close()
    print("✓ Database updated!")
    
    print(f"\nView at: http://127.0.0.1:2543/topic/1472")
    
else:
    print(f"\n✗ Failed to create snapshot")
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text}")
