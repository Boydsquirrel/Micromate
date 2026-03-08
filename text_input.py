# text_input.py
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

# ===== BUTTONS (NON-BLOCKING) =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)  # RIGHT
button2 = Pin(19, Pin.IN, Pin.PULL_UP)  # LEFT
button3 = Pin(18, Pin.IN, Pin.PULL_UP)  # SELECT
button4 = Pin(16, Pin.IN, Pin.PULL_UP)  # ROW DOWN
last_btn_state = [1, 1, 1, 1]

def read_buttons():
    global last_btn_state
    states = [button1.value(), button2.value(), button3.value(), button4.value()]
    for i, v in enumerate(states):
        if v == 0 and last_btn_state[i] == 1:
            last_btn_state = states
            return i + 1
    last_btn_state = states
    return 0

# ===== TOUCH SETUP =====
spi_touch = SPI(2, baudrate=2000000, polarity=0, phase=0, sck=Pin(25), mosi=Pin(32), miso=Pin(39))
cs = Pin(33, Pin.OUT)
irq = Pin(36, Pin.IN)
cs.value(1)

CAL_FILE = "touch_cal.json"

def read(cmd):
    cs.value(0)
    spi_touch.write(bytearray([cmd]))
    data = spi_touch.read(2)
    cs.value(1)
    return ((data[0] << 8) | data[1]) >> 3

def read_touch():
    if irq.value():
        return None
    return read(0xD0), read(0x90)

