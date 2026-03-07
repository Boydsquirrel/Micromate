
# ===== IMPORTS =====
import time
from machine import Pin, SPI, PWM
import urandom
from ili9341 import Display
import ujson

# ===== DISPLAY SETUP =====
spi_disp = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi_disp, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)

SCREEN_W = 320
SCREEN_H = 240

# ===== BACKLIGHT =====
pwm = PWM(Pin(21))
pwm.freq(1000)
pwm.duty_u16(65535)

# ===== TOUCH SETUP =====
spi_touch = SPI(2, baudrate=2000000, polarity=0, phase=0,
                sck=Pin(25), mosi=Pin(32), miso=Pin(39))

cs = Pin(33, Pin.OUT)
irq = Pin(36, Pin.IN)

cs.value(1)

CAL_FILE = "touch_cal.json"

# ===== RAW TOUCH =====
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

# ===== MAP VALUE =====
def map_value(v, in_min, in_max, out_min, out_max):
    return int((v - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

# ===== LOAD CALIBRATION =====
try:
    with open(CAL_FILE,"r") as f:
        cal = ujson.load(f)
except:
    cal = {"X_MIN":400,"X_MAX":3900,"Y_MIN":200,"Y_MAX":3900}

# ===== SMOOTH TOUCH =====
def get_touch_pixel(samples=3):

    vals = []

    for _ in range(samples):
        t = read_touch()
        if t:
            vals.append(t)
        time.sleep(0.01)

    if not vals:
        return None

    avg_x = sum(v[0] for v in vals) // len(vals)
    avg_y = sum(v[1] for v in vals) // len(vals)

    # AXIS SWAP + INVERSION
    x = map_value(avg_y, cal["Y_MIN"], cal["Y_MAX"], 0, SCREEN_W)
    y = map_value(avg_x, cal["X_MIN"], cal["X_MAX"], 0, SCREEN_H)

    return x,y

# ===== RECTANGLES =====
rectangles = []

def draw_rectangles(num=4):

    rectangles.clear()
    disp.clear(0)

    attempts = 0

    while len(rectangles) < num and attempts < 100:

        attempts += 1

        w = urandom.getrandbits(6) + 40
        h = urandom.getrandbits(6) + 40

        x = urandom.getrandbits(8) % (SCREEN_W - w)
        y = urandom.getrandbits(8) % (SCREEN_H - h)

        overlap = False

        for rx,ry,rw,rh,_ in rectangles:
            if not (x+ w < rx or x > rx+rw or y+h < ry or y > ry+rh):
                overlap = True
                break

        if overlap:
            continue

        r = urandom.getrandbits(5) << 11
        g = urandom.getrandbits(6) << 5
        b = urandom.getrandbits(5)

        color = r | g | b

        disp.fill_rectangle(x,y,w,h,color)
        disp.draw_rectangle(x,y,w,h,0xFFFF)

        rectangles.append((x,y,w,h,color))

draw_rectangles()

# ===== MAIN LOOP =====
PADDING = 12

print("Touch screen ready")

while True:

    pos = get_touch_pixel()

    if pos:

        tx,ty = pos
        print("Touch:",tx,ty)

        # draw debug dot
        disp.fill_rectangle(tx-3,ty-3,6,6,0xFFFF)
        time.sleep(0.05)
        disp.fill_rectangle(tx-3,ty-3,6,6,0)

        for i,(x,y,w,h,color) in enumerate(rectangles):

            if x-PADDING <= tx <= x+w+PADDING and y-PADDING <= ty <= y+h+PADDING:

                disp.fill_rectangle(x,y,w,h,0xFFFF)
                time.sleep(0.1)

                disp.fill_rectangle(x,y,w,h,color)
                disp.draw_rectangle(x,y,w,h,0xFFFF)

                print("Rectangle",i+1,"touched")

                break

    time.sleep(0.05)
