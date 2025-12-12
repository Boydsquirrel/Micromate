import updateer
import wifi
import network
import utime
import buttons
import machine
import time
import os
from machine import Pin, lightsleep
updateer.run_updater()
print("finished updating")

#variables
settings = {}
wlan = network.WLAN(network.STA_IF)
t = utime.localtime()

with open("settings.txt", "r") as f:
    for line in f:
        if "=" in line:
            key, value = line.strip().split("=", 1)
            settings[key] = value

theme_mode = settings["solid_theme"]
brightness = settings["brightness"]
print(f"the time is {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")# prints time
FLAG_FILE = "firstboot.flag"

def write_flag_once():
    if FLAG_FILE not in os.listdir():
        print("first boot")
        with open(FLAG_FILE, "x") as f:
            f.write("1") 
    else:
        pass  
        print("boot finished")

write_flag_once()

timer = 0
boot = True
while boot:
    if buttons.button_input() != 0: #autosleep
        print("Button pressed!")
    else:
        timer += 1
        if timer == 240:
            print("timer hit 240")
            print("Sleeping for 0.5 sec...")
            lightsleep(500)  # ms
            if buttons.button_input() != 0:
                timer = 0
        else:
            time.sleep(1)
   

   
    

