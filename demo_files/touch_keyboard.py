# ===== IMPORTS =====
import time
from machine import Pin, SPI, PWM
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

# ===== TOUCH SMOOTHING =====
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

    x = map_value(avg_y, cal["Y_MIN"], cal["Y_MAX"], 0, SCREEN_W)
    y = map_value(avg_x, cal["X_MIN"], cal["X_MAX"], 0, SCREEN_H)

    return x,y

# ===== TEXT INPUT =====
text = ""

# ===== KEYBOARD =====
rows = [
    "QWERTYUIOP",
    "ASDFGHJKL",
    "ZXCVBNM"
]

keys = []

TEXTBOX_H = 90
KEY_W = 28
KEY_H = 28

# ===== DRAW TEXTBOX =====
def draw_textbox():

    disp.fill_rectangle(0,0,SCREEN_W,TEXTBOX_H,0)

    disp.draw_rectangle(2,2,SCREEN_W-4,TEXTBOX_H-4,0xFFFF)

    x = 10
    y = 10

    for ch in text:
        disp.draw_text8x8(x,y,ch,0xFFFF)

        x += 8

        if x > SCREEN_W-10:
            x = 10
            y += 10

# ===== DRAW KEYBOARD =====
def draw_keyboard():

    global keys
    keys = []

    y_start = TEXTBOX_H + 5

    for r,row in enumerate(rows):

        for c,ch in enumerate(row):

            x = c * (KEY_W+2) + 5
            y = y_start + r*(KEY_H+4)

            disp.fill_rectangle(x,y,KEY_W,KEY_H,0x4208)
            disp.draw_rectangle(x,y,KEY_W,KEY_H,0xFFFF)

            disp.draw_text8x8(x+10,y+10,ch,0xFFFF)

            keys.append((x,y,KEY_W,KEY_H,ch))

    # BACKSPACE
    dx = 5
    dy = y_start + 3*(KEY_H+4)

    disp.fill_rectangle(dx,dy,60,KEY_H,0x4208)
    disp.draw_rectangle(dx,dy,60,KEY_H,0xFFFF)

    disp.draw_text8x8(dx+15,dy+10,"DEL",0xFFFF)

    keys.append((dx,dy,60,KEY_H,"DEL"))

    # SPACEBAR
    sx = 75
    sy = dy

    disp.fill_rectangle(sx,sy,200,KEY_H,0x4208)
    disp.draw_rectangle(sx,sy,200,KEY_H,0xFFFF)

    disp.draw_text8x8(sx+85,sy+10,"SPACE",0xFFFF)

    keys.append((sx,sy,200,KEY_H," "))

# ===== INITIAL DRAW =====
disp.clear(0)

draw_textbox()
draw_keyboard()

print("Touch keyboard ready")

# ===== MAIN LOOP =====
while True:

    pos = get_touch_pixel()

    if pos:

        tx,ty = pos

        for x,y,w,h,val in keys:

            if x <= tx <= x+w and y <= ty <= y+h:

                if val == "DEL":
                    text = text[:-1]
                else:
                    text += val

                draw_textbox()

                time.sleep(0.25)

    time.sleep(0.05)
