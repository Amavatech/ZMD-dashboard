import os
import sys
import pandas as pd
import logging
import datetime
import pytz

# Add the utility directory to sys.path
utility_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mqtt_subscriber_timestream_output'))
sys.path.insert(0, utility_path)

import timescaleUtil as ts
import mySqlUtil
import configUtil as config

logging.basicConfig(level=logging.INFO)

# Force all Timescale operations in this script to use the public schema
SCHEMA_NAME = "public"
ts._schema_name = SCHEMA_NAME

def fix_dashboard_sql(table_obj, topic):
    """
    Fix SQL queries in dashboard panels to use proper time series format.
    """
    import requests
    import json
    
    grafana_url = "http://localhost:3000/grafana"
    api_key = config.config.get('Grafana', 'API_Key', fallback='eyJrIjoiaFBDeEJWaUthMWtsVzZ6Zk9xalRVQ1dpdzF1MW13M1UiLCJuIjoiQWRtaW4iLCJpZCI6MX0=')
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    
    dashboard_uid = table_obj.db_uid
    if not dashboard_uid:
        logging.warning(f"No dashboard UID for topic {topic}")
        return
    
    # Get normalized table name
    table_name = ts._normalize_table_name(topic.replace('/', '_'))
    
    try:
        # Fetch current dashboard
        resp = requests.get(f"{grafana_url}/api/dashboards/uid/{dashboard_uid}", headers=headers, timeout=10)
        if resp.status_code != 200:
            logging.error(f"Failed to fetch dashboard {dashboard_uid}: {resp.status_code}")
            return
        
        dashboard_data = resp.json()
        dashboard = dashboard_data['dashboard']
        
        # Get measurements for this topic
        measurements = [m.name for m in table_obj.measurements if m.visible == 1]
        
        if not measurements:
            logging.warning(f"No visible measurements for topic {topic}")
            return
        
        # Fix all panels
        fixed = 0
        for i, panel in enumerate(dashboard.get('panels', [])):
            if i < len(measurements) and 'targets' in panel:
                measure_name = measurements[i]
                panel['title'] = measure_name
                for target in panel['targets']:
                    # Use proper time series SQL format
                    target['rawSql'] = f'SELECT time AS "time", measure_value_double::double precision AS "{measure_name}" FROM public.{table_name} WHERE measure_name=\'{measure_name}\' AND $__timeFilter(time) AND measure_value_double IS NOT NULL ORDER BY time'
                    target['format'] = 'time_series'
                    fixed += 1
        
        if fixed > 0:
            # Update dashboard
            update_payload = {'dashboard': dashboard, 'overwrite': True}
            resp = requests.post(f"{grafana_url}/api/dashboards/db", headers=headers, data=json.dumps(update_payload), timeout=10)
            if resp.status_code == 200:
                logging.info(f"Fixed {fixed} panels in dashboard for {topic}")
            else:
                logging.error(f"Failed to update dashboard: {resp.status_code} - {resp.text}")
    except Exception as e:
        logging.error(f"Error fixing dashboard SQL for {topic}: {e}")

def get_latest_timestamp(topic):
    tbl_name = ts._normalize_table_name(topic.replace("/", "_"))
    conn = ts._get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(time) FROM {SCHEMA_NAME}.{tbl_name}")
            res = cur.fetchone()
            return res[0] if res and res[0] else None
    except Exception as e:
        logging.debug(f"Could not get latest timestamp for {tbl_name}: {e}")
        return None
    finally:
        ts._put_conn(conn)

def _infer_station_id_from_row(row, topic):
    """
    Infer station ID from data row, mimicking MQTT subscriber logic.
    Priority: 1) Station_Name column, 2) Station_ID column, 3) topic last segment
    """
    # Try Station_Name first
    if 'Station_Name' in row and pd.notna(row['Station_Name']) and str(row['Station_Name']).strip():
        return str(row['Station_Name']).strip()
    
    # Try Station_ID
    if 'Station_ID' in row and pd.notna(row['Station_ID']) and str(row['Station_ID']).strip():
        return str(row['Station_ID']).strip()
    
    # Fall back to topic parsing
    topic_parts = topic.split("/") if topic else []
    for part in topic_parts[::-1]:
        if part and part.upper() not in {"HOUR", "SYNOP", "DATA", "CR1000X"}:
            return part
    
    return "unknown"

