#!/usr/bin/env python3
"""
Test script to import data for a single station (LusakaAirport).
This helps verify the import process works before running on all stations.
"""
import os
import sys
import pandas as pd
import logging

# Add the utility directory to sys.path
utility_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mqtt_subscriber_timestream_output'))
sys.path.insert(0, utility_path)

import mySqlUtil

logging.basicConfig(level=logging.INFO)

def main():
    # Test with LusakaAirport station
    station_info = {
        'WMO_Station_Name': 'LusakaAirport',
        'DCP ID': '1835F572',
        'WMO_Station_ID(WIGOS ID)': '0-894-2-LSLU002',
        'Serial': '46556'
    }
    
    base_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EUMETSAT")
    
    # Import the main processing function
    from import_module import process_station_data
    
    logging.info("="*60)
    logging.info(f"Testing import for station: {station_info['WMO_Station_Name']}")
    logging.info(f"Serial: {station_info['Serial']}, DCP: {station_info['DCP ID']}")
    logging.info("="*60)
    
    try:
        # Create a pandas Series to mimic CSV row
        station_row = pd.Series(station_info)
        process_station_data(station_row, base_folder)
        logging.info("="*60)
        logging.info("✓ Import completed successfully!")
        logging.info("="*60)
    except Exception as e:
        logging.error(f"✗ Import failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
