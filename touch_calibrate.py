# ===== IMPORTS =====
import time
from machine import Pin, SPI
from ili9341 import Display
import ujson

# ===== DISPLAY SETUP =====
spi_disp = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi_disp, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)

SCREEN_W = 320
SCREEN_H = 240

# ===== BACKLIGHT SETUP =====
from machine import PWM

boot_brightness = 100
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
# ===== TOUCH SETUP =====
spi_touch = SPI(2, baudrate=2000000, polarity=0, phase=0,
                sck=Pin(25), mosi=Pin(32), miso=Pin(39))

cs = Pin(33, Pin.OUT)
irq = Pin(36, Pin.IN)

cs.value(1)

CAL_FILE = "touch_cal.json"

# ===== RAW TOUCH READ =====
def read(cmd):
    cs.value(0)
    spi_touch.write(bytearray([cmd]))
    data = spi_touch.read(2)
    cs.value(1)
    return ((data[0] << 8) | data[1]) >> 3

def read_touch():
    if irq.value():
        return None
    x = read(0xD0)
    y = read(0x90)
    return x, y

# ===== WAIT FOR TOUCH =====
def wait_touch():
    while True:
        t = read_touch()
        if t:
            while read_touch():  # wait release
                time.sleep(0.01)
            return t
        time.sleep(0.01)

# ===== DRAW TARGET =====
def draw_target(x, y):
    disp.fill_rectangle(0,0,SCREEN_W,SCREEN_H,0)
    disp.draw_rectangle(x-10, y-10, 20, 20, 0xFFFF)

# ===== CALIBRATION POINTS =====
points = [
    (20, 20),                       # top left
    (SCREEN_W-20, 20),              # top right
    (SCREEN_W-20, SCREEN_H-20),     # bottom right
    (20, SCREEN_H-20)               # bottom left
]

raw_points = []

print("Touch the 4 targets...")

for x,y in points:
    draw_target(x,y)
    raw = wait_touch()
    raw_points.append(raw)
    time.sleep(0.5)

# ===== COMPUTE CALIBRATION =====
xs = [p[0] for p in raw_points]
ys = [p[1] for p in raw_points]

cal = {
    "X_MIN": min(xs),
    "X_MAX": max(xs),
    "Y_MIN": min(ys),
    "Y_MAX": max(ys)
}

# ===== SAVE =====
with open(CAL_FILE, "w") as f:
    ujson.dump(cal, f)

disp.fill_rectangle(0,0,SCREEN_W,SCREEN_H,0)
print("Calibration saved:", cal)
print("Restart your main program.")