def process_station_data(station_row, base_folder):
    station_name = str(station_row['WMO_Station_Name']).strip()
    dcp_id = str(station_row['DCP ID']).strip()
    wmo_id = str(station_row['WMO_Station_ID(WIGOS ID)']).strip()
    serial = str(station_row['Serial']).strip()

    if not dcp_id or dcp_id == 'nan' or not wmo_id or wmo_id == 'nan':
        return

    station_folder = os.path.join(base_folder, f"{station_name}_DCP_{dcp_id}")
    if not os.path.exists(station_folder):
        return

    files = [
        (os.path.join(station_folder, f"{station_name}_TableHour.dat"), "hour"),
        (os.path.join(station_folder, f"{station_name}_TableSYNOP.dat"), "synop")
    ]

    for file_path, table_type in files:
        if not os.path.exists(file_path):
            continue

        # Use the working topic format (cs/v1/...) and uppercase table type
        topic = f"cs/v1/data/cr1000x/{serial}/{table_type.upper()}"
        logging.info(f"Processing topic: {topic}")

        # Ensure table exists in timestream_tables and has correct broker/group
        table_obj = mySqlUtil.get_timestream_table(topic)
        if not table_obj:
            logging.info(f"Creating missing table for topic: {topic}")
            ts.create_table(config.timescale.database, topic.replace("/", "_"))
            # Use brokerID=11 and groupID=6 to match the working dashboard configuration
            table_obj = mySqlUtil.timestream_table(topic=topic, brokerID=11, groupID=6, db_uid="", longitude=0, latitude=0)
            mySqlUtil.session.add(table_obj)
            mySqlUtil.session.commit()
            # Register in Grafana
            try:
                mySqlUtil.create_dashboard_table(table_obj)
            except Exception as e:
                logging.error(f"Failed to create dashboard table for {topic}: {e}")
        else:
            # Ensure broker and group are correct for visibility
            if table_obj.brokerID != 11 or table_obj.groupID != 6:
                logging.info(f"Correcting brokerID/groupID for {topic}")
                table_obj.brokerID = 11
                table_obj.groupID = 6
                mySqlUtil.session.commit()
                try:
                    mySqlUtil.create_dashboard_table(table_obj)
                except Exception as e:
                    logging.error(f"Failed to update dashboard table for {topic}: {e}")

        latest_ts = get_latest_timestamp(topic)
        if latest_ts and latest_ts.tzinfo is None:
            latest_ts = pytz.UTC.localize(latest_ts)
        
        if latest_ts:
            logging.info(f"Latest record in DB for {topic}: {latest_ts}")

        try:
            # Read metadata row to check if it's a valid TOA5 file
            with open(file_path, 'r') as f:
                first_line = f.readline()
                if not first_line.startswith('"TOA5"'):
                    logging.warning(f"File {file_path} is not a valid TOA5 file. Skipping.")
                    continue

            # Read header row to get column names (skip metadata row 0)
            df_header = pd.read_csv(file_path, skiprows=1, nrows=0)
            columns = df_header.columns.tolist()
            
            # Read data (skip metadata 0, header 1, units 2, datatypes 3)
            df = pd.read_csv(file_path, skiprows=4, names=columns)
        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")
            continue

        if df.empty:
            continue

        # Convert TIMESTAMP and filter
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
        
        # Ensure UTC
        if df['TIMESTAMP'].dt.tz is None:
            df['TIMESTAMP'] = df['TIMESTAMP'].dt.tz_localize('UTC')
        else:
            df['TIMESTAMP'] = df['TIMESTAMP'].dt.tz_convert('UTC')

        if latest_ts:
            df = df[df['TIMESTAMP'] > latest_ts]

        if df.empty:
            logging.info(f"No new records to import for {topic}")
            continue

        logging.info(f"Importing {len(df)} new records for {topic}")

        all_records = []
        all_weather_rows = []

        # Track if we need to update Grafana dashboard
        measurements_added = False

        # Cache existing measurements for this topic to avoid repeated DB queries
        existing_measurements = set()
        table_obj = mySqlUtil.get_timestream_table(topic)
        if table_obj:
            existing_measurements = {m.name for m in table_obj.measurements}

        for _, row in df.iterrows():
            dt = row['TIMESTAMP']
            record_time = str(1000 * int(dt.timestamp()))
            
            # Infer station_id from the actual data row (mimics MQTT subscriber behavior)
            station_id = _infer_station_id_from_row(row, topic)
            
            records_for_this_row = []
            
            for col in columns:
                if col in ['TIMESTAMP', 'RECORD']:
                    continue
                
                val = row[col]
                if pd.isna(val) or val == 'NAN' or val == '':
                    continue
                
                # Determine type
                if isinstance(val, (int, float)):
                    measure_type = "DOUBLE"
                else:
                    measure_type = "VARCHAR"
                
                unit = "unitless" 
                
                if col not in existing_measurements:
                    logging.info(f"Adding new measurement '{col}' for topic '{topic}'")
                    mySqlUtil.add_timestream_measurement(topic, col, unit, measure_type, True, True)
                    existing_measurements.add(col)
                    measurements_added = True
                
                records_for_this_row.append({
                    'Dimensions': [{'Name': 'unit', 'Value': unit}, {'Name': 'Measurement Type', 'Value': measure_type}],
                    'MeasureValueType': measure_type,
                    'Time': record_time,
                    'MeasureName': col,
                    'MeasureValue': str(val)
                })

                if measure_type == "DOUBLE":
                    all_weather_rows.append((dt.to_pydatetime(), station_id, col, float(val)))
            
            all_records.extend(records_for_this_row)

        if all_records:
            # Group records by topic for write_records if we were doing multiple topics, 
            # but here all records in this loop are for the same topic.
            ts.write_records(config.timescale.database, topic.replace('/', '_'), all_records)
        
        if all_weather_rows:
            try:
                ts.write_weather_data(all_weather_rows)
            except Exception as e:
                if "duplicate key value" in str(e):
                    logging.debug(f"Duplicate weather_data entries for {topic}")
                else:
                    logging.error(f"Error writing to weather_data for {topic}: {e}")
        
        # Update Grafana dashboard - always recreate after import to ensure correct configuration
        try:
            table_obj = mySqlUtil.get_timestream_table(topic)
            if table_obj:
                # Recreate dashboard with all measurements
                mySqlUtil.create_dashboard_table(table_obj)
                logging.info(f"Recreated Grafana dashboard for {topic} (UID: {table_obj.db_uid})")
                
                # Fix SQL queries in all panels
                fix_dashboard_sql(table_obj, topic)
        except Exception as e:
            logging.warning(f"Grafana dashboard update failed for {topic}: {e}")
        
        mySqlUtil.session.commit()
        logging.info(f"Successfully imported data for {topic}")

def main():
    base_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EUMETSAT")
    stations_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stations.csv")
    
    if not os.path.exists(stations_csv):
        logging.error(f"Error: {stations_csv} not found.")
        return

    try:
        stations_df = pd.read_csv(stations_csv)
    except Exception as e:
        logging.error(f"Error reading stations CSV: {e}")
        return

    for _, row in stations_df.iterrows():
        try:
            process_station_data(row, base_folder)
        except Exception as e:
            logging.error(f"Failed to process station {row.get('WMO_Station_Name')}: {e}")
            mySqlUtil.session.rollback()

if __name__ == "__main__":
    main()
