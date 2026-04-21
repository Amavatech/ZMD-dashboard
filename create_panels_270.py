import psycopg2
import requests
import json

GRAFANA_URL = "http://127.0.0.1:3000/grafana"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="
headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}

def create_panels_for_topic(table_id):
    # Get topic and UID from DB
    conn = psycopg2.connect(dbname='mqtt_dashboard', user='postgres', password='campDashSQL', host='localhost', port=5432)
    cur = conn.cursor()
    cur.execute("SELECT tableid, topic, db_uid FROM timestream_tables WHERE tableid = %s;", (table_id,))
    row = cur.fetchone()
    
    if not row:
        print(f"Topic {table_id} not found")
        return
    
    table_id, topic, db_uid = row
    print(f"Creating panels for Topic {table_id}: {topic}")
    
    # Get measurements for this topic
    cur.execute("SELECT name, unit, type FROM timestream_measurements WHERE tableid = %s ORDER BY name;", (table_id,))
    measurements = cur.fetchall()
    cur.close()
    conn.close()
    
    if not measurements:
        print(f"No measurements found for topic {table_id}")
        return
    
    print(f"Found {len(measurements)} measurements")
    
    # Fetch existing dashboard
    resp = requests.get(f"{GRAFANA_URL}/api/dashboards/uid/{db_uid}", headers=headers)
    if resp.status_code != 200:
        print(f"Failed to fetch dashboard: {resp.status_code}")
        return
    
    dashboard_data = resp.json()
    dashboard = dashboard_data['dashboard']
    
    # Create panels for each measurement
    panel_id = 1
    panels = []
    y_pos = 0
    
    for measure_name, unit, measure_type in measurements:
        # Determine the value column type
        value_col = 'measure_value_double' if measure_type == 'DOUBLE' else 'measure_value_varchar'
        
        # Create SQL query
        sql = f"""
SELECT
    time as "time",
    {value_col} as "{measure_name}"
FROM
    aws_db.{table_id}
WHERE
    measure_name = '{measure_name}'
    AND time > $__timeFrom
    AND time < $__timeTo
    AND {value_col} IS NOT NULL
ORDER BY time
"""
        
        # Create panel
        panel = {
            "id": panel_id,
            "title": measure_name,
            "type": "timeseries",
            "gridPos": {
                "h": 8,
                "w": 12,
                "x": 0,
                "y": y_pos
            },
            "targets": [
                {
                    "refId": "A",
                    "format": "time_series",
                    "rawSql": sql,
                    "datasourceUid": "-100"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "fixed",
                        "fixedColor": "yellow"
                    },
                    "custom": {
                        "drawStyle": "line",
                        "lineInterpolation": "linear",
                        "lineWidth": 2,
                        "fillOpacity": 10,
                        "showPoints": "never",
                        "spanNulls": True
                    }
                },
                "overrides": []
            },
            "options": {
                "legend": {
                    "calcs": ["mean", "lastNotNull"],
                    "displayMode": "list",
                    "placement": "bottom",
                    "showLegend": True
                },
                "tooltip": {
                    "mode": "multi",
                    "sort": "none"
                }
            }
        }
        
        panels.append(panel)
        panel_id += 1
        y_pos += 8
    
    # Update dashboard
    dashboard['panels'] = panels
    dashboard['time'] = {"from": "now-24h", "to": "now"}
    dashboard['refresh'] = "30s"
    
    update_payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": f"Created {len(panels)} panels for measurements"
    }
    
    resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=update_payload)
    
    if resp.status_code == 200:
        print(f"\n✓ Successfully created {len(panels)} panels!")
        for measure_name, _, _ in measurements:
            print(f"  - {measure_name}")
    else:
        print(f"✗ Failed to update dashboard: {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    create_panels_for_topic(270)
