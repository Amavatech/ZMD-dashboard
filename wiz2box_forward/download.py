import os
import re
import time
import pandas as pd
import requests
import sys
import gzip
import shutil
import csv
import json
import paho.mqtt.client as mqtt
from datetime import datetime

username = "ZambiaMD"
password = "5PhzAHE3P4H1"

# Reporting endpoint (shared with mqtt_subscriber)
REPORT_ENDPOINT = "http://16.28.16.60:3000/api/report/cmm7yibi4khzco01lckk56ivo"

# MQTT Configuration
MQTT_BROKER = "3.124.208.185"
MQTT_PORT = 1883
MQTT_USERNAME = "wis2box"
MQTT_PASSWORD = "Wh00mqtt!"
MQTT_TOPIC_PREFIX = "data-incoming/zmb/campbell-v1"

def _post_report(alias: str, value: str):
    """POST a key/value metric to the reporting webapp."""
    try:
        resp = requests.post(
            REPORT_ENDPOINT,
            json={"alias": alias, "value": value},
            timeout=10,
        )
        print(f"Report sent: {alias}={value} (HTTP {resp.status_code})")
    except Exception as exc:
        print(f"Failed to send report ({alias}): {exc}")


def _write_station_log(contacted: set, with_data: set):
    """Write a text file next to this script listing contacted and data-transmitting stations.

    The file is overwritten on every run so it always reflects the latest run.
    """
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "station_run_log.txt")
    now = datetime.now().isoformat(timespec="seconds")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# Station run log — generated {now}\n")
            f.write(f"# Stations recognised (download succeeded, no validation error): {len(contacted)}\n")
            f.write(f"# Stations with new datapoints: {len(with_data)}\n")
            f.write("\n")
            f.write("[STATIONS THAT MADE CONTACT — data or no data]\n")
            for sid in sorted(contacted):
                f.write(f"  {sid}\n")
            f.write("\n")
            f.write("[STATIONS THAT TRANSMITTED DATA]\n")
            for sid in sorted(with_data):
                f.write(f"  {sid}\n")
        print(f"Station run log written to {log_path}")
    except Exception as exc:
        print(f"Failed to write station run log: {exc}")


def publish_to_mqtt(df, wigos_id, station_id, station_name, header, units):
    """
    Convert DataFrame to GeoJSON and publish to MQTT.
    """
    if df is None or df.empty:
        return

    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return

    topic = f"{MQTT_TOPIC_PREFIX}/{wigos_id}/data"
    published = 0

    # Group by timestamp
    for timestamp, group in df.groupby('TIMESTAMP'):
        try:
            # Format timestamp to ISO 8601
            dt = datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S")
            iso_time = dt.isoformat() + "Z"
            
            observations = []
            observation_names = []
            observation_units = []
            
            # Get the first row of the group (assuming one record per timestamp)
            row = group.iloc[0]
            
            for i, col in enumerate(header):
                if col in ['TIMESTAMP', 'RECORD', 'JobID', 'StationID', 'WMO_Block', 'Station_ID', 'Station_Name', 'WMO_Station_Type', 'M_Year', 'M_Month', 'M_DayOfMonth', 'M_HourOfDay', 'M_Minutes']:
                    continue
                
                val = row.get(col)
                try:
                    if pd.isna(val):
                        continue
                except TypeError:
                    pass

                # Convert numpy types to native Python for JSON serialization
                if hasattr(val, 'item'):
                    val = val.item()

                observation_names.append(col)
                observations.append(val)
                observation_units.append(units[i] if i < len(units) else "unitless")
            
            # Add Station_Name and Station_ID to observations
            observation_names.extend(["Station_Name", "Station_ID"])
            observations.extend([station_name, station_id])
            observation_units.extend(["", ""])

            geojson = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [0, 0] # Default coordinates, update if available
                },
                "properties": {
                    "observationNames": observation_names,
                    "observationUnits": observation_units,
                    "observations": {
                        iso_time: observations
                    }
                }
            }
            
            # Update coordinates if available in SYNOP data
            if 'Longitude' in row and 'Latitude' in row and not pd.isna(row['Longitude']) and not pd.isna(row['Latitude']):
                lon = row['Longitude'].item() if hasattr(row['Longitude'], 'item') else float(row['Longitude'])
                lat = row['Latitude'].item() if hasattr(row['Latitude'], 'item') else float(row['Latitude'])
                geojson["geometry"]["coordinates"] = [lon, lat]

            result = client.publish(topic, json.dumps(geojson), qos=0)
            published += 1
            print(f"Published to {topic} for timestamp {iso_time}")
            
        except Exception as e:
            print(f"Error publishing row for timestamp {timestamp}: {e}")

    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print(f"Done: published {published} messages to {topic}")

