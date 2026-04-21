import psycopg2
import json

try:
    conn = psycopg2.connect(
        dbname='mqtt_dashboard',
        user='postgres',
        password='campDashSQL',
        host='localhost',
        port=5432
    )
    cur = conn.cursor()
    
    # Get all registered topics/dashboards
    cur.execute("SELECT tableid, topic, db_uid FROM timestream_tables;")
    tables = cur.fetchall()
    
    results = []
    for tableid, topic, db_uid in tables:
        # Check if the table exists (normalized name)
        normalized_name = topic.lower().replace("-", "_").replace("/", "_")
        
        # Check for data in the specific table
        try:
            cur.execute(f"SELECT COUNT(*) FROM \"{normalized_name}\";")
            count = cur.fetchone()[0]
        except Exception:
            conn.rollback()
            count = 0
            
        results.append({
            "tableID": tableid,
            "topic": topic,
            "dashboard_uid": db_uid,
            "record_count": count
        })
    
    print(json.dumps(results, indent=2))
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
