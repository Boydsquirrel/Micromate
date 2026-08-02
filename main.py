import sys
sys.path.append("/system/modules")

import updateer
import wifi
import network
import utime
import buttons
import machine
import time
import os
import ntptime
from machine import Pin, SPI, PWM
import gc
import json

import crashlog
import bootflags
import battery
import backlight

print("welcome to the micromate")

_pending_launch_target = bootflags.read_and_clear_launch_target()
_fast_boot = _pending_launch_target is not None and \
             _pending_launch_target != bootflags.CAROUSEL_TARGET


#FIRST BOOT
FLAG_FILE = "firstboot.flag"

def first_boot():
    try:
        disp.clear(BG)
        disp.fill_rectangle(0, 0, 320, 20, ACCENT)
        disp.draw_text8x8(8, 6, "Welcome to Micromate!", BG)
        disp.draw_text8x8(10, 50, "Connect to Wi-Fi?", TEXT_COLOR)
        disp.draw_text8x8(10, 80, "Yes", 0x07E0)
        disp.draw_text8x8(10, 100, "Skip", 0xF800)
    except:
        pass

    from machine import Pin
    _y = Pin(18, Pin.IN, Pin.PULL_UP)
    _n = Pin(4, Pin.IN, Pin.PULL_UP)
    _ly, _ln = 1, 1
    choice = None
    deadline = time.time() + 30

    while time.time() < deadline:
        vy, vn = _y.value(), _n.value()
        if vy == 0 and _ly == 1:
            choice = "yes"
            break
        if vn == 0 and _ln == 1:
            choice = "no"
            break
        _ly, _ln = vy, vn
        time.sleep(0.05)

    if choice == "yes":
        try:
            wifi.wifi_manager(disp)
            time.sleep(2)
            ntptime.settime()
        except:
            pass


def write_flag_once():
    try:
        if FLAG_FILE not in os.listdir():
            with open(FLAG_FILE, "x") as f:
                f.write("1")
            first_boot()
    except:
        pass


#WIFI TIME
if not _fast_boot:
    try:
        wifi.wifi_manager()
        try:
            ntptime.settime()
        except:
            pass
    except:
        pass

gc.collect()

#DISPLAY
from ili9341 import Display
spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240, rotation=180, bgr=False)

BG         = 0x0000
TEXT_COLOR = 0xFFFF
ACCENT     = 0x07FF
DIM        = 0x8410

disp.clear(BG)

#SETTINGS
def load_system_settings():
    try:
        with open("/system/settings.json", "r") as f:
            return json.load(f)
    except:
        return {"brightness": 100}

settings      = load_system_settings()
last_activity = time.time()
sleeping      = False

#BACKLIGHT
backlight.init(settings.get("brightness", 100))
apply_brightness = backlight.apply_brightness

if not _fast_boot:
    write_flag_once()

#UPDATE
gc.collect()
gc.collect()
print("Free mem before update:", gc.mem_free())

if not _fast_boot:
    # Reconnect if wifi dropped since boot
    try:
        _wlan = network.WLAN(network.STA_IF)
        if not _wlan.isconnected():
            print("WiFi dropped, trying auto-reconnect...")
            _wlan.active(True)

            _deadline = time.time() + 5
            while time.time() < _deadline:
                if _wlan.isconnected():
                    print("Auto-reconnected:", _wlan.ifconfig()[0])
                    break
                time.sleep(0.25)

            if not _wlan.isconnected():
                print("Trying saved networks...")
                wifi.try_auto_connect()

            if _wlan.isconnected():
                try:
                    ntptime.settime()
                except:
                    pass
    except Exception as e:
        print("Reconnect error:", e)

    try:
        updateer.run_updater(disp)
    except Exception as e:
        print("Updater error:")
        sys.print_exception(e)

gc.collect()

# Deferred on purpose: not needed until after the update check above,
# so the update fetch gets first crack at free/unfragmented heap.
import statusbar
import appregistry
import launcher

#STATUS BAR
statusbar.init(disp, BG, TEXT_COLOR)
statusbar.draw_status_bar()

#HOME & LAUNCH
def render_home():
    # home_carousel.py owns its own apps/selected state internally via
    # the Carousel class - this just re-enters the carousel UI loop.
    _run_home_ui()

def launch_app(app):
    launcher.launch_app(app, disp, statusbar.draw_status_bar)

def _run_home_ui():
    import home_carousel

    gc.collect()
    print("Free heap right before Carousel init:", gc.mem_free())

    ctx = {
        "disp":             disp,
        "settings":         settings,
        "apply_brightness": apply_brightness,
        "list_apps":        appregistry.list_apps,
        "launch_app":       launch_app,
        "draw_status_bar":  statusbar.draw_status_bar,
        "update_clock":     statusbar.update_clock,
        "draw_wifi_status": statusbar.draw_wifi_status,
        "STATUS_H":         statusbar.STATUS_H,
        "BG":               BG,
        "TEXT_COLOR":       TEXT_COLOR,
        "ACCENT":           ACCENT,
        "DIM":              DIM,
    }

    home_carousel.run(ctx)

if _fast_boot:
    launcher.execute_app(_pending_launch_target, disp, BG, TEXT_COLOR)
    bootflags.write_launch_target_and_reset(bootflags.CAROUSEL_TARGET)
    print("Fast-boot return-to-carousel reset failed - falling back to "
          "normal carousel loop without resetting.")
    while True:
        _run_home_ui()
else:
    # Normal full boot (cold boot, or explicitly returning to carousel).
    while True:
        _run_home_ui()

