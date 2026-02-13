import updateer
import wifi
import network
import utime
import buttons
import machine
import time
import os
import ntptime
from machine import Pin, SPI
import gc

print("hi")
settings = {}
boot = True

FLAG_FILE = "firstboot.flag"

# ====== FIRST BOOT ======
def first_boot():
    print("Welcome to the Micromate!")
    wifi_true = input("Connect to Wi-Fi? y/n: ").strip().lower()
    if wifi_true in ("y", "yes"):
        wifi.wifi_manager()
        time.sleep(2)
        try:
            ntptime.settime()
        except:
            pass

def write_flag_once():
    if FLAG_FILE not in os.listdir():
        with open(FLAG_FILE, "x") as f:
            f.write("1")
        first_boot()

write_flag_once()

# ====== WIFI & TIME ======
wifi.wifi_manager()
time.sleep(2)
try:
    ntptime.settime()
except:
    pass

# ====== UPDATE ======
updateer.run_updater()
gc.collect()

# ====== DISPLAY ======
from ili9341 import Display, color565
from xglcd_font import XglcdFont

spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)
disp.clear(0x0000)

import json
from machine import PWM, Pin
import json

def load_system_settings():
    try:
        with open("/system/settings.json", "r") as f:
            return json.load(f)
    except:
        return {"brightness": 100, "sleep": 0}

settings = load_system_settings()

sleep_time = settings.get("sleep", 0)
last_activity = time.time()
sleeping = False
boot_brightness = settings.get("brightness", 100)

# try to setup PWM backlight; fallback to digital on/off if PWM not supported
_pwm_backlight = None
_backlight_pin = None
try:
    _pwm = PWM(Pin(21))
    _pwm.freq(1000)
    duty = int((boot_brightness / 100) * 65535)
    _pwm.duty_u16(duty)
    _pwm_backlight = _pwm
except Exception:
    try:
        _backlight_pin = Pin(21, Pin.OUT)
        _backlight_pin.value(1 if boot_brightness > 0 else 0)
    except Exception:
        _backlight_pin = None

def apply_brightness(brightness):
    """
    brightness: 0-100
    if PWM available use duty_u16, else digital on/off
    """
    global _pwm_backlight, _backlight_pin
    try:
        if _pwm_backlight:
            duty = int((max(0, min(100, brightness)) / 100) * 65535)
            _pwm_backlight.duty_u16(duty)
        elif _backlight_pin:
            _backlight_pin.value(1 if brightness > 0 else 0)
    except Exception:
        pass

# ====== WIFI ICON ======
def draw_wifi_status(connected):
    color = 0x07E0 if connected else 0xF800
    x, y = 300, 220
    disp.fill_rectangle(x, y, 15, 15, 0x0000)
    disp.draw_line(x, y+15, x+4, y+11, color)
    disp.draw_line(x+5, y+15, x+9, y+9, color)
    disp.draw_line(x+10, y+15, x+14, y+5, color)

SCREEN_W, SCREEN_H = 320, 240
COLS, ROWS = 3, 3
CELL_W, CELL_H = SCREEN_W // COLS, SCREEN_H // ROWS
days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

apps = []
selected = 0


    

# ====== HOME RENDER ======
def render_home():
    global apps, selected
    disp.clear(0x0000)
    apps = list_apps()

    if not apps:
        disp.draw_text8x8(90, 120, "No apps found", 0xFFFF)
        return

    selected = min(selected, len(apps) - 1)
    draw_app_grid_initial(apps)
    highlight_app(selected, apps)
    gc.collect()

# ====== APP LAUNCHER (CRASH SAFE) ======
def launch_app(app_name):
    try:
        disp.clear(0x0000)
        gc.collect()
        # import the module safely
        module = __import__("apps." + app_name + ".main", None, None, ["run"])
        # call run and pass disp (your apps expect this)
        module.run(disp)
    except Exception as e:
        disp.clear(0x0000)
        try:
            disp.draw_text8x8(10, 110, "App crashed", 0xFFFF)
            disp.draw_text8x8(10, 130, str(e), 0xFFFF)
        except Exception:
            pass
        time.sleep(2)
    finally:
        render_home()
# ===== FAST APP SYSTEM =====

ICON_SIZE = 32
ICON_BYTES = ICON_SIZE * ICON_SIZE * 2

SCREEN_W, SCREEN_H = 320, 240
COLS, ROWS = 3, 3
CELL_W, CELL_H = SCREEN_W // COLS, SCREEN_H // ROWS

