import configparser,os

script_dir=os.path.dirname(os.path.realpath(__file__))

config=configparser.ConfigParser()
config.read(script_dir+'/config.ini')

class mqtt:
    authentication=config["MQTT"]["Authentication"]=="True"
    username=config["MQTT"]["UserName"]
    password=config["MQTT"]["Password"]
    address=config["MQTT"]["Address"]
    port=int(config["MQTT"]["Port"])

_timescale_section = "Timescale" if config.has_section("Timescale") else "Timestream"

class timescale:
    database=config[_timescale_section]["DataBase"]
    schema=config[_timescale_section].get("Schema", "public")
    username=config[_timescale_section].get("UserName", config.get("MySQL", "UserName", fallback=""))
    password=config[_timescale_section].get("Password", config.get("MySQL", "Password", fallback=""))
    host=config[_timescale_section].get("Host", "localhost")
    port=int(config[_timescale_section].get("Port", "5432"))
    admin_database=config[_timescale_section].get("AdminDatabase", "postgres")
    use_current_time=(config[_timescale_section].get("UseCurrentTimeAsTimestamp", "False")=="True")

class mysql:
    username=config.get("MySQL", "UserName", fallback=config.get("MySQL", "Username", fallback=""))
    password=config.get("MySQL", "Password", fallback="")
    address=config.get("MySQL", "Host", fallback=config.get("MySQL", "Address", fallback="localhost"))
    port=int(config.get("MySQL", "Port", fallback="5432"))
    database=config.get("MySQL", "DataBase", fallback="")