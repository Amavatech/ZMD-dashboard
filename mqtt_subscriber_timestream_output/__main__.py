from jmespath import search
from pymysql import DateFromTicks
import requests
from sqlalchemy import table,event
from multiprocessing import shared_memory,Process, resource_tracker
import timescaleUtil as ts
import configUtil as config
import paho.mqtt.client as mqtt
import os, sys, json,queue,threading, logging,time,re,datetime,pytz,atexit
import mySqlUtil
import grafana_helpers
from dateutil import parser

def remove_shm_from_resource_tracker():
    """Monkey-patch multiprocessing.resource_tracker so SharedMemory won't be tracked

    More details at: https://bugs.python.org/issue38119
    """

    def fix_register(name, rtype):
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.register(self, name, rtype)
    resource_tracker.register = fix_register

    def fix_unregister(name, rtype):
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.unregister(self, name, rtype)
    resource_tracker.unregister = fix_unregister

    if "shared_memory" in resource_tracker._CLEANUP_FUNCS:
        del resource_tracker._CLEANUP_FUNCS["shared_memory"]

remove_shm_from_resource_tracker()
try:
    messages=shared_memory.ShareableList(name="messages")
except FileNotFoundError:
    messages=shared_memory.ShareableList([False,int(-1),'X'],name="messages")

class HourlyDirHandler(logging.Handler):
    def __init__(self, base_dir="logs"):
        super().__init__()
        self.base_dir = base_dir

    def emit(self, record):
        try:
            msg = self.format(record)
            now = datetime.datetime.now()
            month_dir = os.path.join(self.base_dir, now.strftime("%Y-%m"))
            day_dir = os.path.join(month_dir, now.strftime("%d"))
            os.makedirs(day_dir, exist_ok=True)
            filename = os.path.join(day_dir, now.strftime("%H.log"))
            with open(filename, "a", encoding='utf-8') as f:
                f.write(msg + "\n")
        except Exception:
            self.handleError(record)

class StreamToLogger(object):
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        self.lock = threading.Lock()

    def write(self, buf):
        with self.lock:
            for char in buf:
                if char == '\n':
                    self.logger.log(self.log_level, self.linebuf.rstrip())
                    self.linebuf = ''
                else:
                    self.linebuf += char

    def flush(self):
        with self.lock:
            if self.linebuf:
                self.logger.log(self.log_level, self.linebuf.rstrip())
                self.linebuf = ''

# Ensure TimescaleDB is ready
ts.ensure_database()
ts.ensure_extension()

# Setup logging
original_stdout = sys.stdout
original_stderr = sys.stderr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter with timestamps
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Hourly file handler with directory structure
_log_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
file_handler = HourlyDirHandler(base_dir=_log_base_dir)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler (to original stdout)
console_handler = logging.StreamHandler(original_stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Redirect stdout and stderr
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)

#Set timezone of the device to Africa. Can be changed if timezone is different
sa=pytz.timezone("Africa/Johannesburg")

brokerIDs=[]
clients=[]
threads=[]
message_queue=queue.LifoQueue(maxsize=1000)

# Daily statistics
REPORT_ENDPOINT = "http://16.28.16.60:3000/api/report/cmm7yibi4khzco01lckk56ivo"
stats_lock = threading.Lock()
daily_packet_count = 0
daily_unique_stations = set()
_stats_date = datetime.date.today()
last_message_time = datetime.datetime.utcnow()  # updated on every incoming MQTT message
SILENCE_RECONNECT_MINUTES = 15  # force reconnect if no messages received for this long
_silence_triggered = False  # set True when watchdog fires; cleared on next message

# Thread crash tracking: {thread_name: error_message}
crash_lock = threading.Lock()
crashed_threads: dict = {}

# ---------------------------------------------------------------------------
# Station contact tracking
# ---------------------------------------------------------------------------
STATION_CONTACTS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "station_contacts.csv",
)
station_contacts_lock = threading.Lock()
station_contacts: dict = {}  # {station_id: {last_contact, has_valid_data, last_error}}


def _sort_key_station_id(sid: str):
    """Sort key: pure integers first, then trailing-integer strings, then alpha."""
    try:
        return (0, int(sid), "")
    except (ValueError, TypeError):
        m = re.search(r'(\d+)$', str(sid))
        if m:
            return (0, int(m.group(1)), str(sid))
        return (1, 0, str(sid))


