#!/usr/bin/env python3
"""
Apply the dashboard fix to ALL topics in the database.
"""
import requests
import json
import psycopg2
import re

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

# Get all dashboard UIDs from database
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute("SELECT tableID, db_uid, topic FROM timestream_tables WHERE db_uid IS NOT NULL AND db_uid != ''")
topics = cur.fetchall()
cur.close()
conn.close()

print(f"Found {len(topics)} topics with dashboards to fix\n")

for table_id, dashboard_uid, topic in topics:
    print(f"Processing Topic {table_id}: {topic}")
    print(f"  Dashboard UID: {dashboard_uid}")
    
    # Fetch dashboard
    response = requests.get(
        f"{GRAFANA_URL}/api/dashboards/uid/{dashboard_uid}",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"  ✗ Failed to fetch dashboard: {response.status_code}")
        continue
    
    dashboard_data = response.json()
    dashboard = dashboard_data['dashboard']
    
    # Set proper time range
    dashboard['time'] = {
        "from": "now-24h",
        "to": "now"
    }
    dashboard['refresh'] = "30s"
    dashboard['timepicker'] = {
        "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
    }
    
    # Fix each panel
    panel_id = 1
    fixed_panels = 0
    
    for panel in dashboard['panels']:
        # Assign proper panel ID if missing
        if panel.get('id') is None:
            panel['id'] = panel_id
        panel_id += 1
        
        if panel.get('type') == 'timeseries':
            fixed_panels += 1
            
            # Fix fieldConfig
            if 'fieldConfig' not in panel:
                panel['fieldConfig'] = {}
            if 'defaults' not in panel['fieldConfig']:
                panel['fieldConfig']['defaults'] = {}
            
            # Set yellow color and minimal config
            panel['fieldConfig']['defaults']['color'] = {"mode": "fixed", "fixedColor": "yellow"}
            
            if 'custom' not in panel['fieldConfig']['defaults']:
                panel['fieldConfig']['defaults']['custom'] = {}
            
            panel['fieldConfig']['defaults']['custom'] = {
                "drawStyle": "line",
                "lineInterpolation": "linear",
                "lineWidth": 2,
                "fillOpacity": 10,
                "showPoints": "never",
                "spanNulls": True
            }
            
            # Fix targets
            if 'targets' in panel:
                for target in panel['targets']:
                    # Ensure refId is set
                    if not target.get('refId'):
                        target['refId'] = 'A'
                    
                    target['format'] = 'time_series'
                    
                    # Fix SQL queries
                    if 'rawSql' in target:
                        sql = target['rawSql']
                        
                        # Replace generic aliases
                        pattern = r"AS value,\s*'([^']+)'\s+AS metric"
                        match = re.search(pattern, sql)
                        if match:
                            metric_name = match.group(1)
                            sql = re.sub(pattern, f'AS "{metric_name}"', sql)
                        
                        # Add NULL filter
                        if 'measure_value_double' in sql and 'IS NOT NULL' not in sql:
                            sql = re.sub(r'(ORDER BY)', r'AND measure_value_double IS NOT NULL \1', sql)
                        elif 'measure_value_varchar' in sql and 'IS NOT NULL' not in sql:
                            sql = re.sub(r'(ORDER BY)', r'AND measure_value_varchar IS NOT NULL \1', sql)
                        
                        target['rawSql'] = sql
            
            # Remove field overrides that hide data
            if 'overrides' in panel['fieldConfig']:
                panel['fieldConfig']['overrides'] = [
                    override for override in panel['fieldConfig']['overrides']
                    if not any(
                        prop.get('id') == 'custom.hideFrom' and 
                        prop.get('value', {}).get('viz') == True
                        for prop in override.get('properties', [])
                    )
                ]
            
            # Add legend with stats
            if 'options' not in panel:
                panel['options'] = {}
            panel['options']['legend'] = {
                "calcs": ["mean", "lastNotNull"],
                "displayMode": "list",
                "placement": "bottom",
                "showLegend": True
            }
            panel['options']['tooltip'] = {
                "mode": "multi",
                "sort": "none"
            }
    
    print(f"  Fixed {fixed_panels} timeseries panels")
    
    # Update dashboard
    update_payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": f"Applied fix for topic {table_id}"
    }
    
    response = requests.post(
        f"{GRAFANA_URL}/api/dashboards/db",
        headers=headers,
        data=json.dumps(update_payload)
    )
    
    if response.status_code == 200:
        print(f"  ✓ Dashboard updated successfully\n")
    else:
        print(f"  ✗ Failed to update: {response.status_code}\n")

print(f"\nCompleted! Fixed {len(topics)} dashboards.")
