#!/usr/bin/env python3
"""
Create a Grafana snapshot with static hardcoded data points.
"""
import requests
import json
from datetime import datetime, timedelta

GRAFANA_URL = "http://localhost:3000"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

# Generate static data points
now = datetime.now()
datapoints_temp = []
datapoints_humidity = []
datapoints_pressure = []
datapoints_wind = []

import math

for i in range(100):
    timestamp = int((now - timedelta(hours=6) + timedelta(minutes=i*3.6)).timestamp() * 1000)
    
    # Temperature: smooth sine wave 20-30°C
    temp_value = 25 + 5 * math.sin(i * 0.3)
    datapoints_temp.append([temp_value, timestamp])
    
    # Humidity: smooth sine wave 50-80%
    humidity_value = 65 + 15 * math.sin(i * 0.2)
    datapoints_humidity.append([humidity_value, timestamp])
    
    # Pressure: smooth variation 995-1025 hPa
    pressure_value = 1010 + 15 * math.sin(i * 0.15)
    datapoints_pressure.append([pressure_value, timestamp])
    
    # Wind: varying 2-18 m/s
    wind_value = 10 + 8 * math.sin(i * 0.25)
    datapoints_wind.append([wind_value, timestamp])

print(f"Generated {len(datapoints_temp)} data points")
print(f"Pressure range: {min(p[0] for p in datapoints_pressure):.1f} - {max(p[0] for p in datapoints_pressure):.1f} hPa")

# Create snapshot with embedded data
snapshot_data = {
    "dashboard": {
        "title": "Weather Station Demo",
        "tags": ["demo", "weather"],
        "timezone": "browser",
        "schemaVersion": 37,
        "version": 0,
        "refresh": False,
        "panels": [
            {
                "id": 1,
                "title": "Temperature (°C)",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 0, "y": 0},
                "targets": [{"refId": "A", "target": "Temperature"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "axisPlacement": "auto",
                            "lineInterpolation": "smooth"
                        },
                        "unit": "celsius"
                    }
                },
                "options": {
                    "legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single"}
                }
            },
            {
                "id": 2,
                "title": "Humidity (%)",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 12, "y": 0},
                "targets": [{"refId": "A", "target": "Humidity"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "axisPlacement": "auto",
                            "lineInterpolation": "smooth"
                        },
                        "unit": "percent"
                    }
                },
                "options": {
                    "legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single"}
                }
            },
            {
                "id": 3,
                "title": "Atmospheric Pressure (hPa)",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 0, "y": 9},
                "targets": [{"refId": "A", "target": "Pressure"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "axisPlacement": "auto",
                            "lineInterpolation": "smooth"
                        },
                        "unit": "pressurehpa"
                    }
                },
                "options": {
                    "legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single"}
                }
            },
            {
                "id": 4,
                "title": "Wind Speed (m/s)",
                "type": "timeseries",
                "gridPos": {"h": 9, "w": 12, "x": 12, "y": 9},
                "targets": [{"refId": "A", "target": "Wind Speed"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "axisPlacement": "auto",
                            "lineInterpolation": "smooth"
                        },
                        "unit": "velocityms"
                    }
                },
                "options": {
                    "legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single"}
                }
            },
            {
                "id": 5,
                "title": "Station Information",
                "type": "text",
                "gridPos": {"h": 4, "w": 24, "x": 0, "y": 18},
                "options": {
                    "content": "### Weather Station Demo Dashboard\n\n**Station:** Test Site Demo  \n**Data Source:** Hardcoded Test Data  \n**Status:** ✅ Active  \n**Time Range:** Last 6 Hours\n\nThis dashboard demonstrates the Grafana configuration with static test data.",
                    "mode": "markdown"
                }
            }
        ],
        "time": {"from": "now-6h", "to": "now"}
    },
    "name": "Weather Station Demo Snapshot",
    "expires": 0,
    "snapshot": {
        "data": {
            "Temperature": datapoints_temp,
            "Humidity": datapoints_humidity,
            "Pressure": datapoints_pressure,
            "Wind Speed": datapoints_wind
        }
    }
}

print("Creating snapshot with hardcoded data points...")
snapshot_resp = requests.post(
    url=f'{GRAFANA_URL}/api/snapshots',
    data=json.dumps(snapshot_data),
    headers=headers
)

if snapshot_resp.ok:
    snap_json = snapshot_resp.json()
    snapshot_key = snap_json.get("key", "")
    
    print(f"\n✅ SUCCESS! Snapshot created with visible data!")
    print(f"\n📊 Snapshot Key: {snapshot_key}")
    print(f"\n🔗 Test URL (kiosk mode):")
    print(f"   http://localhost:3000/dashboard/snapshot/{snapshot_key}?kiosk=tv&orgId=1")
    print(f"\n📈 This snapshot includes:")
    print(f"   • {len(datapoints_temp)} data points per metric")
    print(f"   • Temperature, Humidity, Pressure, Wind Speed graphs")
    print(f"   • 6 hours of simulated weather data")
else:
    print(f"❌ Failed to create snapshot: {snapshot_resp.status_code}")
    print(snapshot_resp.text)
