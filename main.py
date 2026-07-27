import updateer
import wifi
import network
import utime
import buttons
import machine
import time
import os
import ntptime
from machine import Pin, SPI, PWM, ADC
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
disp = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240, rotation=180)

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

#BATTERY
try:
    _batt_adc = ADC(Pin(35))
    _batt_adc.atten(ADC.ATTN_11DB)
except:
    _batt_adc = None

def read_battery_voltage(samples=20, delay_ms=2):
    """Quick averaged read - intentionally NOT a full 1-second blocking
    loop like a standalone script could get away with, since this runs
    inside the UI loop and can't freeze the display/input for a second
    every time it's called. samples*delay_ms stays small (~40ms)."""
    if not _batt_adc:
        return None
    try:
        total = 0
        for _ in range(samples):
            total += _batt_adc.read()
            time.sleep_ms(delay_ms)
        average_raw = total / samples
        adc_voltage = (average_raw / 4095) * 3.3
        return adc_voltage * 2  # 1M + 1M divider
    except:
        return None

def battery_percent():
    """Rough linear map of single-cell LiPo voltage to percentage.
    Not accurate near the bottom of the curve (real LiPo discharge
    isn't linear), but good enough for a glance in the status bar."""
    v = read_battery_voltage()
    if v is None:
        return None
    if v >= 4.2:
        return 100
    if v <= 3.3:
        return 0
    return round((v - 3.3) / (4.2 - 3.3) * 100)

#TIMEZONE / DST
# ntptime.settime() sets the RTC to UTC. If the weather app has a
# manual location saved (see apps/settings), we use that location's
# country to pick the right standard UTC offset + DST rule. If only
# auto-detect (IP geolocation) is in use, there's no reliable country
# to key off of, so we fall back to the old hardcoded EU (CET/CEST)
# assumption - same behaviour as before, including the summer drift.
_LOCATION_FILE = "/apps/weather/location.json"

UTC_OFFSET_STANDARD = 1  # CET fallback, hours ahead of UTC

def _load_saved_location():
    try:
        with open(_LOCATION_FILE, "r") as f:
            return json.load(f)
    except:
        return None

def _last_sunday(year, month):
    days_in_month = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = days_in_month[month - 1]
    while True:
        try:
            wd = utime.localtime(utime.mktime((year, month, day, 0, 0, 0, 0, 0)))[6]
        except:
            return day
        if wd == 6:  # Sunday (weekday 0=Monday .. 6=Sunday)
            return day
        day -= 1

def _nth_weekday_of_month(year, month, weekday, n):
    count = 0
    for day in range(1, 32):
        try:
            wd = utime.localtime(utime.mktime((year, month, day, 0, 0, 0, 0, 0)))[6]
        except:
            return None
        if wd == weekday:
            count += 1
            if count == n:
                return day
    return None

def _is_eu_dst(utc_t):
    year, month, day, hour = utc_t[0], utc_t[1], utc_t[2], utc_t[3]
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    if month == 3:
        dst_start_day = _last_sunday(year, 3)
        return (day > dst_start_day) or (day == dst_start_day and hour >= 1)
    if month == 10:
        dst_end_day = _last_sunday(year, 10)
        return (day < dst_end_day) or (day == dst_end_day and hour < 1)
    return False

def _is_us_dst(utc_t):
    # Approximate: 2nd Sunday March 07:00 UTC (2am EST) to
    # 1st Sunday November 06:00 UTC (2am EDT). Exact for US Eastern;
    # off by up to an hour on transition day itself for other US zones.
    year, month, day, hour = utc_t[0], utc_t[1], utc_t[2], utc_t[3]
    if month < 3 or month > 11:
        return False
    if 3 < month < 11:
        return True
    if month == 3:
        start_day = _nth_weekday_of_month(year, 3, 6, 2)
        return (day > start_day) or (day == start_day and hour >= 7)
    if month == 11:
        end_day = _nth_weekday_of_month(year, 11, 6, 1)
        return (day < end_day) or (day == end_day and hour < 6)
    return False

