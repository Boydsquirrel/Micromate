# micromate_home_final_fixed.py
import updateer
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

print("hi")

# ===== FIRST BOOT =====
FLAG_FILE = "firstboot.flag"
def first_boot():
    print("Welcome to the Micromate!")
    try:
        wifi_true = input("Connect to Wi-Fi? y/n: ").strip().lower()
    except:
        wifi_true = "n"
    if wifi_true in ("y", "yes"):
        try:
            wifi.wifi_manager()
            time.sleep(2)
            ntptime.settime()
        except: pass

def write_flag_once():
    try:
        if FLAG_FILE not in os.listdir():
            with open(FLAG_FILE, "x") as f:
                f.write("1")
            first_boot()
    except: pass

write_flag_once()


gc.collect()

# ===== DISPLAY =====
from ili9341 import Display
spi  = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)

BG         = 0x0000
TEXT_COLOR = 0xFFFF
ACCENT     = 0x07FF
DIM        = 0x8410

disp.clear(BG)

# ===== SETTINGS =====
def load_system_settings():
    try:
        with open("/system/settings.json", "r") as f:
            return json.load(f)
    except: return {"brightness": 100, "sleep": 0}

settings      = load_system_settings()
sleep_time    = settings.get("sleep", 0)
last_activity = time.time()
sleeping      = False

# ===== BACKLIGHT =====
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
    except: _backlight_pin = None

def apply_brightness(brightness):
    try:
        if _pwm_backlight:
            _pwm_backlight.duty_u16(int((max(0, min(100, brightness)) / 100) * 65535))
        elif _backlight_pin:
            _backlight_pin.value(1 if brightness > 0 else 0)
    except: pass

# ===== UPDATE =====
gc.collect()
gc.collect()
print("Free mem before update:", gc.mem_free())
try:
    updateer.run_updater(disp)
except Exception as e:
    print("Updater error:", e)
gc.collect()

# ===== WIFI ICON =====
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
        disp.draw_line(x + 5,  y + 15, x + 9,  y + 9,  color)
        disp.draw_line(x + 10, y + 15, x + 14, y + 5,  color)
    except: pass

# ===== STATUS BAR =====
STATUS_H = 28
days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
_last_drawn_minute = -1

def draw_status_bar():
    global _last_drawn_minute, _last_wifi_state
    _last_drawn_minute = -1
    _last_wifi_state   = None
    try:
        disp.fill_rectangle(0, 0, 320, STATUS_H, BG)
    except: pass
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
        disp.draw_text8x8(250, 8, time_str, TEXT_COLOR)
    except: pass

draw_status_bar()

# ===== APP SYSTEM =====
ICON_SIZE  = 32
ICON_BYTES = ICON_SIZE * ICON_SIZE * 2
apps       = []
selected   = 0
icon_cache = {}

class App:
    def __init__(self, name, icon_path):
        self.name      = name
        self.icon_path = icon_path
        self.icon      = self._load_icon(icon_path)

    def _load_icon(self, path):
        if not path: return None
        if path in icon_cache: return icon_cache[path]
        try:
            with open(path, "rb") as f:
                data = f.read()
                if len(data) == ICON_BYTES:
                    icon_cache[path] = data
                    return data
        except: pass
        return None

def list_apps():
    result = []
    try:
        for d in os.listdir("apps"):
            path = "apps/" + d
            try:   entries = os.listdir(path)
            except: continue
            if "main.py" not in entries: continue
            icon = path + "/icon.raw" if "icon.raw" in entries else None
            result.append(App(d, icon))
    except: pass
    return result

def draw_icon(icon, x, y):
    try: disp.block(x, y, x + ICON_SIZE - 1, y + ICON_SIZE - 1, icon)
    except: pass

# ===== LAYOUT CONSTANTS =====
CENTER_X = 160
CENTER_Y = 120
SPACING  = 100

DRAW_Y = STATUS_H + 2
DRAW_H = 240 - DRAW_Y

ICON_Y     = CENTER_Y - 16
BORDER_TOP = CENTER_Y - 40
BORDER_BOT = CENTER_Y + 40

ICON_WIPE_Y = ICON_Y - 1
ICON_WIPE_H = 4

TEXT_Y = CENTER_Y + 44
TEXT_H = 20

ANIM_STRIP_Y = BORDER_TOP - 2
ANIM_STRIP_H = (ICON_Y + ICON_SIZE + ICON_WIPE_H) - ANIM_STRIP_Y

