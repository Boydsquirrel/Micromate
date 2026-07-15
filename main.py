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
import math
import sys

print("welcome to the micromate")
LAUNCH_FLAG_FILE = "/launch.flag"
CAROUSEL_TARGET  = "CAROUSEL"

def _read_and_clear_launch_target():
    try:
        with open(LAUNCH_FLAG_FILE, "r") as f:
            target = f.read().strip()
        os.remove(LAUNCH_FLAG_FILE)
        return target if target else None
    except:
        return None

def _write_launch_target_and_reset(target):
    try:
        with open(LAUNCH_FLAG_FILE, "w") as f:
            f.write(target)
    except Exception as e:
        print("Failed to write launch flag, staying put:", e)
        return
    machine.reset()

_pending_launch_target = _read_and_clear_launch_target()
_fast_boot = _pending_launch_target is not None and \
             _pending_launch_target != CAROUSEL_TARGET

#CRASH LOGGER 
def log_crash(app_name, error):
    try:
        # prevent log getting too big
        try:
            if "crash.log" in os.listdir() and os.stat("crash.log")[6] > 5000:
                os.remove("crash.log")
        except:
            pass

        with open("crash.log", "a") as f:
            f.write("=== CRASH ===\n")
            f.write("App: " + str(app_name) + "\n")

            try:
                t = utime.localtime()
                f.write("Time: {:02d}:{:02d}:{:02d}\n".format(t[3], t[4], t[5]))
            except:
                pass

            f.write("Error: " + str(error) + "\n")
            f.write("Traceback:\n")
            sys.print_exception(error, f)
            f.write("\n\n")
    except:
        pass


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
disp = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)

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
_pwm_backlight = None
_backlight_pin = None

try:
    _pwm = PWM(Pin(21))
    _pwm.freq(1000)
    _pwm.duty_u16(int((settings.get("brightness", 100) / 100) * 65535))
    _pwm_backlight = _pwm
except:
    try:
        _backlight_pin = Pin(21, Pin.OUT)
        _backlight_pin.value(1 if settings.get("brightness", 100) > 0 else 0)
    except:
        _backlight_pin = None

def apply_brightness(brightness):
    try:
        if _pwm_backlight:
            _pwm_backlight.duty_u16(int((max(0, min(100, brightness)) / 100) * 65535))
        elif _backlight_pin:
            _backlight_pin.value(1 if brightness > 0 else 0)
    except:
        pass

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

#WIFI ICON
_last_wifi_state = None

def draw_wifi_status(connected):
    global _last_wifi_state
    if connected == _last_wifi_state:
        return
    _last_wifi_state = connected
    x, y = 300, 5
    try:
        disp.fill_rectangle(x, y, 15, 15, BG)
        color = 0x07E0 if connected else 0xF800
        disp.draw_line(x,      y + 15, x + 4,  y + 11, color)
        disp.draw_line(x + 5,   y + 15, x + 9,  y + 9,  color)
        disp.draw_line(x + 10,  y + 15, x + 14, y + 5,  color)
    except:
        pass

#STATUS BAR
STATUS_H = 28
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_last_drawn_minute = -1

def draw_status_bar():
    global _last_drawn_minute, _last_wifi_state
    _last_drawn_minute = -1
    _last_wifi_state = None
    try:
        disp.fill_rectangle(0, 0, 320, STATUS_H, BG)
    except:
        pass
    update_clock()
    draw_wifi_status(network.WLAN(network.STA_IF).isconnected())

def update_clock():
    global _last_drawn_minute
    try:
        t = utime.localtime()
        if t[4] == _last_drawn_minute:
            return
        _last_drawn_minute = t[4]
        day_str  = days[t[6]] if 0 <= t[6] < 7 else ""
        time_str = "{:02d}:{:02d}".format(t[3], t[4])
        disp.fill_rectangle(5,   0, 195, STATUS_H, BG)
        disp.fill_rectangle(245, 0,  55, STATUS_H, BG)
        disp.draw_text8x8(5,   8, day_str,  TEXT_COLOR)
        disp.draw_text8x8(250,  8, time_str, TEXT_COLOR)
    except:
        pass

draw_status_bar()

