#!/usr/bin/env python3
import psycopg2
from datetime import datetime, timedelta

DB_CONFIG = {
    'dbname': 'mqtt_dashboard',
    'user': 'postgres',
    'password': 'campDashSQL',
    'host': 'localhost',
    'port': 5432
}

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# Test original query format
print("=== ORIGINAL FORMAT (with ::double precision) ===")
cur.execute("""
    SELECT time AS "time", measure_value_double::double precision AS "AirTempK" 
    FROM public.data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655 
    WHERE measure_name='AirTempK' 
        AND time >= NOW() - INTERVAL '24 hours'
        AND measure_value_double IS NOT NULL 
    ORDER BY time DESC LIMIT 3
""")
rows = cur.fetchall()
print(f"Returned {len(rows)} rows")
if rows:
    print("Sample:", rows[0])

# Test working query format  
print("\n=== WORKING FORMAT (without cast) ===")
cur.execute("""
    SELECT time AS "time", measure_value_double AS "AirTempK"
    FROM data_incoming_zmb_campbell_v1_0_894_2_lslu002_data_cr1000x_4655
    WHERE measure_name = 'AirTempK'
        AND time >= NOW() - INTERVAL '24 hours'
        AND measure_value_double IS NOT NULL
    ORDER BY time ASC LIMIT 3
""")
rows = cur.fetchall()
print(f"Returned {len(rows)} rows")
if rows:
    print("Sample:", rows[0])

cur.close()
conn.close()
