#!/usr/bin/env python3
"""
Dry-run test: Check what would be imported without actually writing to database.
"""
import os
import sys
import pandas as pd
import logging
import pytz

# Add the utility directory to sys.path
utility_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mqtt_subscriber_timestream_output'))
sys.path.insert(0, utility_path)

import timescaleUtil as ts
import mySqlUtil

logging.basicConfig(level=logging.INFO)

def main():
    # Test with LusakaAirport
    station_name = 'LusakaAirport'
    serial = '46556'
    dcp_id = '1835F572'
    
    base_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EUMETSAT")
    station_folder = os.path.join(base_folder, f"{station_name}_DCP_{dcp_id}")
    
    files = [
        (os.path.join(station_folder, f"{station_name}_TableHour.dat"), "hour"),
        (os.path.join(station_folder, f"{station_name}_TableSYNOP.dat"), "synop")
    ]
    
    for file_path, table_type in files:
        if not os.path.exists(file_path):
            logging.info(f"✗ File not found: {file_path}")
            continue
            
        topic = f"cs/v1/data/cr1000x/{serial}/{table_type.upper()}"
        logging.info(f"\n{'='*60}")
        logging.info(f"File: {os.path.basename(file_path)}")
        logging.info(f"Topic: {topic}")
        logging.info(f"{'='*60}")
        
        # Check if topic exists in database
        table_obj = mySqlUtil.get_timestream_table(topic)
        if table_obj:
            logging.info(f"✓ Topic exists in DB (tableID={table_obj.tableID}, brokerID={table_obj.brokerID}, groupID={table_obj.groupID})")
            logging.info(f"  Dashboard UID: {table_obj.db_uid}")
            measurement_count = len([m for m in table_obj.measurements if m.visible == 1])
            logging.info(f"  Visible measurements: {measurement_count}")
        else:
            logging.info(f"✗ Topic does not exist in DB - will be created")
        
        # Get latest timestamp from DB
        tbl_name = ts._normalize_table_name(topic.replace("/", "_"))
        try:
            conn = ts._get_conn()
            with conn.cursor() as cur:
                cur.execute(f"SELECT MAX(time) FROM public.{tbl_name}")
                latest_ts = cur.fetchone()[0]
                if latest_ts:
                    if latest_ts.tzinfo is None:
                        latest_ts = pytz.UTC.localize(latest_ts)
                    logging.info(f"  Latest DB timestamp: {latest_ts}")
                else:
                    logging.info(f"  Latest DB timestamp: None (empty table)")
            ts._put_conn(conn)
        except Exception as e:
            logging.info(f"  Latest DB timestamp: Error - {e}")
            latest_ts = None
        
        # Read file
        try:
            with open(file_path, 'r') as f:
                first_line = f.readline()
                if not first_line.startswith('"TOA5"'):
                    logging.warning(f"✗ Not a valid TOA5 file")
                    continue
            
            df_header = pd.read_csv(file_path, skiprows=1, nrows=0)
            columns = df_header.columns.tolist()
            df = pd.read_csv(file_path, skiprows=4, names=columns)
            
            logging.info(f"  File rows: {len(df)}")
            logging.info(f"  Columns: {len(columns)}")
            
            # Convert timestamps
            df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
            if df['TIMESTAMP'].dt.tz is None:
                df['TIMESTAMP'] = df['TIMESTAMP'].dt.tz_localize('UTC')
            else:
                df['TIMESTAMP'] = df['TIMESTAMP'].dt.tz_convert('UTC')
            
            logging.info(f"  Date range: {df['TIMESTAMP'].min()} to {df['TIMESTAMP'].max()}")
            
            # Filter by latest timestamp
            if latest_ts:
                new_df = df[df['TIMESTAMP'] > latest_ts]
                logging.info(f"  New rows to import: {len(new_df)}")
            else:
                new_df = df
                logging.info(f"  All rows are new: {len(new_df)}")
            
            if len(new_df) > 0:
                # Count measurements that would be created
                data_columns = [col for col in columns if col not in ['TIMESTAMP', 'RECORD']]
                logging.info(f"  Data measurements: {len(data_columns)}")
                
                # Sample first row
                if len(new_df) > 0:
                    sample_row = new_df.iloc[0]
                    logging.info(f"\n  Sample row (first new record):")
                    logging.info(f"    Timestamp: {sample_row['TIMESTAMP']}")
                    non_null_cols = []
                    for col in data_columns[:5]:  # Show first 5
                        val = sample_row[col]
                        if pd.notna(val) and val != 'NAN' and val != '':
                            non_null_cols.append(f"{col}={val}")
                    logging.info(f"    Sample values: {', '.join(non_null_cols)}")
            
        except Exception as e:
            logging.error(f"✗ Error reading file: {e}")
    
    logging.info(f"\n{'='*60}")
    logging.info("Dry-run complete! No data was written to database.")
    logging.info("='*60}")

if __name__ == "__main__":
    main()
