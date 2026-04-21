import json
import re

def get_station_name(topic):
    # Try to find the station name in common patterns
    match = re.search(r'0-894-2-([^/]+)', topic)
    if match:
        return match.group(1).replace('-', ' ')
    
    # Fallback to the last part or second to last part
    parts = topic.split('/')
    if len(parts) >= 2:
        for part in reversed(parts):
            if part and part not in ['SYNOP', 'HOUR', 'data', 'cr1000x', 'cr6', 'TableHour', 'TableDay']:
                return part
    return topic

try:
    with open('/home/ubuntu/mqtt_dashboard/dashboards_info.json', 'r') as f:
        data = json.load(f)
    
    # Filter for dashboards with records
    active_dashboards = [d for d in data if d['record_count'] > 0]
    
    # Sort by record count descending
    active_dashboards.sort(key=lambda x: x['record_count'], reverse=True)
    
    print("# Active Dashboards (Dashboards with Data)\n")
    print("| Station / Topic | Dashboard UID | Record Count | Topic |")
    print("| :--- | :--- | :--- | :--- |")
    
    processed_uids = set()
    for d in active_dashboards:
        uid = d['dashboard_uid']
        if uid in processed_uids:
            continue
        processed_uids.add(uid)
        
        station = get_station_name(d['topic'])
        print(f"| {station} | {uid} | {d['record_count']:,} | {d['topic']} |")

except Exception as e:
    print(f"Error processing dashboards: {e}")