#APP SYSTEM
ICON_SIZE  = 32
apps       = []
selected   = 0
icon_cache = {}

from sprite import Sprite

class App:
    def __init__(self, name, icon_path):
        self.name      = name
        self.icon_path = icon_path
        self.icon      = self._load_icon(icon_path)

    def _load_icon(self, path):
        if not path:
            return None
        if path in icon_cache:
            return icon_cache[path]
        try:
            sprite = Sprite(path)  # path points at icon.spr
            icon_cache[path] = sprite
            return sprite
        except Exception as e:
            print("Failed to load icon", path, ":", e)
            return None

def list_apps():
    result = []
    try:
        for d in os.listdir("apps"):
            path = "apps/" + d
            try:
                entries = os.listdir(path)
            except:
                continue
            if "main.py" not in entries:
                continue
            icon = path + "/icon.spr" if "icon.spr" in entries else None
            result.append(App(d, icon))
    except:
        pass
    return result

#HOME & LAUNCH
def render_home():
    # home_carousel.py owns its own apps/selected state internally via
    # the Carousel class - this just re-enters the carousel UI loop.
    _run_home_ui()

def _execute_app(app_name):
    """Actually run an app's run(disp) - no flag writing, no reset.
    Used ONLY right after a fast-boot reset, when we already know (from
    the launch flag we just read) that this app is what should run.
    Never call this directly from the carousel - that goes through
    launch_app() instead, which resets first so the app gets a clean
    heap with the carousel's memory fully released."""
    try:
        try:
            disp.fill_rectangle(0, 0, 320, 240, BG)
        except:
            pass

        gc.collect()

        module_name = "apps." + app_name + ".main"

        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
        except:
            pass

        module = __import__(module_name, None, None, ["run"])

        if hasattr(module, "run"):
            module.run(disp)
        else:
            raise Exception("no run() in app")

    except Exception as e:
        print("App crashed:", app_name)
        sys.print_exception(e)

        log_crash(app_name, e)

        try:
            disp.fill_rectangle(0, STATUS_H + 2, 320, 240 - (STATUS_H + 2), BG)
            disp.draw_text8x8(10, 100, "App crashed", TEXT_COLOR)
            disp.draw_text8x8(10, 120, app_name[:20], 0xF800)
            disp.draw_text8x8(10, 140, str(e)[:38], TEXT_COLOR)
        except:
            pass

        time.sleep(2)


def launch_app(app):
    """Called by the carousel (or any future home UI) when the user
    wants to launch an app. Does NOT run the app directly - the
    carousel + all its Sprites/Scene/icon cache are still fully loaded
    in RAM at this point, and apps need real headroom. Instead, this
    writes the target to the launch flag and resets - the NEXT boot
    (see top of this file) reads that flag before anything else runs
    and calls _execute_app() with a genuinely clean heap."""
    _write_launch_target_and_reset(app.name)
    # machine.reset() does not return - if we ever get here, the reset
    # itself failed (see _write_launch_target_and_reset's fallback).
    print("launch_app: reset failed, app not launched:", app.name)

def _run_home_ui():
    import home_carousel

    gc.collect()
    print("Free heap right before Carousel init:", gc.mem_free())

    ctx = {
        "disp":             disp,
        "settings":         settings,
        "apply_brightness": apply_brightness,
        "list_apps":        list_apps,
        "launch_app":       launch_app,
        "draw_status_bar":  draw_status_bar,
        "update_clock":     update_clock,
        "draw_wifi_status": draw_wifi_status,
        "STATUS_H":         STATUS_H,
        "BG":               BG,
        "TEXT_COLOR":       TEXT_COLOR,
        "ACCENT":           ACCENT,
        "DIM":              DIM,
    }

    home_carousel.run(ctx)

if _fast_boot:
    _execute_app(_pending_launch_target)
    _write_launch_target_and_reset(CAROUSEL_TARGET)
    print("Fast-boot return-to-carousel reset failed - falling back to "
          "normal carousel loop without resetting.")
    while True:
        _run_home_ui()
else:
    # Normal full boot (cold boot, or explicitly returning to carousel).
    while True:
        _run_home_ui()