# Extract the datasets from the unzipped file
def extract_datasets(file_path, log_file, record_num_file, last_entry):
    dataset_count = 0
    datasets_Hour = []
    datasets_SYNOP = []
    existing_Timestamp = True

    with open(file_path, 'r', encoding='latin-1', errors='ignore') as file:  # Specify encoding as UTF-8

        lines = file.readlines()
        idx = 0
        first = True
        while idx < len(lines):
            line = lines[idx].strip()

            #Find a timestamp in the text to determine the start of a DCP message
            match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),$', line)
            if match:
                timestamp = match.group(1)

                # Check if there are at least 80 lines ending with a comma after the timestamp to filter out Alert Messages
                comma_count = sum(1 for l in lines[idx+1:idx+81] if l.strip().endswith(','))

                #Check if the data has already been saved
                date_check = search_text_in_file(timestamp, log_file)
                if date_check:
                    existing_Timestamp = True
                else:
                    existing_Timestamp = False

                if comma_count >= 80 and existing_Timestamp == False:

                    #write the timestamp to the log file
                    with open(log_file, 'a') as file:
                        file.write(timestamp + '\n')

                    #write the record number to the record_num file
                    with open(record_num_file, 'a') as file:
                        last_entry = int(last_entry) + 1 
                        file.write(str(last_entry) + '\n')

                    dataset_count += 1
                    dataset_lines = lines[idx:idx+106]  # Extract 108 lines for the dataset

                    # Convert dataset lines to DataFrame
                    dataset_df = pd.DataFrame([line.strip().split(',') for line in dataset_lines])#, dtype=dataType)
                    dataset_df = dataset_df.T

                    if first == True :
                        first = False

##### Hourly data ####
                    # Separate the data into Hourly data
                    df_H = dataset_df.iloc[:, :61]
                    # Remove the last entry (row) from the DataFrame
                    df_H = df_H.drop(df_H.index[-1])

                    #Add record number column
                    insert_index = 1
                    df_H.insert(insert_index, '', [last_entry])
                    df_H.columns = range(0, len(df_H.columns))

                    #Cast all non numeric values as numeric
                    string_list_H = [0,2,3,54,55,56]
                    for c in df_H.columns:
                        if c not in string_list_H:
                            for r, row in df_H.iterrows():
                                try:     
                                    df_H.at[r,c] = pd.to_numeric(df_H.iat[r, c], errors='coerce')
                                except (ValueError, TypeError):
                                    df_H.at[r, c] = float('NaN')