# Country code -> (standard UTC offset, dst rule). Not exhaustive, and
# multi-timezone countries (US, CA, RU, AU, BR, ...) are approximated
# with one representative offset. Add more entries here as needed.
_TZ_TABLE = {
    "NL": (1, "eu"), "DE": (1, "eu"), "FR": (1, "eu"), "BE": (1, "eu"),
    "ES": (1, "eu"), "IT": (1, "eu"), "AT": (1, "eu"), "CH": (1, "eu"),
    "PL": (1, "eu"), "SE": (1, "eu"), "DK": (1, "eu"), "NO": (1, "eu"),
    "PT": (0, "eu"), "IE": (0, "eu"), "GB": (0, "eu"),
    "FI": (2, "eu"), "GR": (2, "eu"), "RO": (2, "eu"), "BG": (2, "eu"),
    "US": (-5, "us"), "CA": (-5, "us"),
    "JP": (9, "none"), "CN": (8, "none"), "IN": (5.5, "none"),
    "AU": (10, "none"),
}

def _dst_offset_for_country(cc, utc_t):
    """Returns (standard_offset, dst_add) for a known country code,
    or None if the country isn't in the table (caller should fall back)."""
    entry = _TZ_TABLE.get(cc)
    if not entry:
        return None
    std_offset, rule = entry
    if rule == "eu":
        return std_offset, (1 if _is_eu_dst(utc_t) else 0)
    if rule == "us":
        return std_offset, (1 if _is_us_dst(utc_t) else 0)
    return std_offset, 0

def get_local_time():
    try:
        utc_t = utime.localtime()

        loc = _load_saved_location()
        if loc and loc.get("manual") and loc.get("cc"):
            result = _dst_offset_for_country(loc["cc"], utc_t)
            if result is not None:
                std_offset, dst_add = result
                offset_hours = std_offset + dst_add
                return utime.localtime(utime.mktime(utc_t) + int(offset_hours * 3600))
            # Manual location saved, but country not in our table -
            # fall through to the EU fallback below rather than
            # guessing further.

        # No manual location (auto-detect) or unknown country: fall
        # back to the old hardcoded EU assumption.
        offset_hours = UTC_OFFSET_STANDARD + (1 if _is_eu_dst(utc_t) else 0)
        return utime.localtime(utime.mktime(utc_t) + offset_hours * 3600)
    except:
        return utime.localtime()

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
        t = get_local_time()
        if t[4] == _last_drawn_minute:
            return
        _last_drawn_minute = t[4]
        day_str  = days[t[6]] if 0 <= t[6] < 7 else ""
        time_str = "{:02d}:{:02d}".format(t[3], t[4])
        disp.fill_rectangle(5,   0, 195, STATUS_H, BG)
        disp.fill_rectangle(205, 0,  38, STATUS_H, BG)   # battery area
        disp.fill_rectangle(245, 0,  55, STATUS_H, BG)
        disp.draw_text8x8(5,   8, day_str,  TEXT_COLOR)

        pct = battery_percent()
        if pct is not None:
            batt_str = "{:d}%".format(pct)
            batt_color = 0x07E0 if pct > 20 else 0xF800  # green, red if low
            disp.draw_text8x8(207, 8, batt_str, batt_color)

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

def app_wants_reset(app_name):
#for apps that need the extra ram from a reset
    try:
        return "reset.flag" in os.listdir("apps/" + app_name)
    except:
        return False


def launch_app(app):
    if app_wants_reset(app.name):
        _write_launch_target_and_reset(app.name)
        # machine.reset() does not return - if we ever get here, the
        # reset itself failed (see _write_launch_target_and_reset's
        # fallback).
        print("launch_app: reset failed, app not launched:", app.name)
    else:
        _execute_app(app.name)
        draw_status_bar()

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