def map_value(v, in_min, in_max, out_min, out_max):
    return int((v - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

try:
    with open(CAL_FILE,"r") as f:
        cal = ujson.load(f)
except:
    cal = {"X_MIN":400,"X_MAX":3900,"Y_MIN":200,"Y_MAX":3900}

def get_touch_pixel():
    t = read_touch()
    if not t:
        return None
    x_raw, y_raw = t
    x = map_value(y_raw, cal["Y_MIN"], cal["Y_MAX"], 0, SCREEN_W)
    y = map_value(x_raw, cal["X_MIN"], cal["X_MAX"], 0, SCREEN_H)
    return x, y

# ===== UI SETTINGS =====
TEXTBOX_H = 70
KEY_W = 28
KEY_H = 26
KEY_SP = 4
KEY_BG = 0x4208
KEY_BORDER = 0xFFFF
TXT_COLOR = 0xFFFF
BG_COLOR = 0x0000
CURSOR_COLOR = 0xF800

MODES = ["letters","numbers","symbols"]
mode_idx = 0
keys = []
text = ""
CURSOR_ROW = 0
CURSOR_COL = 0
cursor_key = None

# ===== DEFAULT LAYOUTS =====
default_layouts = {
    "letters":["QWERTYUIOP","ASDFGHJKL","ZXCVBNM"],
    "numbers":["1234567890"],
    "symbols":["!@#?.,:;"]
}

layouts = default_layouts

# ===== BUILD KEYS =====
def build_keys():
    global keys
    keys = []
    rows = layouts[MODES[mode_idx]]
    y_start = TEXTBOX_H + 6

    # ---- main letter/number/symbol keys ----
    for r, row in enumerate(rows):
        row_len = len(row)
        total_w = row_len*KEY_W + (row_len-1)*KEY_SP
        x_start = (SCREEN_W - total_w)//2
        for c, ch in enumerate(row):
            x = x_start + c*(KEY_W+KEY_SP)
            y = y_start + r*(KEY_H+KEY_SP)
            keys.append((x, y, KEY_W, KEY_H, ch, r, c))

    # ---- first special row: MODE, DEL, SPACE ----
    br = len(rows)
    my = y_start + br*(KEY_H + KEY_SP)
    spacing = 4
    total_special = SCREEN_W - 2*spacing
    key_w = (total_special - 2*spacing)//3
    keys.append((spacing, my, key_w, KEY_H, "MODE", br, 0))
    keys.append((spacing+key_w+spacing, my, key_w, KEY_H, "DEL", br, 1))
    keys.append((spacing+2*(key_w+spacing), my, key_w, KEY_H, " ", br, 2))

    # ---- second special row: ENTER ----
    br2 = br + 1
    my2 = my + KEY_H + KEY_SP
    enter_w = SCREEN_W - 2*spacing
    keys.append((spacing, my2, enter_w, KEY_H, "ENTER", br2, 0))

# ===== DRAW TEXTBOX =====
def draw_textbox():
    disp.fill_rectangle(0, 0, SCREEN_W, TEXTBOX_H, BG_COLOR)
    disp.draw_rectangle(2, 2, SCREEN_W-4, TEXTBOX_H-4, KEY_BORDER)
    x = 8
    y = 8
    for ch in text:
        disp.draw_text8x8(x, y, ch, TXT_COLOR)
        x += 8
        if x > SCREEN_W-12:
            x = 8
            y += 10

# ===== DRAW KEY =====
def draw_key(k):
    x, y, w, h, val, _, _ = k
    disp.fill_rectangle(x, y, w, h, KEY_BG)
    disp.draw_rectangle(x, y, w, h, KEY_BORDER)
    lx = x + (w//2) - 4
    ly = y + (h//2) - 4
    if val==" ":
        disp.draw_text8x8(lx-12, ly, "SPACE", TXT_COLOR)
    elif val=="MODE":
        disp.draw_text8x8(lx-8, ly, MODES[mode_idx][:4].upper(), TXT_COLOR)
    elif val=="ENTER":
        disp.draw_text8x8(lx-12, ly, "ENTER", TXT_COLOR)
    else:
        disp.draw_text8x8(lx, ly, val, TXT_COLOR)

# ===== DRAW KEYBOARD =====
def draw_keyboard():
    disp.fill_rectangle(0, TEXTBOX_H, SCREEN_W, SCREEN_H-TEXTBOX_H, BG_COLOR)
    for k in keys:
        draw_key(k)

# ===== CURSOR =====
def draw_cursor(new_key):
    global cursor_key
    if cursor_key:
        x, y, w, h, _, _, _ = cursor_key
        disp.draw_rectangle(x-2, y-2, w+4, h+4, BG_COLOR)
    x, y, w, h, _, _, _ = new_key
    disp.draw_rectangle(x-2, y-2, w+4, h+4, CURSOR_COLOR)
    cursor_key = new_key

# ===== KEY PRESS =====
def press_key(k):
    global text, mode_idx
    val = k[4]
    if val=="DEL":
        text=text[:-1]
    elif val==" ":
        text+=" "
    elif val=="ENTER":
        return True  # signal to return text
    elif val=="MODE":
        mode_idx = (mode_idx + 1) % len(MODES)
        build_keys()
        draw_keyboard()
    else:
        text+=val
    draw_textbox()
    return False

# ===== HIT KEY =====
def hit_key(tx, ty):
    for k in keys:
        x, y, w, h, _, _, _ = k
        if x <= tx <= x+w and y <= ty <= y+h:
            return k

# ===== MAIN FUNCTION =====
def gettext(custom_layouts=None):
    global layouts, text, CURSOR_ROW, CURSOR_COL
    text=""
    CURSOR_ROW=0
    CURSOR_COL=0
    if custom_layouts:
        layouts = custom_layouts
    build_keys()
    disp.clear(BG_COLOR)
    draw_textbox()
    draw_keyboard()
    draw_cursor(keys[0])
    while True:
        # TOUCH
        pos = get_touch_pixel()
        if pos:
            k = hit_key(pos[0], pos[1])
            if k:
                if press_key(k):
                    return text

        # BUTTONS
        btn = read_buttons()
        if btn:
            rows = sorted(set(k[5] for k in keys))
            row_keys = [k for k in keys if k[5]==CURSOR_ROW]
            if btn==1:
                CURSOR_COL = (CURSOR_COL+1)%len(row_keys)
            elif btn==2:
                CURSOR_COL = (CURSOR_COL-1)%len(row_keys)
            elif btn==4:
                CURSOR_ROW = (CURSOR_ROW+1)%len(rows)
                CURSOR_COL = 0
            elif btn==3:
                if press_key(row_keys[CURSOR_COL]):
                    return text
            new_key = [k for k in keys if k[5]==CURSOR_ROW][CURSOR_COL]
            draw_cursor(new_key)
        time.sleep_ms(10)
