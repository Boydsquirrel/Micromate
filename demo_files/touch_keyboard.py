# full_keyboard_optimized_fixed.py

# ===== IMPORTS =====
import time
from machine import Pin, SPI, PWM
from ili9341 import Display
import ujson
import urandom

# ===== DISPLAY SETUP =====
spi_disp = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
disp = Display(spi_disp, dc=Pin(2), cs=Pin(15), rst=Pin(0), width=320, height=240)

SCREEN_W = 320
SCREEN_H = 240

# ===== BACKLIGHT =====
pwm = PWM(Pin(21))
pwm.freq(1000)
pwm.duty_u16(65535)

# ===== BUTTONS (NON BLOCKING) =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)   # RIGHT
button2 = Pin(19, Pin.IN, Pin.PULL_UP)   # LEFT
button3 = Pin(18, Pin.IN, Pin.PULL_UP)   # SELECT
button4 = Pin(16, Pin.IN, Pin.PULL_UP)   # ROW DOWN

last_btn_state = [1,1,1,1]

def read_buttons():
    global last_btn_state

    states = [
        button1.value(),
        button2.value(),
        button3.value(),
        button4.value()
    ]

    for i,v in enumerate(states):
        if v == 0 and last_btn_state[i] == 1:
            last_btn_state = states
            return i+1

    last_btn_state = states
    return 0

# ===== TOUCH SETUP =====
spi_touch = SPI(2, baudrate=2000000, polarity=0, phase=0,
                sck=Pin(25), mosi=Pin(32), miso=Pin(39))

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
    return int((v - in_min) * (out_max - out_min) /
              (in_max - in_min) + out_min)

# ===== LOAD CAL =====
try:
    with open(CAL_FILE,"r") as f:
        cal = ujson.load(f)
except:
    cal = {"X_MIN":400,"X_MAX":3900,"Y_MIN":200,"Y_MAX":3900}

def get_touch_pixel():
    t = read_touch()
    if not t:
        return None

    x_raw,y_raw = t

    # preserved mapping you had working (swap + possible inversion already baked in)
    x = map_value(y_raw, cal["Y_MIN"], cal["Y_MAX"], 0, SCREEN_W)
    y = map_value(x_raw, cal["X_MIN"], cal["X_MAX"], 0, SCREEN_H)

    return x,y

# ===== UI =====
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

layouts = {
"letters":[
"QWERTYUIOP",
"ASDFGHJKL",
"ZXCVBNM"
],
"numbers":[
"1234567890"
],
"symbols":[
"!@#?.,:;"
]
}

keys=[]
text=""

CURSOR_ROW=0
CURSOR_COL=0
cursor_key=None  # currently highlighted key tuple

# ===== BUILD KEYS =====
def build_keys():
    global keys, CURSOR_ROW, CURSOR_COL, cursor_key
    keys=[]

    rows = layouts[MODES[mode_idx]]

    y_start = TEXTBOX_H + 6

    for r,row in enumerate(rows):

        row_len=len(row)
        total_w=row_len*KEY_W+(row_len-1)*KEY_SP
        x_start=(SCREEN_W-total_w)//2

        for c,ch in enumerate(row):

            x=x_start+c*(KEY_W+KEY_SP)
            y=y_start+r*(KEY_H+KEY_SP)

            keys.append((x,y,KEY_W,KEY_H,ch,r,c))

    br=len(rows)

    my=y_start+br*(KEY_H+KEY_SP)

    # MODE, DEL, SPACE
    keys.append((6,my,60,KEY_H,"MODE",br,0))
    keys.append((70,my,60,KEY_H,"DEL",br,1))
    keys.append((134,my,140,KEY_H," ",br,2))

    # reset cursor to first key (safe)
    CURSOR_ROW = 0
    CURSOR_COL = 0
    cursor_key = keys[0] if keys else None

# ===== DRAW TEXTBOX =====
def draw_textbox():

    disp.fill_rectangle(0,0,SCREEN_W,TEXTBOX_H,BG_COLOR)
    disp.draw_rectangle(2,2,SCREEN_W-4,TEXTBOX_H-4,KEY_BORDER)

    x=8
    y=8

    for ch in text:
        disp.draw_text8x8(x,y,ch,TXT_COLOR)
        x+=8
        if x>SCREEN_W-12:
            x=8
            y+=10