##### SYNOP data ####
                    # Separate the data into SYNOP data
                    df_S = dataset_df.iloc[:, 61:]
                    # Remove the last entry (row) from the DataFrame
                    df_S = df_S.drop(df_S.index[-1])

                    #Add timestamp column
                    insert_index = 0
                    df_S.insert(insert_index, '', [timestamp])
                    df_S.columns = range(0, len(df_S.columns))
                    #Add record number column
                    insert_index = 1
                    df_S.insert(insert_index, '', [last_entry])
                    df_S.columns = range(0, len(df_S.columns))

                    #Cast all non numeric values as numeric
                    string_list_S = [0,3,4,41]
                    for c in df_S.columns:
                        if c not in string_list_S:
                            for r, row in df_S.iterrows():
                                try:     
                                    df_S.at[r,c] = pd.to_numeric(df_S.iat[r, c], errors='coerce')
                                except (ValueError, TypeError):
                                    df_S.at[r, c] = float('NaN')

                    #Add timestamps to data
                    datasets_Hour.append((timestamp, df_H))
                    datasets_SYNOP.append((timestamp, df_S))
                    idx += 106  # Skip to the next timestamp
                    existing_Timestamp = True
                else:
                    idx += 1
            else:
                idx += 1
    return datasets_Hour, datasets_SYNOP

def search_text_in_file(line, filename):
    try:
        with open(filename, 'r') as file:
            # Read all lines from the file
            lines = file.readlines()
            
            # Iterate through each line and check if the provided line is present
            for file_line in lines:
                if line.strip() == file_line.strip():
                    return True
            return False
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        return False

#Unzips the GZ file
def unzip_gz(gz_file, output_dir=None):
    if output_dir is None:
        output_dir = os.path.dirname(gz_file)
    
    with gzip.open(gz_file, 'rb') as f_in:
        file_name = os.path.splitext(os.path.basename(gz_file))[0]
        output_path = os.path.join(output_dir, f"{file_name}.txt")
        with open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    print(f"File '{gz_file}' has been successfully unzipped to '{output_path}'")

def concatenate_datasets(datasets):
    if not datasets:
        return None  # Return None if no datasets are provided

    combined_df = pd.concat([df for _, df in datasets], ignore_index=True)
    return combined_df

