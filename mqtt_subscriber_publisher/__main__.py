import configparser,os
import paho.mqtt.client as mqtt
import time
import json
import random
from datetime import datetime,date,timedelta
import pprint
import copy
pp = pprint.PrettyPrinter(indent=4)

cur_date=datetime.today()+timedelta(weeks=-1)

script_dir=os.path.dirname(os.path.realpath(__file__))

config=configparser.ConfigParser()
config.read(script_dir+'/config.ini')

authenticate=config["MQTT"]["authenitcation"]=="True"
username = config["MQTT"]["UserName"]
password= config["MQTT"]["Password"]
address=config["MQTT"]["Address"]
port=int(config["MQTT"]["Port"])
data=""
if(config["Data"]["Usefile"]=="True"):
    with open(script_dir+"/"+config["Data"]["File"]) as f:
        data=f.read()
else:
    data=config["Data"]["Data"]
topic="/cs/v1/data/01"
if("Topic" in config["Data"]):
    topic=config["Data"]["Topic"]

connected=False

def on_connect(client, userdata, flags, rc):
    if rc==0:
        connected=True
        print("Connected OK Returned code=",rc)
    else:
        print("Bad connection Returned code=",rc)

client=mqtt.Client("gideon2")
client.on_connect=on_connect

if(authenticate):
    client.username_pw_set(username=username,password=password)

payload=json.loads(data)

client.connect(address,port=port)
client.loop_start()
t=list(payload["properties"]["observations"].keys())[0]
timestr=cur_date.strftime("%Y-%m-%dT%H:%M:%SZ")
payload["properties"]["observations"][timestr]=payload["properties"]["observations"][t]
del payload["properties"]["observations"][t]
t=timestr
cur_date=cur_date+timedelta(hours=1)
while cur_date<datetime.now()+timedelta(days=-1):
    timestr=cur_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["properties"]["observations"][timestr]=copy.deepcopy(payload["properties"]["observations"][t])
    for i in range(len(payload["properties"]["observations"][timestr])):
        if type(payload["properties"]["observations"][timestr][i])!=str:
            if payload["properties"]["observations"][timestr][i]==0:
                payload["properties"]["observations"][timestr][i]=1
            payload["properties"]["observations"][timestr][i]=payload["properties"]["observations"][timestr][i]*random.uniform(0.5,1.6)
    cur_date=cur_date+timedelta(hours=3)
pp.pprint(payload)
ret=client.publish(topic,json.dumps(payload))
print(f"published message, result code={ret[0]}")
time.sleep(1)
client.loop_stop()