apps = []
selected = 0
icon_cache = {}

# ===== APP CLASS =====
class App:
    def __init__(self, name, icon_path):
        self.name = name
        self.icon_path = icon_path
        self.icon = self.load_icon(icon_path)

    def load_icon(self, path):
        if not path:
            return None

        if path in icon_cache:
            return icon_cache[path]

        try:
            with open(path, "rb") as f:
                data = f.read()

                if len(data) != ICON_BYTES:
                    return None

                icon_cache[path] = data
                return data

        except:
            return None


# ===== LIST APPS =====
def list_apps():
    result = []

    try:
        dirs = os.listdir("apps")

        for d in dirs:

            path = "apps/" + d

            try:
                entries = os.listdir(path)
            except:
                continue

            if "main.py" not in entries:
                continue

            icon = None
            if "icon.raw" in entries:
                icon = path + "/icon.raw"

            result.append(App(d, icon))

    except:
        pass

    return result


# ===== FAST ICON DRAW =====
def draw_icon(icon, x, y):

    if not icon:
        return

    try:
        # fastest possible draw method
        disp.block(x, y, x + ICON_SIZE - 1, y + ICON_SIZE - 1, icon)

    except:
        pass


# ===== DRAW ONE CELL =====
def draw_cell(index, highlight=False):

    if index >= len(apps):
        return

    app = apps[index]

    r = index // COLS
    c = index % COLS

    cell_x = c * CELL_W
    cell_y = r * CELL_H

    bg = 0xFFFF if highlight else 0x0000
    fg = 0x0000 if highlight else 0xFFFF

    disp.fill_rectangle(cell_x, cell_y, CELL_W, CELL_H, bg)

    # draw icon
    if app.icon:
        ix = cell_x + (CELL_W - ICON_SIZE) // 2
        iy = cell_y + 8

        draw_icon(app.icon, ix, iy)

        text_y = iy + ICON_SIZE + 2

    else:
        text_y = cell_y + CELL_H // 2


    text_x = cell_x + (CELL_W - len(app.name) * 8) // 2

    disp.draw_text8x8(text_x, text_y, app.name, fg, bg)


# ===== DRAW GRID ONCE =====
def draw_grid():

    disp.clear(0x0000)

    for i in range(len(apps)):
        draw_cell(i, highlight=False)

    draw_cell(selected, highlight=True)


# ===== UPDATE SELECTION ONLY =====
def update_selection(old, new):

    if old == new:
        return

    draw_cell(old, highlight=False)

    draw_cell(new, highlight=True)


# ===== HOME RENDER =====
def render_home():

    global apps, selected

    gc.collect()

    apps = list_apps()

    if not apps:
        disp.clear(0)
        disp.draw_text8x8(90, 120, "No apps found", 0xFFFF)
        return

    if selected >= len(apps):
        selected = 0

    draw_grid()

    gc.collect()


# ===== LAUNCH APP =====
def launch_app(app):

    try:

        disp.clear(0)

        gc.collect()

        module = __import__(
            "apps." + app.name + ".main",
            None,
            None,
            ["run"]
        )

        module.run(disp)

    except Exception as e:

        disp.clear(0)

        disp.draw_text8x8(10, 110, "App crashed", 0xFFFF)

        try:
            disp.draw_text8x8(10, 130, str(e), 0xFFFF)
        except:
            pass

        time.sleep(2)

    finally:

        render_home()

# ====== START ======
render_home()

# ====== MAIN LOOP ======
while True:
    wlan = network.WLAN(network.STA_IF)
    draw_wifi_status(wlan.isconnected())

    t = utime.localtime()
    try:
        disp.draw_text8x8(275, 5, f"{t[3]:02d}:{t[4]:02d}", 0xFFFF)
        disp.draw_text8x8(0, 5, days[t[6]], 0xFFFF)
    except Exception:
        pass

    btn = buttons.button_input()
    prev = selected

    if apps:
        if btn == 1:
            selected = (selected - 1) % len(apps)
        elif btn == 2:
            selected = (selected + 1) % len(apps)
        elif btn == 3:
            launch_app(apps[selected])
        elif btn == 4:
            render_home()  # SOFT HOME BUTTON

    if btn:
        last_activity = time.time()

    if sleeping:
        # Wake up
        apply_brightness(settings.get("brightness", 100))
        sleeping = False

    if prev != selected and apps:
        update_selection(prev, selected)