def main():
   
   #File download
    autoDownload = "true"
    V_flag = "false"
    valFlag = ""
    
    if V_flag == "true":
        valFlag = "v"
    
    base_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EUMETSAT")
    stations_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stations.csv")
    
    if not os.path.exists(stations_csv):
        print(f"Error: {stations_csv} not found.")
        return

    stations_df = pd.read_csv(stations_csv)

    # Tracking sets for this run
    stations_recognized: set = set()   # downloaded without validation error
    stations_with_data: set = set()    # had at least one new datapoint

    for index, row in stations_df.iterrows():
        try:
            dcp_id = str(row['DCP ID']).strip()
            station_name = str(row['WMO_Station_Name']).strip()
            station_location = str(row['WMO_Station_Name']).strip()
            station_id = str(row['Last reported on last sat comms (LoggerStationID)']).strip()
            wigos_id = str(row['WMO_Station_ID(WIGOS ID)']).strip()
            station_SN = str(row['Serial']).strip()
            
            if not dcp_id or dcp_id == 'nan':
                continue

            print(f"\nProcessing Station: {station_name} (DCP ID: {dcp_id})")

            # Define dependent paths
            station_folder = os.path.join(base_folder, f"{station_name}_DCP_{dcp_id}")
            dev_files_folder = os.path.join(station_folder, "Dev_Files")

            DOWNLOAD_PATH = station_folder
            Log_File = os.path.join(dev_files_folder, f"{station_location}_Log.txt")
            Record_num_file = os.path.join(dev_files_folder, "Record_Num.txt")
            gz_file_path = os.path.join(station_folder, f"DCP_ID_{dcp_id}_Zipped.gz")
            unzipped_file_path = os.path.join(station_folder, f"DCP_ID_{dcp_id}_Zipped.txt")
            hourly_file_path = os.path.join(station_folder, f"{station_name}_TableHour.dat")
            SYNOP_file_path = os.path.join(station_folder, f"{station_name}_TableSYNOP.dat")

            # Create directories if they don't exist
            os.makedirs(dev_files_folder, exist_ok=True)
            os.makedirs(DOWNLOAD_PATH, exist_ok=True)

            # If the log file does not exist, create it
            if not os.path.isfile(Log_File):
                with open(Log_File, 'w') as file:
                    file.write("")

            # If the record num file does not exist, create it
            if not os.path.isfile(Record_num_file):
                with open(Record_num_file, 'w') as file:
                    file.write("")

            #Check the last record number used
            last_entry = 0
            with open(Record_num_file, 'r', errors='ignore') as file:
                lines = file.readlines()
            if lines:
                last_entry = lines[-1].strip() or 0

            urlDirectDownload = "https://" + valFlag + "service.eumetsat.int/dcswebservice/dcpAdmin.do?action=ACTION_DOWNLOAD&id=" + \
                                dcp_id + "&user=" + username + "&pass=" + password
            
            with requests.session() as s:
                if autoDownload == "true":
                    # Fetch the login page
                    r = s.get(urlDirectDownload)
                    errList = re.findall(".*Validation Error.*", r.text)
                    if len(errList) > 0:
                        print(f"Could not login or download for DCP ID {dcp_id}! Username or Password incorrect or ID invalid.")
                        continue

                    # Station was recognised on the satellite website
                    stations_recognized.add(f"{station_name} (DCP:{dcp_id} ID:{station_id})")

                    print("Filename: " + gz_file_path)
                    open(gz_file_path, 'wb').write(r.content)

            #Unzip gz file
            unzip_gz(gz_file_path)

            # File Processing
            datasets_Hour, datasets_SYNOP = extract_datasets(unzipped_file_path, Log_File, Record_num_file, last_entry)

            #Deletes the downloaded txt files
            if os.path.exists(gz_file_path): os.remove(gz_file_path)
            if os.path.exists(unzipped_file_path): os.remove(unzipped_file_path)

            #Define headers for both tables
            header_Hour = ['TIMESTAMP','RECORD','JobID','StationID','WSpd_min','WSpd_max','WSpd_avg','WSpd_std','WDir','AirTemp_avg','RH','RH_avg','SlrW_avg','SlrW_tot','Sun_Hours','Rain','BPress_avg','QFE_avg','QNH_avg','QNH_ICAO_avg','Bpress','BPress_Success','LeafWetkOhms','LeafWetkOhms_tot','VWC_5cm_avg','SoilTemp_5cm','ECBulk_5cm','VWC_10cm','SoilTemp_10cm','ECBulk_10cm','VWC_20cm','SoilTemp_20cm','ECBulk_20cm','VWC_30cm','SoilTemp_30cm','ECBulk_30cm','VWC_40cm','SoilTemp_40cm','ECBulk_40cm','VWC_50cm','SoilTemp_50cm','ECBulk_50cm','VWC_60cm','SoilTemp_60cm','ECBulk_60cm','VWC_75cm','SoilTemp_75cm','ECBulk_75cm','VWC_100cm','SoilTemp_100cm','ECBulk_100cm','ET_Shortgrass_1h','SlrMJ_ClearSky_1h','Evap_Calc_1h','LoggerSerialNumber','ProgramName','ProgramSignature','LoggerBattery','LoggerTemp','LoggerLithiumBatt','PingTime','ScanCount'] #62 fields
            header_SYNOP = ["TIMESTAMP", "RECORD", "WMO_Block", "Station_ID", "Station_Name", "WMO_Station_Type", "M_Year", "M_Month", "M_DayOfMonth", "M_HourOfDay", "M_Minutes", "Latitude", "Longitude", "Elevation", "BP_Elevation", "BP", "QNH", "BP_Change", "BP_Tendency", "Temp_H", "AirTempK", "DewPointTempK", "RH", "Sun_hr", "SunHrs", "Sun_hr24", "SunHrs24", "Rain_H", "Rain_hr", "Rain_mm_Tot", "Temp_hr24", "Temp24T", "AirTempMaxK", "AirTempMinK", "WSpeed_height", "Wind_Type", "Wind_Sig", "Wind_T", "WSPeed", "WindDir", "WSpeed10M_Avg", "WindG_Sig", "WindGust", "Solar_hr", "SlrJ", "Solar_hr24", "SlrJ24"]

            #Define units for both tables
            units_Hour = ["TS","RN","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","mm","MJ/m^2","mm","mm","mm","","","","","","",""]
            units_SYNOP = ["TS","RN","","","","","","","","","","DecDeg","DecDeg","M","","","","Pa","","m","K","K","%","","minutes","","minutes","m","","mm","","","K","K","m","","","","m/s","Deg","m/s","","m/s","","J/m^2","","J/m^2"]


            #Define metadata for both tables
            metaData_Hour = ["TOA5",station_id,"CR1000X",station_SN,"CR1000X.Std.07","CPU:ZMD_J5580_V1R1_20231108.cr1x",station_SN,"TableHour"]
            metaData_SYNOP = ["TOA5", station_id, "", "", "", "", "", "SYNOP"]

            #Define datatype for both tables
            dtype_Hour = ["","","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp"]
            dtype_SYNOP = ["","","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Tot","Smp","Smp","Smp","Smp","Tot","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","WVc","WVc","Smp","Smp","Smp","Smp","Tot","Smp","Smp"]


            # Combine datasets into one DataFrame
            combined_H_df = concatenate_datasets(datasets_Hour)
            combined_S_df = concatenate_datasets(datasets_SYNOP)        

            if combined_H_df is not None or combined_S_df is not None:
                stations_with_data.add(f"{station_name} (DCP:{dcp_id} ID:{station_id})")

            if combined_H_df is not None:
                FilePresentH = os.path.exists(hourly_file_path) and os.path.getsize(hourly_file_path) > 0
                combined_H_df.columns = header_Hour
               
                if FilePresentH:
                    combined_H_df.to_csv(hourly_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC, na_rep='')
                else:
                    with open(hourly_file_path, 'w', newline='') as file:
                        writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
                        writer.writerow(metaData_Hour)
                        writer.writerow(header_Hour)
                        writer.writerow(units_Hour)
                        writer.writerow(dtype_Hour)
                    combined_H_df.to_csv(hourly_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC, na_rep='')
                
                # Publish Hourly data to MQTT
                publish_to_mqtt(combined_H_df, wigos_id, station_id, station_name, header_Hour, units_Hour)
            else:
                print(f"No new Hourly data for {station_name}")

            if combined_S_df is not None:
                FilePresentS = os.path.exists(SYNOP_file_path) and os.path.getsize(SYNOP_file_path) > 0
                combined_S_df.columns = header_SYNOP

                if FilePresentS:
                    combined_S_df.to_csv(SYNOP_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC)
                else:
                    with open(SYNOP_file_path, 'w', newline='') as file:
                        writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
                        writer.writerow(metaData_SYNOP)
                        writer.writerow(header_SYNOP)
                        writer.writerow(units_SYNOP)
                        writer.writerow(dtype_SYNOP)
                    combined_S_df.to_csv(SYNOP_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC)
                
                # Publish SYNOP data to MQTT
                publish_to_mqtt(combined_S_df, wigos_id, station_id, station_name, header_SYNOP, units_SYNOP)
            else:
                print(f"No new SYNOP data for {station_name}")

        except Exception as e:
            print(f"Error processing station {row.get('WMO_Station_Name', 'Unknown')}: {e}")
            continue

    # ── End-of-run summary ──────────────────────────────────────────────────
    total_in_csv = sum(
        1 for _, r in stations_df.iterrows()
        if str(r.get('DCP ID', '')).strip() not in ('', 'nan')
    )
    print(f"\n=== Run summary ===")
    print(f"  Stations in CSV:              {total_in_csv}")
    print(f"  Recognised on satellite site: {len(stations_recognized)}")
    print(f"  Stations with new datapoints: {len(stations_with_data)}")

    _post_report("eumetsat_stations_in_csv", str(total_in_csv))
    _post_report("eumetsat_stations_recognised", str(len(stations_recognized)))
    _post_report("eumetsat_stations_with_data", str(len(stations_with_data)))

    _write_station_log(stations_recognized, stations_with_data)