def load_station_contacts():
    """Load existing station contacts from CSV on startup (if present)."""
    import csv
    if not os.path.exists(STATION_CONTACTS_FILE):
        return
    try:
        with open(STATION_CONTACTS_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = row.get("station_id", "").strip()
                if sid:
                    station_contacts[sid] = {
                        "last_contact": row.get("last_contact", ""),
                        "has_valid_data": row.get("has_valid_data", "False").strip().lower() == "true",
                        "last_error": row.get("last_error", ""),
                    }
        logging.info("Loaded %d station contacts from %s", len(station_contacts), STATION_CONTACTS_FILE)
    except Exception as exc:
        logging.warning("Failed to load station contacts: %s", exc)


def write_station_contacts_csv():
    """Write the station contact log, sorted by station ID, to CSV."""
    import csv
    try:
        with station_contacts_lock:
            contacts_snapshot = dict(station_contacts)
        sorted_ids = sorted(contacts_snapshot.keys(), key=_sort_key_station_id)
        tmp_path = STATION_CONTACTS_FILE + ".tmp"
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["station_id", "last_contact", "has_valid_data", "last_error"],
            )
            writer.writeheader()
            for sid in sorted_ids:
                entry = contacts_snapshot[sid]
                writer.writerow({
                    "station_id": sid,
                    "last_contact": entry.get("last_contact", ""),
                    "has_valid_data": entry.get("has_valid_data", False),
                    "last_error": entry.get("last_error", ""),
                })
        os.replace(tmp_path, STATION_CONTACTS_FILE)
    except Exception as exc:
        logging.warning("Failed to write station contacts CSV: %s", exc)


def _update_station_contact(station_id: str, has_valid_data: bool = False, error: str = ""):
    """Thread-safe update of a station's contact record."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with station_contacts_lock:
        existing = station_contacts.get(str(station_id), {})
        station_contacts[str(station_id)] = {
            "last_contact": now,
            "has_valid_data": existing.get("has_valid_data", False) or has_valid_data,
            "last_error": error if error else existing.get("last_error", ""),
        }

def Connect(client,broker,port,keepalive,run_forever=False):
    """Attempts connection set delay to >1 to keep trying
    but at longer intervals. If runforever flag is true then
    it will keep trying to connect or reconnect indefinetly otherwise
    gives up after 3 failed attempts"""
    connflag=False
    delay=5
    #print("connecting ",client)
    badcount=0 # counter for bad connection attempts
    while not connflag:
        logging.info("connecting to broker "+str(broker))
        #print("connecting to broker "+str(broker)+":"+str(port))
        logging.info("Attempts "+str(badcount))
        time.sleep(delay)
        try:
            client.connect(broker,port,keepalive)
            connflag=True

        except Exception as exc:
            client.badconnection_flag=True
            logging.error("connection failed %s: %s", badcount, exc)
            badcount +=1
            if badcount>=15: 
                return -1
                raise SystemExit #give up             
    return 0

def wait_for(client,msgType,period=1,wait_time=10,running_loop=False):
    """Will wait for a particular event gives up after period*wait_time, Default=10