# ===== DRAW KEY =====
def draw_key(k):

    x,y,w,h,val,_,_=k

    disp.fill_rectangle(x,y,w,h,KEY_BG)
    disp.draw_rectangle(x,y,w,h,KEY_BORDER)

    lx=x+(w//2)-4
    ly=y+(h//2)-4

    if val==" ":
        disp.draw_text8x8(lx-12,ly,"SPACE",TXT_COLOR)
    elif val=="MODE":
        disp.draw_text8x8(lx-8,ly,MODES[mode_idx][:4].upper(),TXT_COLOR)
    elif val=="DEL":
        disp.draw_text8x8(lx-6,ly,"DEL",TXT_COLOR)
    else:
        # single char label
        disp.draw_text8x8(lx,ly,val,TXT_COLOR)

# ===== DRAW KEYBOARD =====
def draw_keyboard():

    disp.fill_rectangle(0,TEXTBOX_H,SCREEN_W,SCREEN_H-TEXTBOX_H,BG_COLOR)

    for k in keys:
        draw_key(k)

# ===== CURSOR =====
def draw_cursor(new_key):

    global cursor_key, CURSOR_ROW, CURSOR_COL

    # restore previous key by redrawing it (no full keyboard redraw)
    if cursor_key:
        draw_key(cursor_key)

    # draw highlight rectangle around new_key
    x,y,w,h,_,_,_=new_key
    disp.draw_rectangle(x-2,y-2,w+4,h+4,CURSOR_COLOR)

    cursor_key=new_key

# ===== KEY PRESS =====
def press_key(k):

    global text,mode_idx, CURSOR_ROW, CURSOR_COL, cursor_key

    val=k[4]

    if val=="DEL":
        text=text[:-1]

    elif val==" ":
        text+=" "

    elif val=="MODE":
        mode_idx=(mode_idx+1)%len(MODES)
        build_keys()
        draw_keyboard()
        # ensure cursor points to first key in new layout
        draw_cursor(keys[0])

    else:
        text+=val

    draw_textbox()

# ===== FIND KEY =====
def hit_key(tx,ty):

    for k in keys:
        x,y,w,h,_,_,_=k
        if x<=tx<=x+w and y<=ty<=y+h:
            return k
    return None

# ===== START =====
build_keys()

disp.clear(BG_COLOR)

draw_textbox()
draw_keyboard()

# set initial cursor highlight
if keys:
    draw_cursor(keys[0])

print("keyboard ready")

# ===== MAIN LOOP =====
while True:

    # TOUCH
    pos=get_touch_pixel()
    if pos:
        k=hit_key(pos[0],pos[1])
        if k:
            # quick visual flash for touch
            x,y,w,h,_,_,_=k
            disp.fill_rectangle(x,y,w,h,0xFFFF)
            disp.draw_text8x8(x+(w//2)-4,y+(h//2)-4, k[4] if k[4] not in (" ","MODE","DEL") else ("SPACE" if k[4]==" " else ("MODE" if k[4]=="MODE" else "DEL")), 0x0000)
            time.sleep(0.08)
            draw_key(k)  # restore look
            press_key(k)

    # BUTTONS
    btn=read_buttons()

    if btn:

        # build list of available row indices and keys in current row
        rows = sorted(set(k[5] for k in keys))
        row_keys = [k for k in keys if k[5]==CURSOR_ROW]
        if not row_keys:
            # reset to first available row
            CURSOR_ROW = rows[0]
            row_keys = [k for k in keys if k[5]==CURSOR_ROW]

        if btn==1:  # RIGHT
            CURSOR_COL = (CURSOR_COL + 1) % len(row_keys)

        elif btn==2:  # LEFT
            CURSOR_COL = (CURSOR_COL - 1) % len(row_keys)

        elif btn==4:  # ROW DOWN (next row)
            idx = rows.index(CURSOR_ROW)
            idx = (idx + 1) % len(rows)
            CURSOR_ROW = rows[idx]
            # clamp CURSOR_COL to new row length
            new_row_keys = [k for k in keys if k[5]==CURSOR_ROW]
            CURSOR_COL = min(CURSOR_COL, len(new_row_keys)-1)

        elif btn==3:  # SELECT
            row_keys = [k for k in keys if k[5]==CURSOR_ROW]
            if row_keys:
                press_key(row_keys[CURSOR_COL])

        # update new_key and redraw minimal
        row_keys = [k for k in keys if k[5]==CURSOR_ROW]
        if row_keys:
            new_key = row_keys[CURSOR_COL]
            draw_cursor(new_key)

    time.sleep(0.03)
