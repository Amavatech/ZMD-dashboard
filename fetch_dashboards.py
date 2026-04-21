import requests
import json

GRAFANA_URL = "http://127.0.0.1:3000/grafana"
API_KEY = "eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0="

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

def get_dashboards():
    try:
        response = requests.get(f"{GRAFANA_URL}/api/search?type=dash-db", headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.status_code, "text": response.text}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    dashboards = get_dashboards()
    with open('all_dashboards.json', 'w') as f:
        json.dump(dashboards, f, indent=4)
    print("Fetched dashboards successfully")
