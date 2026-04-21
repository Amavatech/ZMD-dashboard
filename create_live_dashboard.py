#!/usr/bin/env python3
"""
Create a new Grafana dashboard with properly configured panels for live PostgreSQL data.
"""
import requests
import json
import psycopg2

GRAFANA_URL = "http://localhost:3000"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="
DATASOURCE_UID = "az2bN8Svz"
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

# Get station info
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute("SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 WHERE measure_name='Station_Name' ORDER BY time DESC LIMIT 1")
station_name = cur.fetchone()[0] if cur.rowcount > 0 else "Weather Station"
cur.close()
conn.close()

# Create dashboard with proper time series queries
dashboard = {
    "dashboard": {
        "title": f"Live Weather Data - {station_name}",
        "tags": ["weather", "live"],
        "timezone": "browser",
        "schemaVersion": 37,
        "version": 0,
        "refresh": "5s",  # Auto-refresh every 5 seconds
        "time": {
            "from": "now-6h",
            "to": "now"
        },
        "timepicker": {
            "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
        },
        "panels": [
            # Station Info Panel
            {
                "id": 1,
                "type": "stat",
                "title": "Station Information",
                "gridPos": {"h": 4, "w": 24, "x": 0, "y": 0},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [{
                    "refId": "A",
                    "format": "table",
                    "rawSql": "SELECT measure_value_varchar as \"Station Name\" FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 WHERE measure_name='Station_Name' ORDER BY time DESC LIMIT 1"
                }],
                "options": {
                    "reduceOptions": {
                        "values": False,
                        "calcs": ["lastNotNull"]
                    },
                    "orientation": "auto",
                    "textMode": "value_and_name",
                    "colorMode": "value",
                    "graphMode": "none",
                    "justifyMode": "auto"
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [{"color": "blue", "value": None}]
                        }
                    }
                }
            },
            # Air Temperature Panel
            {
                "id": 2,
                "type": "timeseries",
                "title": "Air Temperature (K)",
                "gridPos": {"h": 9, "w": 12, "x": 0, "y": 4},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [{
                    "refId": "A",
                    "format": "time_series",
                    "rawSql": """SELECT 
  time AS "time",
  measure_value_double AS "Temperature"
FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
WHERE 
  measure_name = 'AirTempK'
  AND $__timeFilter(time)
ORDER BY time""",
                    "rawQuery": True
                }],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "kelvin"
                    }
                },
                "options": {
                    "tooltip": {"mode": "single", "sort": "none"},
                    "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True}
                }
            },
            # Relative Humidity Panel
            {
                "id": 3,
                "type": "timeseries",
                "title": "Relative Humidity (%)",
                "gridPos": {"h": 9, "w": 12, "x": 12, "y": 4},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [{
                    "refId": "A",
                    "format": "time_series",
                    "rawSql": """SELECT 
  time AS "time",
  measure_value_double AS "Humidity"
FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
WHERE 
  measure_name = 'RH'
  AND $__timeFilter(time)
ORDER BY time""",
                    "rawQuery": True
                }],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "percent",
                        "min": 0,
                        "max": 100
                    }
                },
                "options": {
                    "tooltip": {"mode": "single", "sort": "none"},
                    "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True}
                }
            },
            # Barometric Pressure Panel
            {
                "id": 4,
                "type": "timeseries",
                "title": "Barometric Pressure (hPa)",
                "gridPos": {"h": 9, "w": 12, "x": 0, "y": 13},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [{
                    "refId": "A",
                    "format": "time_series",
                    "rawSql": """SELECT 
  time AS "time",
  measure_value_double AS "Pressure"
FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
WHERE 
  measure_name = 'BP'
  AND $__timeFilter(time)
ORDER BY time""",
                    "rawQuery": True
                }],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "pressurehpa"
                    }
                },
                "options": {
                    "tooltip": {"mode": "single", "sort": "none"},
                    "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True}
                }
            },
            # Wind Speed Panel
            {
                "id": 5,
                "type": "timeseries",
                "title": "Wind Speed (m/s)",
                "gridPos": {"h": 9, "w": 12, "x": 12, "y": 13},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [{
                    "refId": "A",
                    "format": "time_series",
                    "rawSql": """SELECT 
  time AS "time",
  measure_value_double AS "Wind Speed"
FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
WHERE 
  measure_name = 'WSpeed'
  AND $__timeFilter(time)
ORDER BY time""",
                    "rawQuery": True
                }],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "velocityms"
                    }
                },
                "options": {
                    "tooltip": {"mode": "single", "sort": "none"},
                    "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True}
                }
            }
        ]
    },
    "overwrite": True
}

print("Creating new live dashboard...")
response = requests.post(
    f"{GRAFANA_URL}/api/dashboards/db",
    headers=headers,
    data=json.dumps(dashboard)
)

if response.status_code == 200:
    result = response.json()
    dashboard_uid = result.get('uid')
    dashboard_url = result.get('url')
    
    print(f"\n✓ Live dashboard created successfully!")
    print(f"  UID: {dashboard_uid}")
    print(f"  URL: {GRAFANA_URL}{dashboard_url}?kiosk=tv&orgId=1")
    
    # Update database
    print("\nUpdating database with new dashboard UID...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "UPDATE timestream_tables SET db_uid = %s WHERE tableID = 1472",
        (dashboard_uid,)
    )
    conn.commit()
    cur.close()
    conn.close()
    print("✓ Database updated!")
    
    print(f"\nView at: http://127.0.0.1:2543/topic/1472")
    
else:
    print(f"\n✗ Failed to create dashboard")
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text}")
