import subprocess
from time import sleep

try:
    priv = "sudo"
    action = "mosquitto_passwd"
    b = "-b"
    path = "/etc/mosquitto"
    usr = "aaauser"
    pwd = "aaapass"
    print("Stopping mosquitto...")
    subprocess.call(["service", "mosquitto", "stop"])
    print("Stopped.")
    sleep(1)
    print("Adding user...")
    subprocess.call([priv, action, b, path, usr, pwd])
    print("User Added.")
    sleep(1)
    print("Starting mosquitto...")
    subprocess.call(["service", "mosquitto", "start"])
    print("Started.")
except Exception as e:
    print("exception:"+str(e))