def main_old():
   
   #File download
    autoDownload = "true"
    V_flag = "false"
    valFlag = ""
    FilePresentH = True
    FilePresentS = True
    
    if V_flag == "true":
        valFlag = "v"
    
    # Print input arguments if correct
    print("Username: " + username + ", password: " + password + ", dcp id: " + dcp_id)
    print("Download Path: " + DOWNLOAD_PATH)
    
    url = "https://" + valFlag + "service.eumetsat.int/dcswebservice/logon.do"
    payload = {'username': username, 'password': password, 'submit': 'Submit'}
    urlDownload = "https://" + valFlag + "service.eumetsat.int/dcswebservice/dcpAdmin.do?action=ACTION_DOWNLOAD&id=" + dcp_id
    
    urlDirectDownload = "https://" + valFlag + "service.eumetsat.int/dcswebservice/dcpAdmin.do?action=ACTION_DOWNLOAD&id=" + \
                        dcp_id + "&user=" + username + "&pass=" + password
    
    with requests.session() as s:
        
        if autoDownload == "true":
            # Fetch the login page
            r = s.get(urlDirectDownload)
            errList = re.findall(".*Validation Error.*", r.text)
            if len(errList) > 0:
                print("Could not login! Username or Password incorrect!")
                sys.exit()
        
            # Generate the filename based on the dcp_id
            filename = f"{DOWNLOAD_PATH}/DCP_ID_{dcp_id}_Zipped.gz"
    
            print("Filename: " + filename)
            open(filename, 'wb').write(r.content)

    #Unzip gz file
    unzip_gz(gz_file_path)

    # File Processing
    datasets_Hour, datasets_SYNOP = extract_datasets(unzipped_file_path, last_entry)

    #Deletes the downloaded txt files
    os.remove(gz_file_path)
    os.remove(unzipped_file_path)

    #Define headers for both tables
    header_Hour = ['TIMESTAMP','RECORD','JobID','StationID','WSpd_min','WSpd_max','WSpd_avg','WSpd_std','WDir','AirTemp_avg','RH','RH_avg','SlrW_avg','SlrW_tot','Sun_Hours','Rain','BPress_avg','QFE_avg','QNH_avg','QNH_ICAO_avg','Bpress','BPress_Success','LeafWetkOhms','LeafWetkOhms_tot','VWC_5cm_avg','SoilTemp_5cm','ECBulk_5cm','VWC_10cm','SoilTemp_10cm','ECBulk_10cm','VWC_20cm','SoilTemp_20cm','ECBulk_20cm','VWC_30cm','SoilTemp_30cm','ECBulk_30cm','VWC_40cm','SoilTemp_40cm','ECBulk_40cm','VWC_50cm','SoilTemp_50cm','ECBulk_50cm','VWC_60cm','SoilTemp_60cm','ECBulk_60cm','VWC_75cm','SoilTemp_75cm','ECBulk_75cm','VWC_100cm','SoilTemp_100cm','ECBulk_100cm','ET_Shortgrass_1h','SlrMJ_ClearSky_1h','Evap_Calc_1h','LoggerSerialNumber','ProgramName','ProgramSignature','LoggerBattery','LoggerTemp','LoggerLithiumBatt','PingTime','ScanCount'] #62 fields
    header_SYNOP = ["TIMESTAMP", "RECORD", "WMO_Block", "Station_ID", "Station_Name", "WMO_Station_Type", "M_Year", "M_Month", "M_DayOfMonth", "M_HourOfDay", "M_Minutes", "Latitude", "Longitude", "Elevation", "BP_Elevation", "BP", "QNH", "BP_Change", "BP_Tendency", "Temp_H", "AirTempK", "DewPointTempK", "RH", "Sun_hr", "SunHrs", "Sun_hr24", "SunHrs24", "Rain_H", "Rain_hr", "Rain_mm_Tot", "Temp_hr24", "Temp24T", "AirTempMaxK", "AirTempMinK", "WSpeed_height", "Wind_Type", "Wind_Sig", "Wind_T", "WSPeed", "WindDir", "WSpeed10M_Avg", "WindG_Sig", "WindGust", "Solar_hr", "SlrJ", "Solar_hr24", "SlrJ24"]

    #Define units for both tables
    units_Hour = ["TS","RN","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","mm","MJ/m^2","mm","mm","mm","","","","","","",""]
    units_SYNOP = ["TS","RN","","","","","","","","","","DecDeg","DecDeg","M","","","","Pa","","m","K","K","%","","minutes","","minutes","m","","mm","","","K","K","m","","","","m/s","Deg","m/s","","m/s","","J/m^2","","J/m^2"]


    #Define metadata for both tables
    metaData_Hour = ["TOA5",station_id,"CR1000X",station_SN,"CR1000X.Std.07","CPU:ZMD_J5580_V1R1_20231108.cr1x",station_SN,"TableHour"]
    metaData_SYNOP = ["TOA5", station_id, "", "", "", "", "", "SYNOP"]

    #Define datatype for both tables
    dtype_Hour = ["","","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp"]
    dtype_SYNOP = ["","","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Tot","Smp","Smp","Smp","Smp","Tot","Smp","Smp","Smp","Smp","Smp","Smp","Smp","Smp","WVc","WVc","Smp","Smp","Smp","Smp","Tot","Smp","Smp"]


    # Combine datasets into one DataFrame
    combined_H_df = concatenate_datasets(datasets_Hour)
    combined_S_df = concatenate_datasets(datasets_SYNOP)        

    if combined_H_df is not None:

        combined_H_df.columns = header_Hour
       
        # If the file does not exist, create it
        if not os.path.isfile(hourly_file_path):
            with open(hourly_file_path, 'w') as file:
                file.write("")
                FilePresentH = False

        if FilePresentH:
            combined_H_df.columns = header_Hour
            combined_H_df.to_csv(hourly_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC, na_rep='')
        else:
            with open(hourly_file_path, 'r') as file:
                reader = csv.reader(file)
                existing_data = list(reader)

            existing_data.insert(0, metaData_Hour)
            existing_data.insert(1, header_Hour)
            existing_data.insert(2, units_Hour)
            existing_data.insert(3, dtype_Hour)
            FilePresentH = True

            with open(hourly_file_path, 'w', newline='') as file:
                writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
                writer.writerows(existing_data)

            combined_H_df.to_csv(hourly_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC, na_rep='')
    else:
        print("No new Hourly data")

    if combined_S_df is not None:

        combined_S_df.columns = header_SYNOP
        #print(combined_S_df)

        # If the file does not exist, create it
        if not os.path.isfile(SYNOP_file_path):
            with open(SYNOP_file_path, 'w') as file:
                file.write("")
                FilePresentS = False

        if FilePresentS:
            combined_S_df.columns = header_SYNOP
            combined_S_df.to_csv(SYNOP_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC)
        else:
            with open(SYNOP_file_path, 'r') as file:
                reader = csv.reader(file)
                existing_data = list(reader)

            existing_data.insert(0, metaData_SYNOP)
            existing_data.insert(1, header_SYNOP)
            existing_data.insert(2, units_SYNOP)
            existing_data.insert(3, dtype_SYNOP)
            FilePresentS = True

            with open(SYNOP_file_path, 'w', newline='') as file:
                writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
                writer.writerows(existing_data)

            combined_S_df.to_csv(SYNOP_file_path, mode='a', header=False, index=False, quoting=csv.QUOTE_NONNUMERIC)

    else:
        print("No new SYNOP data")

if __name__ == "__main__":
    main()