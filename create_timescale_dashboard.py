#!/usr/bin/env python3
"""
Create a Grafana dashboard with proper TimescaleDB time series queries.
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

# Create comprehensive dashboard with all weather metrics
dashboard = {
    "dashboard": {
        "title": "LusakaAirport Weather Station - Complete View",
        "timezone": "browser",
        "editable": True,
        "hideControls": False,
        "graphTooltip": 0,
        "time": {
            "from": "now-24h",
            "to": "now"
        },
        "timepicker": {
            "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
        },
        "refresh": "30s",
        "schemaVersion": 16,
        "version": 0,
        "panels": [
            # Station Info Panel
            {
                "id": 1,
                "type": "table",
                "title": "Station Information",
                "gridPos": {"h": 4, "w": 8, "x": 0, "y": 0},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "table",
                        "rawSql": """SELECT 
                            (SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'Station_Name' ORDER BY time DESC LIMIT 1) as "Station",
                            (SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'Station_ID' ORDER BY time DESC LIMIT 1) as "ID",
                            (SELECT measure_value_varchar FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'WMO_Station_Type' ORDER BY time DESC LIMIT 1) as "Type"
                        """,
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "options": {
                    "showHeader": True
                },
                "fieldConfig": {
                    "defaults": {
                        "custom": {
                            "align": "center",
                            "displayMode": "color-text"
                        }
                    }
                }
            },
            # Location Info
            {
                "id": 50,
                "type": "stat",
                "title": "Location",
                "gridPos": {"h": 4, "w": 8, "x": 8, "y": 0},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "table",
                        "rawSql": """SELECT 
                            ROUND(CAST((SELECT measure_value_double FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'Latitude' ORDER BY time DESC LIMIT 1) AS numeric), 4) as "Latitude",
                            ROUND(CAST((SELECT measure_value_double FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'Longitude' ORDER BY time DESC LIMIT 1) AS numeric), 4) as "Longitude",
                            ROUND(CAST((SELECT measure_value_double FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
                             WHERE measure_name = 'Elevation' ORDER BY time DESC LIMIT 1) AS numeric), 1) as "Elevation (m)"
                        """,
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "options": {
                    "reduceOptions": {
                        "values": False,
                        "calcs": ["lastNotNull"]
                    },
                    "textMode": "value_and_name",
                    "colorMode": "background",
                    "graphMode": "none",
                    "orientation": "horizontal"
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
            # Last Update Time
            {
                "id": 51,
                "type": "stat",
                "title": "Last Update",
                "gridPos": {"h": 4, "w": 8, "x": 16, "y": 0},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "table",
                        "rawSql": """SELECT MAX(time) as "Last Data" FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "options": {
                    "reduceOptions": {
                        "values": False,
                        "calcs": ["lastNotNull"]
                    },
                    "textMode": "value",
                    "colorMode": "background",
                    "graphMode": "none"
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "unit": "dateTimeAsIso",
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [{"color": "green", "value": None}]
                        }
                    }
                }
            },
            # Air Temperature Panel
            {
                "id": 2,
                "type": "timeseries",
                "title": "Air Temperature",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double - 273.15 AS "Current Temp (°C)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'AirTempK'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double - 273.15 AS "Max Temp (°C)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'AirTempMaxK'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "C",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double - 273.15 AS "Min Temp (°C)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'AirTempMinK'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "D",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double - 273.15 AS "Dew Point (°C)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'DewPointTempK'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 0,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "celsius"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Current Temp (°C)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Max Temp (°C)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Min Temp (°C)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Dew Point (°C)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "light-blue"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["mean", "lastNotNull", "max", "min"], "displayMode": "table", "placement": "bottom"}
                }
            },
            # Relative Humidity Panel
            {
                "id": 3,
                "type": "timeseries",
                "title": "Relative Humidity",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Humidity"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'RH'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
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
                        "max": 100,
                        "min": 0
                    }
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["mean", "lastNotNull"], "displayMode": "list", "placement": "bottom"}
                }
            },
            # Barometric Pressure Panel
            {
                "id": 4,
                "type": "timeseries",
                "title": "Barometric Pressure",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Station Pressure (hPa)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'BP'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "QNH (hPa)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'QNH'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 0,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "pressurehpa"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Station Pressure (hPa)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "QNH (hPa)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["mean", "lastNotNull"], "displayMode": "table", "placement": "bottom"}
                }
            },
            # Wind Speed Panel
            {
                "id": 5,
                "type": "timeseries",
                "title": "Wind Speed & Gusts",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Wind Speed (m/s)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'WSpeed'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Wind Gust (m/s)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'WindGust'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "C",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "10m Avg Wind (m/s)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'WSpeed10M_Avg'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 0,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "velocityms"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Wind Speed (m/s)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Wind Gust (m/s)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["mean", "lastNotNull", "max"], "displayMode": "table", "placement": "bottom"}
                }
            },
            # Wind Direction Panel
            {
                "id": 6,
                "type": "timeseries",
                "title": "Wind Direction",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 20},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Direction (°)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'WindDir'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "yellow"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 0,
                            "showPoints": "auto",
                            "spanNulls": True
                        },
                        "unit": "degree",
                        "min": 0,
                        "max": 360
                    }
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["lastNotNull"], "displayMode": "list", "placement": "bottom"}
                }
            },
            # Rainfall Panel
            {
                "id": 7,
                "type": "timeseries",
                "title": "Rainfall",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 20},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Hourly Rain (mm)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'Rain_hr'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Total Rain (mm)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'Rain_mm_Tot'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 20,
                            "showPoints": "auto",
                            "spanNulls": True
                        },
                        "unit": "lengthmm"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Hourly Rain (mm)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Total Rain (mm)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["sum", "lastNotNull"], "displayMode": "table", "placement": "bottom"}
                }
            },
            # Solar Radiation Panel
            {
                "id": 8,
                "type": "timeseries",
                "title": "Solar Radiation",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 28},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Solar Hourly (J)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'SlrJ'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Solar 24h (J)"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'SlrJ24'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "joule"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Solar Hourly (J)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        },
                        {
                            "matcher": {"id": "byName", "options": "Solar 24h (J)"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["mean", "lastNotNull"], "displayMode": "table", "placement": "bottom"}
                }
            },
            # Sunshine Hours Panel
            {
                "id": 9,
                "type": "timeseries",
                "title": "Sunshine Duration",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 28},
                "datasource": {"type": "postgres", "uid": DATASOURCE_UID},
                "targets": [
                    {
                        "refId": "A",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Sunshine Hours"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'SunHrs'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    },
                    {
                        "refId": "B",
                        "format": "time_series",
                        "rawSql": """SELECT
                            time AS "time",
                            measure_value_double AS "Sunshine 24h"
                        FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
                        WHERE 
                            measure_name = 'SunHrs24'
                            AND $__timeFilter(time)
                            AND measure_value_double IS NOT NULL
                        ORDER BY time ASC""",
                        "datasource": {"type": "postgres", "uid": DATASOURCE_UID}
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "drawStyle": "line",
                            "lineInterpolation": "linear",
                            "lineWidth": 2,
                            "fillOpacity": 10,
                            "showPoints": "never",
                            "spanNulls": True
                        },
                        "unit": "h"
                    },
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Sunshine Hours"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]
                        }
                    ]
                },
                "options": {
                    "tooltip": {"mode": "multi", "sort": "none"},
                    "legend": {"calcs": ["sum", "lastNotNull"], "displayMode": "table", "placement": "bottom"}
                }
            }
        ]
    },
    "overwrite": True
}

print("Creating new dashboard with TimescaleDB-compatible queries...")
response = requests.post(
    f"{GRAFANA_URL}/api/dashboards/db",
    headers=headers,
    data=json.dumps(dashboard)
)

if response.status_code == 200:
    result = response.json()
    dashboard_uid = result.get('uid')
    dashboard_url = result.get('url')
    
    print(f"\n✓ Dashboard created successfully!")
    print(f"  UID: {dashboard_uid}")
    print(f"  URL: {GRAFANA_URL}{dashboard_url}?kiosk=tv&orgId=1")
    
    # Update database with new dashboard UID
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
    
    print(f"\nView live dashboard at: http://127.0.0.1:2543/topic/1472")
    print(f"Direct Grafana URL: {GRAFANA_URL}{dashboard_url}?kiosk=tv&orgId=1")
    
else:
    print(f"\n✗ Failed to create dashboard")
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text}")
