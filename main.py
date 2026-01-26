#updated version
import updateer
import wifi
import network
import utime
import buttons
import machine
import time
import os
from machine import Pin, lightsleep, SPI
import gc
#variables
print("hi")
settings = {}
wlan = network.WLAN(network.STA_IF)
t = utime.localtime()
timer = 0
boot = True
#DISPLAY SETUP
# Setup hardware SPI
from updatelog import get_update_log
log_text = get_update_log()
# then anywhere in your code:

#first boot
def first_boot():
    print("welcome to the Micromate!")
    print(f"the time is {t[3]:02d}:{t[4]:02d} does that sound right?")
    print("we are now going to connect the device to the internet! this is used for updating the machineand for syncing")
    wifi_true = input("would you like to connect to wifi? y/n:")
    if wifi_true.strip().lower() in ("y", "yes"):
        wifi.wifi_manager()
    else:
        print("ok we will skip it for now")
    print("setup complete")


print(f"the time is {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")# prints time
FLAG_FILE = "firstboot.flag"

def write_flag_once():
    if FLAG_FILE not in os.listdir():
        print("first boot")
        with open(FLAG_FILE, "x") as f:
            f.write("1")
        first_boot()
    else:
        pass  
        print("boot finished")

write_flag_once()
#update
updateer.run_updater()
print("finished updating")
gc.collect() #this is this far in the code to stop ram overuse 
from ili9341 import Display, color565
from xglcd_font import XglcdFont 
# Setup hardware SPI
spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))

# Create display object — this *initializes* it already
disp = Display(
    spi,
    dc=Pin(2),
    cs=Pin(15),
    rst=Pin(0),   # Using EN as reset works but a real GPIO-reset pin is better
    width=320,
    height=240
)

# Turn backlight on
Pin(21, Pin.OUT).value(1)

# Clear screen to black
disp.clear(color565(0, 0, 0))
print("now booted up")
# During boot
time.sleep(1)
disp.clear(color565(0, 0, 0))
if log_text:  # only display if not None
    # you might want to truncate it so it fits on screen
    disp.draw_text8x8(100, 120, log_text[:50] + ".", color565(255,255,255), color565(0,0,0))
disp.draw_image("splash.raw") #shows micromate logo

time.sleep(1.5)
disp.clear(color565(0, 0, 0))
max_lines = 5   # number of lines you want on screen
line_height = 12
x, y = 10, 120

lines = log_text.splitlines()
for i, line in enumerate(lines[:max_lines]):
    # truncate each line so it fits horizontally
    disp.draw_text8x8(x, y + i*line_height, line[:30], 0xFFFF)

#APP HANDLING LOGIC

def list_apps():
    try:
        return [d for d in os.listdir("apps") if "main.py" in os.listdir("apps/" + d)]
    except:
        return []

def launch_app(app_name):
    try:
        module = __import__("apps." + app_name + ".main", None, None, ["run"])
        module.run(disp)
    except Exception as e:
        disp.clear(0)
        disp.draw_text8x8(10, 120, "App crash:", 0xFFFF)
        disp.draw_text8x8(10, 140, str(e), 0xFFFF)
        time.sleep(2)
        disp.clear(0)
apps = list_apps()
selected = 0
printed = False
current_time = t
weekday = current_time[6]
days = ["Monday", "Tuesday", "Wedensday", "Thursday", "Friday", "Saturday", "Sunday"]
print("Today is:", days[weekday])

while True:
    current_time = utime.localtime()
    if not apps and not printed:
        disp.draw_text8x8(10, 120, "No apps found", 0xFFFF)
        printed = True
        time.sleep(1)
        continue
        
    if not printed:
        disp.clear(0)
        
    for i, app in enumerate(apps):
        prefix = ">" if i == selected else " "
        disp.draw_text8x8(10, 20 + i * 12, prefix + app, 0xFFFF)
        printed = True
    btn = buttons.button_input()
    disp.draw_text8x8(275, 5, f"{current_time[3]:02d}:{current_time[4]:02d}", 0xFFFF)
    disp.draw_text8x8(0, 5, days[weekday], 0xFFFF)
    if btn == 1:      # up
        selected = (selected - 1) % len(apps)
    elif btn == 2:    # down
        selected = (selected + 1) % len(apps)
    elif btn == 3:    # select
        launch_app(apps[selected])

    time.sleep(0.15)