seconds.Returns True if succesful False if fails"""
    #running loop is true when using loop_start or loop_forever
    client.running_loop=running_loop #
    wcount=0  
    while True:
        logging.info("waiting"+ msgType)
        if msgType=="CONNACK":
            if client.on_connect:
                if client.connected_flag:
                    return True
                if client.bad_connection_flag: #
                    return False
                
        if msgType=="SUBACK":
            if client.on_subscribe:
                if client.suback_flag:
                    return True
        if msgType=="MESSAGE":
            if client.on_message:
                if client.message_received_flag:
                    return True
        if msgType=="PUBACK":
            if client.on_publish:        
                if client.puback_flag:
                    return True
     
        if not client.running_loop:
            client.loop(.01)  #check for messages manually
        time.sleep(period)
        wcount+=1
        if wcount>wait_time:
            logging.info("return from wait loop taken too long")
            return False
    return True

def client_loop(client,broker,port,keepalive=60,loop_function=None,\
             loop_delay=1,run_forever=False):
    """runs a loop that will auto reconnect and subscribe to topics
    pass topics as a list of tuples. You can pass a function to be
    called at set intervals determined by the loop_delay
    """
    client.run_flag=True
    client.broker=broker
    logging.info(f"running loop for broker {client.brokerID}")
    client.reconnect_delay_set(min_delay=1, max_delay=12)
      
    while client.run_flag: #loop forever

        if client.bad_connection_flag:
            break         
        if not client.connected_flag:
            logging.info("Connecting to "+str(broker))
            if Connect(client,broker,port,keepalive,run_forever) !=-1:
                if not wait_for(client,"CONNACK"):
                   client.run_flag=False #break no connack
            else:#connect fails
                client.run_flag=False #break
                logging.info("quitting loop for  broker "+str(broker))

        client.loop(1)

        if client.connected_flag and loop_function: #function to call
                loop_function(client,loop_delay) #call function
    time.sleep(1)
    logging.info("disconnecting from"+str(broker))
    if client.connected_flag:
        client.disconnect()
        client.connected_flag=False

def _infer_station_id(payload: dict, topic: str) -> str:
    """Infer the canonical station ID from a message payload and/or topic.

    Priority:
      1. DB-stored station_id for this topic (source of truth for known topics)
      2. Numeric ID extracted from the topic path (4+ digit WMO ID)
      3. Station_Name / Station_ID from the payload (for non-SYNOP topics with no numeric)
      4. Vendor code / last path segment from `_extract_station_id`
    """
    # 1. DB lookup: if this topic is already registered, use its stored station_id
    try:
        db_row = mySqlUtil.get_timestream_table(topic)
        if db_row and db_row.station_id:
            return db_row.station_id
    except Exception:
        pass

    # 2. Prefer numeric WMO ID from topic path for new/unregistered topics
    candidate = mySqlUtil._extract_station_id(topic)
    import re as _re
    if _re.match(r'^\d{4,}$', candidate):
        return candidate

    # 3. For topics without a numeric path segment, try payload Station_Name
    try:
        names = payload.get("properties", {}).get("observationNames", [])
        observations = payload.get("properties", {}).get("observations", {})
        if observations:
            first_time = next(iter(observations.keys()))
            values = observations.get(first_time, [])
            name_to_val = dict(zip(names, values))
            station_name = name_to_val.get("Station_Name")
            if station_name:
                return str(station_name)
            station_id = name_to_val.get("Station_ID")
            if station_id:
                return str(station_id)
    except Exception:
        pass

    # 4. Fall back to whatever _extract_station_id derived (vendor code / last segment)
    return candidate


def message_to_timescale(msg,brokerID=1):
    #Restart mysql session in case connection is lost.
    mySqlUtil.restart_session()
    _current_station_id = None  # track for error reporting
    
    # Get broker info for logging
    broker_info = mySqlUtil.get_broker_by_id(brokerID)
    broker_name = f"{broker_info.name} ({broker_info.URL}:{broker_info.port})" if broker_info else f"Broker {brokerID}"

    format="geojson"

    #Check to see if message is in JSON format, if not then exit
    #logging.info(f"Message from broker {brokerID}, topic `{msg.topic}`")
    try:
        s=msg.payload.decode().replace(",NAN",",null")
        payload = json.loads(s)
    except Exception as exc:
        logging.info("Not a json message: %s", exc)
        return
    topic=msg.topic
    

    topics=re.split("/",topic)


    #Check topic to see if the data should be stored.
    # if(re.search("hour",topics[-1])):
    #     logging.info("Listening for every 5/10 minutes")
    #     return
    if(re.search("5_min",topics[-1]) or re.search("Table10m",topics[-1]) or re.search("Table10M",topics[-1])):
        topic=""
        for t in topics[:-1]:
            topic=topic+"/"+t
    #Check to see if data is in CSIJSON format
    elif(topics[-1]=="cj"):
        format="csijson"
        topic=""
        for t in topics[:-2]:
            topic=topic+"/"+t

    if topic[0]=='/':
        topic=topic[1:]
    if topic[-1]=='/':
        topic=topic[0:-1]
    commit=False
    long=0
    lat=0

    is_state=False
    for t in topics:
        if t=="state":
            is_state=True
            break
    if is_state:
        return
    
    logging.info("Message from %s [Broker: %s]", topic, broker_name)
    if False:
        topic=""
        try:
            for t in topics[:-1]:
                if t=="state":
                    t="data"
                topic=topic+"/"+t

            if topic[0]=='/':
                topic=topic[1:]
            if topic[-1]=='/':
                topic=topic[0:-1]

            target_topics=mySqlUtil.get_timestream_tables_substring(topic)

            if not target_topics:
                _sid = mySqlUtil._extract_station_id(topic)
                ts.create_table(config.timescale.database, f"st_{_sid}")
                mySqlUtil.add_timestream_table(topic,brokerID,True)
                commit=True
                logging.info("Creating new timestream table for station_id=%s", _sid)
                target_topics=[topic]

            state=""
            battery=""
            low_12volt=""
            watchdog_errors=""
            program_signature=""
            isOnline=False
            if payload["state"]=="online":
                state=payload["state"] 
                isOnline=True
            else:
                battery=payload["state"]["reported"]["Battery"]
                low_12volt=payload["state"]["reported"]["Low_12volt"]
                watchdog_errors=payload["state"]["reported"]["Watchdog_Errors"]
                program_signature=payload["state"]["reported"]["Program_Signature"]

            for target in target_topics:
                if isOnline:
                    if(not mySqlUtil.does_timestream_measurement_exist(target.topic,"state")):
                        mySqlUtil.add_timestream_measurement(target.topic,"state","unitless","VARCHAR",True,True)
                        commit=True
                    record_dimensions=[{'Name':'unit','Value':"unitless"},{'Name':'Measurement Type','Value':'VARCHAR'}]
                    dt=datetime.datetime.now(datetime.timezone.utc)
                    dt=dt.replace(tzinfo=datetime.timezone.utc)
                    record_time=str(1000*int(dt.timestamp()))

                    record=[{
                            'Dimensions':record_dimensions,
                            'MeasureValueType':"VARCHAR",
                            'Time': record_time,
                            'MeasureName':"state",
                            'MeasureValue':state
                    }]

                    _tbl = f"st_{target.station_id}" if target.station_id else target.topic.replace('/','_')
                    ts.write_records(config.timescale.database, _tbl, record)

                else:
                    if(not mySqlUtil.does_timestream_measurement_exist(target.topic,"battery")):
                        mySqlUtil.add_timestream_measurement(target.topic,"battery","unitless","VARCHAR",True,True)
                        commit=True
                    if(not mySqlUtil.does_timestream_measurement_exist(target.topic,"low_12volt")):
                        mySqlUtil.add_timestream_measurement(target.topic,"low_12volt","unitless","VARCHAR",True,True)
                        commit=True
                    if(not mySqlUtil.does_timestream_measurement_exist(target.topic,"watchdog_errors")):
                        mySqlUtil.add_timestream_measurement(target.topic,"watchdog_errors","unitless","VARCHAR",True,True)
                        commit=True
                    if(not mySqlUtil.does_timestream_measurement_exist(target.topic,"program_signature")):
                        mySqlUtil.add_timestream_measurement(target.topic,"program_signature","unitless","VARCHAR",True,True)
                        commit=True

                    record_dimensions=[{'Name':'unit','Value':"unitless"},{'Name':'Measurement Type','Value':'VARCHAR'}]
                    dt=datetime.datetime.now(datetime.timezone.utc)
                    dt=dt.replace(tzinfo=datetime.timezone.utc)
                    record_time=str(1000*int(dt.timestamp()))

                    records=[{
                            'Dimensions':record_dimensions,
                            'MeasureValueType':"VARCHAR",
                            'Time': record_time,
                            'MeasureName':"battery",
                            'MeasureValue':battery
                    },
                    {
                            'Dimensions':record_dimensions,
                            'MeasureValueType':"VARCHAR",
                            'Time': record_time,
                            'MeasureName':"low_12volt",
                            'MeasureValue':low_12volt
                    },
                    {
                            'Dimensions':record_dimensions,
                            'MeasureValueType':"VARCHAR",
                            'Time': record_time,
                            'MeasureName':"watchdog_errors",
                            'MeasureValue':watchdog_errors
                    },
                    {
                            'Dimensions':record_dimensions,
                            'MeasureValueType':"VARCHAR",
                            'Time': record_time,
                            'MeasureName':"program_signature",
                            'MeasureValue':program_signature
                    }]

                    _tbl = f"st_{target.station_id}" if target.station_id else target.topic.replace('/','_')
                    ts.write_records(config.timescale.database, _tbl, records)

                if(commit):
                    #If mysql details changed(measurements or a new topic), create a new grafana dashboard and commit changes to the mysql database
                    mySqlUtil.create_dashboard_table(target)
                    mySqlUtil.session.commit()
                    return
        except:
            mySqlUtil.restart_session()

    try:
        if(format=="geojson"):
            if("geometry" in payload.keys()):
                try:
                    #Get longitude from message
                    long=payload["geometry"]["coordinates"][1]
                except:
                    long=0
                try:
                    #Get latitude from message
                    lat=payload["geometry"]["coordinates"][0]
                except:
                    lqt=0
            if("properties" in payload.keys()):
                # First check if observations exist before creating table
                if "observations" not in payload["properties"] or "observationNames" not in payload["properties"]:
                    logging.info("Skipping message with no observations or observationNames for topic %s", topic)
                    return
                
                #Check to see if the topic has an existing timestream table, if not then create it.
                if not mySqlUtil.does_timestream_table_exist(topic):
                    logging.info("Timescale table missing, creating for topic=%s [Broker: %s]", topic, broker_name)
                    _sid = mySqlUtil._extract_station_id(topic)
                    ts.create_table(config.timescale.database, f"st_{_sid}")
                    mySqlUtil.add_timestream_table(topic,brokerID,True)
                    commit=True
                    logging.info("Creating new timestream table for station_id=%s", _sid)

                has_units="observationUnits" in payload["properties"].keys()
                
                times=list(payload["properties"]["observations"].keys())
                obs_names_count = len(payload["properties"]["observationNames"])
                logging.info("GeoJSON observations=%s timepoints=%s [Broker: %s]", obs_names_count, len(times), broker_name)

                station_id=_infer_station_id(payload, topic)
                _current_station_id = station_id
                _update_station_contact(station_id)
                logging.info("Derived station_id=%s", station_id)
                with stats_lock:
                    daily_unique_stations.add(station_id)
                if times:
                    try:
                        parsed_times = [parser.isoparse(t).astimezone(pytz.UTC) for t in times]
                        logging.info(
                            "GeoJSON time window UTC: min=%s max=%s (count=%s)",
                            min(parsed_times),
                            max(parsed_times),
                            len(parsed_times),
                        )
                    except Exception as exc:
                        logging.warning("Failed to parse GeoJSON times: %s", exc)
                #Do this for each timepoint in the data received:
                for cur_time in times:
                    count=0
                    records=[]
                    weather_rows=[]
                    #Do this for each observation(measurement) in the timepoint:
                    for observation_name in payload["properties"]["observationNames"]:

                        unit=""
                        if has_units:
                            unit=payload["properties"]["observationUnits"][count]
                            if(unit==""):
                                unit="unitless"
                        else:
                            unit="unitless"

                        record_type="DOUBLE"
                        record_dimensions=[{'Name':'unit','Value':unit},{'Name':'Measurement Type','Value':'DOUBLE'}]

                        if(type(payload["properties"]["observations"][cur_time][count])==str):
                            record_dimensions[1]['Value']='VARCHAR'
                            record_type="VARCHAR" #set record type to varchar if a string is sent
                        

                        #Check to see if the measurement exists in the MySQL database, if not then create it
                        if(not mySqlUtil.does_timestream_measurement_exist(topic,observation_name)):
                            mySqlUtil.add_timestream_measurement(topic,observation_name,unit,record_type,False)
                            commit=True

                        record_time=""

                        #Check to see if the server time should be used. If not the time found in the payload is used.
                        if config.timescale.use_current_time:
                            dt = datetime.datetime.now(datetime.timezone.utc)
                            time_source = "server"
                        else:
                            dt = parser.isoparse(cur_time)  # Parse time
                            dt = dt.astimezone(pytz.UTC)  # Transform this to UTC
                            time_source = "payload"

                        record_time = str(1000 * int(dt.timestamp()))  # Get the timestamp in ms

                        if(payload["properties"]["observations"][cur_time][count]):
                            record_value=str(payload["properties"]["observations"][cur_time][count])#Get record value
                        else:
                            record_value='0'

                        #Add the observation details to the records to be written to Timescale per-topic table
                        records.append(
                            {
                                'Dimensions':record_dimensions,
                                'MeasureValueType':record_type,
                                'Time': record_time,
                                'MeasureName':observation_name,
                                'MeasureValue':record_value
                            }
                        )

                        try:
                            if record_type == "DOUBLE":
                                weather_value = float(record_value)
                            else:
                                weather_value = None
                        except Exception:
                            weather_value = None

                        weather_rows.append((dt, station_id, observation_name, weather_value))

                        count+=1
                    _tbl = f"st_{station_id}"
                    ts.write_records(config.timescale.database, _tbl, records)
                    table = mySqlUtil.get_timestream_table(topic)
                    topic_id = table.tableID if table else "unknown"
                    logging.info(
                        "Wrote %s records to Timescale table %s (topicID=%s time_source=%s record_time=%s) [Broker: %s]",
                        len(records),
                        _tbl,
                        topic_id,
                        time_source,
                        dt.isoformat(),
                        broker_name,
                    )
                    ts.write_weather_data(weather_rows)
                    _update_station_contact(station_id, has_valid_data=True)
                    logging.info(
                        "Wrote %s records to weather_data (topicID=%s station_id=%s time_source=%s record_time=%s) [Broker: %s]",
                        len(weather_rows),
                        topic_id,
                        station_id,
                        time_source,
                        dt.isoformat(),
                        broker_name,
                    )
                
        elif(format=="csijson"):
            #Check to see if the topic has an existing timestream table, if not then create it.
            if not mySqlUtil.does_timestream_table_exist(topic):
                logging.info("Timescale table missing, creating for topic=%s [Broker: %s]", topic, broker_name)
                _sid = mySqlUtil._extract_station_id(topic)
                ts.create_table(config.timescale.database, f"st_{_sid}")
                mySqlUtil.add_timestream_table(topic,brokerID,True)
                commit=True
                logging.info("Creating new timestream table for station_id=%s", _sid)
            cur_time=payload["data"][0]["time"]

            #Check to see if the server time should be used. If not the time found in the payload is used.
            if config.timescale.use_current_time:
                dt = datetime.datetime.now(datetime.timezone.utc)
            else:
                dt = parser.isoparse(cur_time)  # Parse time
                dt = dt.astimezone(pytz.UTC)  # Transform to UTC

            record_time = str(1000 * int(dt.timestamp()))  # Get timestamp in ms

            records=[]
            weather_rows=[]
            station_id=_infer_station_id(payload, topic)
            _current_station_id = station_id
            _update_station_contact(station_id)
            with stats_lock:
                daily_unique_stations.add(station_id)
            logging.info("CSIJSON observations=%s station_id=%s [Broker: %s]", len(payload["head"]["fields"]), station_id, broker_name)
            #Do for each observation in the timestep:
            for field,val in zip(payload["head"]["fields"],payload["data"][0]["vals"]):
                observation_name=field["name"]
                if("units" in field.keys()):
                    unit=field["units"]
                else:
                    unit="unitless"
                record_type="DOUBLE"
                record_dimensions=[{'Name':'unit','Value':unit},{'Name':'Measurement Type','Value':'DOUBLE'}]

                if(type(val)==str):
                    record_dimensions[1]['Value']='VARCHAR'
                    record_type="VARCHAR"

                #Check to see if the measurement exists in the MySQL database, if not then create it
                if(not mySqlUtil.does_timestream_measurement_exist(topic,observation_name)):
                    mySqlUtil.add_timestream_measurement(topic,observation_name,unit,record_type,False)
                    commit=True
                
                if(val):
                    record_value=str(val)
                else:
                    record_value='0'
                #Add the observation details to the records to be written to Timescale per-topic table
                records.append(
                    {
                        'Dimensions':record_dimensions,
                        'MeasureValueType':record_type,
                        'Time': record_time,
                        'MeasureName':observation_name,
                        'MeasureValue':record_value
                    }
                )
                try:
                    if record_type == "DOUBLE":
                        weather_value = float(record_value)
                    else:
                        weather_value = None
                except Exception:
                    weather_value = None
                weather_rows.append((dt, station_id, observation_name, weather_value))
            #Write the records to the Timestream database:
            _tbl = f"st_{station_id}"
            ts.write_records(config.timescale.database, _tbl, records)
            table = mySqlUtil.get_timestream_table(topic)
            topic_id = table.tableID if table else "unknown"
            logging.info("Wrote %s records to Timescale table %s (topicID=%s) [Broker: %s]", len(records), _tbl, topic_id, broker_name)
            ts.write_weather_data(weather_rows)
            _update_station_contact(station_id, has_valid_data=True)
            logging.info("Wrote %s records to weather_data (topicID=%s station_id=%s) [Broker: %s]", len(weather_rows), topic_id, station_id, broker_name)

        table=mySqlUtil.get_timestream_table(topic)
        if( table and (table.longitude!=long or table.latitude!=lat)):
            table.longitude=long
            table.latitude=lat
            commit=True
        if(commit):
            #If mysql details changed(measurements or a new topic), create a new grafana dashboard and commit changes
            try:
                mySqlUtil.create_dashboard_table(table)
            except Exception as exc:
                logging.warning("Grafana update failed for topic=%s; continuing without dashboard update: %s", topic, exc)
            finally:
                try:
                    mySqlUtil.session.commit()
                except Exception as exc:
                    logging.exception("Failed to commit metadata for topic=%s: %s", topic, exc)
                    mySqlUtil.restart_session()
    except Exception as exc:
        logging.exception("Timescale ingest failed for topic=%s: %s", topic, exc)
        _update_station_contact(_current_station_id or topic, error=str(exc))
        mySqlUtil.restart_session()

def message_worker():

    while True:
        try:
            msg = message_queue.get(timeout=1)
            message_to_timescale(msg["msg"], msg["brokerID"])
            message_queue.task_done()
        except queue.Empty:
            continue
        except Exception as exc:
            logging.exception("message_worker: unexpected error, continuing: %s", exc)
            with crash_lock:
                crashed_threads["message_worker"] = str(exc)
            try:
                message_queue.task_done()
            except Exception:
                pass


def on_connect(client, userdata, flags, rc):
    '''Function to be run when connection is made to MQTT broker.
    Subscribe to all topics if connection is good'''
    if rc==0:
        client.connected_flag=True #set flag
        logging.info(f"Connected OK to broker {client.brokerID} Returned code="+str(rc))
        client.subscribe("#")
    else:
        logging.error(f"Bad connection to broker {client.brokerID} Returned code="+str(rc))
        client.loop_stop()  

def on_subscribe(client, userdata, mid, granted_qos):
    '''Function to be run when subscribed to topic'''
    logging.info(f"Subscribed {userdata}")

def on_disconnect(client, userdata, rc):
    '''Function to be run when disconnected from MQTT broker.'''
    client.connected_flag = False
    if rc != 0:
        logging.warning(f"Unexpected disconnect from broker {client.brokerID} (rc={rc}). client_loop will reconnect.")
    else:
        logging.info(f"Disconnected cleanly from broker {client.brokerID}")

def on_message(client,userdata,msg:mqtt.MQTTMessage):
    '''Function to be run when mqtt message is received.'''
    global daily_packet_count, last_message_time, _silence_triggered
    with stats_lock:
        daily_packet_count += 1
        prev_silence = _silence_triggered
        last_message_time = datetime.datetime.utcnow()
        _silence_triggered = False
    if prev_silence:
        logging.info(
            f"MQTT messages resumed on broker {client.brokerID} "
            f"(topic: {msg.topic})"
        )
    try:
        message_queue.put_nowait({"msg": msg, "brokerID": client.brokerID})
    except queue.Full:
        # If the queue is full, remove the oldest message and add the new one
        try:
            message_queue.get_nowait()
            message_queue.put_nowait({"msg": msg, "brokerID": client.brokerID})
        except queue.Empty:
            pass

def broker_change_worker():
    while True:
        try:
            if(not messages[0]):
               continue
            else:
                messages[0]=False
                print(f'Message ID:{messages[1]} Type:{messages[2]}')
        except Exception as exc:
            logging.exception("broker_change_worker: unexpected error: %s", exc)
            with crash_lock:
                crashed_threads["broker_change_worker"] = str(exc)
            raise  # Let the thread die so is_alive() detects it

def _post_report(alias: str, value: str):
    """Send a single key/value report to the endpoint."""
    try:
        resp = requests.post(
            REPORT_ENDPOINT,
            json={"alias": alias, "value": value},
            timeout=10,
        )
        logging.info("Stats report sent: %s=%s (HTTP %s)", alias, value, resp.status_code)
    except Exception as exc:
        logging.warning("Failed to send stats report (%s): %s", alias, exc)


def stats_reporter():
    """Every 2 minutes POST daily packet count and unique station count to the
    reporting endpoint.  If a worker thread has crashed, reports the crash and
    skips normal metrics until it is resolved.  Resets daily counters at midnight.
    Also watches for prolonged message silence and forces a reconnect if detected."""
    global daily_packet_count, daily_unique_stations, _stats_date, last_message_time
    while True:
        time.sleep(120)  # 2 minutes

        # Silence watchdog: if no messages received for SILENCE_RECONNECT_MINUTES,
        # force-disconnect all clients so client_loop will reconnect and re-subscribe.
        with stats_lock:
            silence_seconds = (datetime.datetime.utcnow() - last_message_time).total_seconds()
        logging.info(
            f"Silence watchdog: {silence_seconds:.0f}s since last MQTT message "
            f"(threshold: {SILENCE_RECONNECT_MINUTES * 60}s)"
        )
        if silence_seconds > SILENCE_RECONNECT_MINUTES * 60:
            logging.warning(
                f"No MQTT messages received for {silence_seconds/60:.1f} minutes — "
                f"forcing reconnect on all {len(clients)} client(s)."
            )
            for c in clients:
                try:
                    c.disconnect()
                    logging.info(f"Force-disconnected client for broker {c.brokerID}")
                except Exception as exc:
                    logging.warning(f"Error disconnecting client for broker {c.brokerID}: {exc}")
            with stats_lock:
                last_message_time = datetime.datetime.utcnow()  # reset to avoid repeated triggers
                _silence_triggered = True

        # Check for dead threads (unhandled crash that killed the thread)
        dead = [name for name, t in _worker_threads.items() if not t.is_alive()]
        for name in dead:
            with crash_lock:
                if name not in crashed_threads:
                    crashed_threads[name] = "thread exited unexpectedly"

        # Report any known crashes and skip normal stats while system is unhealthy
        with crash_lock:
            current_crashes = dict(crashed_threads)

        crash_count = len(current_crashes)
        if current_crashes:
            for thread_name, error in current_crashes.items():
                logging.error("Crashed thread: %s — %s", thread_name, error)
        _post_report("crashed_threads", str(crash_count))

        # Normal daily stats report
        today = datetime.date.today()
        with stats_lock:
            if today != _stats_date:
                daily_packet_count = 0
                daily_unique_stations = set()
                _stats_date = today
            packets = daily_packet_count
            stations = len(daily_unique_stations)

        _post_report("daily_mqtt_packets", str(packets))
        _post_report("daily_unique_stations", str(stations))
        write_station_contacts_csv()


load_station_contacts()

_worker_threads: dict = {}
_worker_threads["message_worker"] = threading.Thread(target=message_worker, daemon=True)
_worker_threads["broker_change_worker"] = threading.Thread(target=broker_change_worker, daemon=True)
for _t in _worker_threads.values():
    _t.start()
threading.Thread(target=stats_reporter, daemon=True).start()

def on_exit():
    messages.shm.close()
    sys.stdout.flush()
    sys.stderr.flush()

mqtt.Client.connected_flag=False #create flag in class
mqtt.Client.bad_connection_flag=False #create flag in class
mqtt.Client.brokerID=1

def add_broker(broker:mySqlUtil.broker):
    client=mqtt.Client(str(broker.brokerID))
    if(broker.authentication):
        client.username_pw_set(username=broker.username,password=broker.password)
    client.on_connect=on_connect
    client.on_disconnect=on_disconnect
    client.on_subscribe=on_subscribe
    client.on_message=on_message
    client.brokerID=broker.brokerID
    clients.append(client)
    brokerIDs.append(broker.brokerID)
    t=threading.Thread(target=client_loop,args=(client,broker.URL,broker.port,60,None,1,True))
    threads.append(t)
    t.start()

@event.listens_for(mySqlUtil.broker, 'after_insert')
def receive_modified(mapper, connection, target):
    print(mapper)
    print(connection)
    print(target)



brokers = mySqlUtil.get_all_brokers()
if not brokers:
    try:
        cfg_broker = mySqlUtil.add_broker_record(
            url=config.mqtt.address,
            port=config.mqtt.port,
            authentication=config.mqtt.authentication,
            username=config.mqtt.username,
            password=config.mqtt.password,
            name="config.ini broker",
        )
        brokers = [cfg_broker]
        logging.info("Added broker from config.ini")
    except Exception as exc:
        logging.warning("Failed to add broker from config.ini: %s", exc)

for broker in brokers:
    add_broker(broker)

if not clients:
    logging.warning("No brokers configured; waiting for brokers to be added.")

try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    pass
