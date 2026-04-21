#!/usr/bin/env python3
"""
Script to create a test Grafana snapshot for testing the dashboard configuration.
"""
import requests
import json

GRAFANA_URL = "http://localhost:3000"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

# Fetch an existing dashboard (using the first one we found)
dashboard_uid = "vucpaUSDk"  # cs/v1/data/cr1000x/46556/SYNOP

print(f"Fetching dashboard {dashboard_uid}...")
dash_resp = requests.get(
    url=f"{GRAFANA_URL}/api/dashboards/uid/{dashboard_uid}",
    headers=headers
)

if not dash_resp.ok:
    print(f"Failed to fetch dashboard: {dash_resp.status_code} {dash_resp.text}")
    exit(1)

dash = dash_resp.json()
print("Dashboard fetched successfully!")

# Create snapshot
print("Creating snapshot...")
snapshot_resp = requests.post(
    url=f'{GRAFANA_URL}/api/snapshots',
    data=json.dumps(dash),
    headers=headers
)

if snapshot_resp.ok:
    snap_json = snapshot_resp.json()
    snapshot_key = snap_json.get("key", "")
    snapshot_url = snap_json.get("url", "")
    
    print(f"\n✓ Snapshot created successfully!")
    print(f"  Key: {snapshot_key}")
    print(f"  Full URL: {GRAFANA_URL}{snapshot_url}?kiosk=tv&orgId=1")
    print(f"\nUpdate your test URL to:")
    print(f"  http://localhost:3000/dashboard/snapshot/{snapshot_key}?kiosk=tv&orgId=1")
else:
    print(f"Failed to create snapshot: {snapshot_resp.status_code}")
    print(snapshot_resp.text)