# ===== CAROUSEL =====
def draw_frame(offset, full_clear=False):
    if full_clear:
        try: disp.fill_rectangle(0, DRAW_Y, 320, DRAW_H, BG)
        except: pass
    else:
        try: disp.fill_rectangle(0, ANIM_STRIP_Y, 320, ANIM_STRIP_H, BG)
        except: pass
        try: disp.fill_rectangle(0, TEXT_Y, 320, TEXT_H, BG)
        except: pass

    for i in range(-2, 3):
        if not apps: break
        idx = (selected + i) % len(apps)
        app = apps[idx]
        x   = CENTER_X + i * SPACING + offset
        if x < -64 or x > 384:
            continue
        if app.icon:
            try: draw_icon(app.icon, x - 16, ICON_Y)
            except: pass

    try: disp.fill_rectangle(0, ICON_WIPE_Y, 320, ICON_WIPE_H, BG)
    except: pass

    for i in range(-2, 3):
        if not apps: break
        idx = (selected + i) % len(apps)
        app = apps[idx]
        x   = CENTER_X + i * SPACING + offset
        if x < -64 or x > 384:
            continue
        if i == 0 and offset == 0:
            try: disp.draw_rectangle(x - 40, BORDER_TOP, 80, 80, ACCENT)
            except: pass
        text_color = TEXT_COLOR if (i == 0 and offset == 0) else DIM
        try:
            name_clamp = app.name[:16]
            text_x = max(0, min(312, x - (len(name_clamp) * 4)))
            disp.draw_text8x8(int(text_x), TEXT_Y + 4, name_clamp, text_color)
        except: pass

# ===== ANIMATION =====
_ANIM_ORDER = [0, -1, 1, -2, 2]
ANIM_STEPS  = 6

def _draw_icons_fast(offset):
    try: disp.fill_rectangle(0, ANIM_STRIP_Y, 320, ANIM_STRIP_H, BG)
    except: pass
    for i in _ANIM_ORDER:
        if not apps: break
        idx = (selected + i) % len(apps)
        app = apps[idx]
        x   = CENTER_X + i * SPACING + offset
        if x < -48 or x > 368:
            continue
        if app.icon:
            try: draw_icon(app.icon, x - 16, ICON_Y)
            except: pass
    try: disp.fill_rectangle(0, ICON_WIPE_Y, 320, ICON_WIPE_H, BG)
    except: pass

def animate_scroll(direction):
    if not apps or len(apps) <= 1:
        return
    gc.collect()
    try: disp.fill_rectangle(0, TEXT_Y, 320, TEXT_H, BG)
    except: pass
    distance = SPACING * direction
    offsets = []
    for s in range(ANIM_STEPS + 1):
        t     = s / ANIM_STEPS
        eased = 0.5 - 0.5 * math.cos(math.pi * t)
        offsets.append(int(round(eased * distance)))
    for offset in offsets:
        _draw_icons_fast(offset)

# ===== HOME & LAUNCH =====
def render_home():
    global apps, selected
    gc.collect()
    apps = list_apps()
    if not apps:
        try:
            disp.fill_rectangle(0, DRAW_Y, 320, DRAW_H, BG)
            disp.draw_text8x8(88, CENTER_Y, "No apps found", TEXT_COLOR)
        except: pass
        return
    selected %= len(apps)
    draw_status_bar()
    draw_frame(0, full_clear=True)

def launch_app(app):
    try:
        try: disp.fill_rectangle(0, 0, 320, 240, BG)
        except: pass
        gc.collect()

        module_name = "apps." + app.name + ".main"
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
        except: pass

        module = __import__(module_name, None, None, ["run"])
        if hasattr(module, "run"):
            module.run(disp)
        else:
            raise Exception("no run() in app")

    except Exception as e:
        try:
            disp.fill_rectangle(0, DRAW_Y, 320, DRAW_H, BG)
            disp.draw_text8x8(10, CENTER_Y - 10, "App crashed",  TEXT_COLOR)
            disp.draw_text8x8(10, CENTER_Y + 10, str(e)[:38],    TEXT_COLOR)
        except: pass
        time.sleep(2)

    finally:
        gc.collect()
        render_home()

render_home()

# ===== MAIN LOOP =====
while True:
    update_clock()
    try:
        draw_wifi_status(network.WLAN(network.STA_IF).isconnected())
    except: pass

    btn = buttons.button_input()

    if apps:
        if btn == 1:
            animate_scroll(1)
            selected = (selected - 1) % len(apps)
            draw_frame(0)
            gc.collect()

        elif btn == 2:
            animate_scroll(-1)
            selected = (selected + 1) % len(apps)
            draw_frame(0)
            gc.collect()

        elif btn == 3:
            launch_app(apps[selected])

        elif btn == 4:
            render_home()

    if btn:
        last_activity = time.time()

    if sleeping:
        apply_brightness(settings.get("brightness", 100))
        sleeping = False

    gc.collect()
    time.sleep(0.01)
