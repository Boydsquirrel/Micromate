# keyboard.py — shared keyboard utility for MicroMate
# Usage:
#   import keyboard
#   result = keyboard.get_input(disp, prompt="Enter name:")
#   # returns string on DONE, None on cancel (B4 when text empty)

import time
import gc
from machine import Pin

# ===== BUTTONS =====
_b1 = Pin(17, Pin.IN, Pin.PULL_UP)  # RIGHT
_b2 = Pin(19, Pin.IN, Pin.PULL_UP)  # LEFT
_b3 = Pin(18, Pin.IN, Pin.PULL_UP)  # SELECT
_b4 = Pin(16,  Pin.IN, Pin.PULL_UP)  # ROW UP / cancel if empty
_last = [1, 1, 1, 1]

def _btn():
    global _last
    pins = [_b1, _b2, _b3, _b4]
    for i in range(4):
        v = pins[i].value()
        if v == 0 and _last[i] == 1:
            _last[i] = 0
            _last = [pins[j].value() for j in range(4)]
            return i + 1
        _last[i] = v
    return 0

# ===== TOUCH (optional) =====
_touch_ok = False
_spi_t = _cs = _irq = None
_cal = {"X_MIN": 400, "X_MAX": 3900, "Y_MIN": 200, "Y_MAX": 3900}

try:
    from machine import SPI
    _spi_t = SPI(2, baudrate=2000000, polarity=0, phase=0,
                 sck=Pin(25), mosi=Pin(32), miso=Pin(39))
    _cs  = Pin(33, Pin.OUT)
    _irq = Pin(36, Pin.IN)
    _cs.value(1)
    _touch_ok = True
except:
    pass

try:
    import ujson
    with open("touch_cal.json", "r") as f:
        _cal = ujson.load(f)
except:
    pass

def _read_raw(cmd):
    _cs.value(0)
    _spi_t.write(bytearray([cmd]))
    d = _spi_t.read(2)
    _cs.value(1)
    return ((d[0] << 8) | d[1]) >> 3

def _map(v, mn, mx, omn, omx):
    if mx == mn: return omn
    return max(omn, min(omx, int((v - mn) * (omx - omn) / (mx - mn) + omn)))

def _touch_pixel():
    if not _touch_ok or _irq.value():
        return None
    xr = _read_raw(0xD0)
    yr = _read_raw(0x90)
    return (_map(yr, _cal["Y_MIN"], _cal["Y_MAX"], 0, 320),
            _map(xr, _cal["X_MIN"], _cal["X_MAX"], 0, 240))

# ===== COLOURS =====
BLACK  = 0x0000
WHITE  = 0xFFFF
RED    = 0xF800
CYAN   = 0x07FF
KEY_BG = 0x4208

# ===== LAYOUT CONSTANTS =====
# Screen: 320x240
# Textbox: 0-80 (80px)  — fits prompt + 5 lines of wrapped text
# Keys:    84-205        — 3 char rows + 1 control row, each 28px tall, 3px gap
# Slack:   205-240       — 35px breathing room at bottom

TEXTBOX_H  = 80
KB_Y0      = TEXTBOX_H + 4   # 84
KEY_W      = 28
KEY_H      = 28
KEY_SP     = 3
CHARS_LINE = 38               # chars per textbox line  (8px font, 8px wide)
LINE_H     = 11               # textbox line height px
TEXT_Y0    = 18               # y of first text line inside textbox

_LAYOUTS = {
    "ABC": ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"],
    "123": ["1234567890", "!@#$%^&*()", "+-=.,?;:_"],
}
_MODE_ORDER = ["ABC", "123"]

# ===== BUILD KEYS =====
# Each key tuple: (x, y, w, h, val, row, col)

def _build_keys(mode):
    keys = []
    rows = _LAYOUTS[mode]
    for r, row in enumerate(rows):
        n = len(row)
        total_w = n * KEY_W + (n - 1) * KEY_SP
        x0 = (320 - total_w) // 2
        y  = KB_Y0 + r * (KEY_H + KEY_SP)
        for c, ch in enumerate(row):
            keys.append((x0 + c * (KEY_W + KEY_SP), y, KEY_W, KEY_H, ch, r, c))
    # control row
    br = len(rows)
    cy = KB_Y0 + br * (KEY_H + KEY_SP)
    keys.append((4,   cy,  58, KEY_H, "MODE", br, 0))
    keys.append((66,  cy,  58, KEY_H, "DEL",  br, 1))
    keys.append((128, cy,  72, KEY_H, "DONE", br, 2))
    keys.append((204, cy, 112, KEY_H, " ",    br, 3))
    return keys

# ===== TEXT WRAP =====
def _wrap_lines(text):
    """Split text into wrapped lines of CHARS_LINE width."""
    lines = []
    while len(text) > CHARS_LINE:
        lines.append(text[:CHARS_LINE])
        text = text[CHARS_LINE:]
    lines.append(text)
    return lines

# ===== DRAW TEXTBOX =====
def _draw_textbox(disp, prompt, text):
    disp.fill_rectangle(0, 0, 320, TEXTBOX_H, BLACK)
    disp.draw_rectangle(2, 2, 316, TEXTBOX_H - 4, WHITE)

    # prompt
    if prompt:
        p = prompt[:CHARS_LINE]
        if p: disp.draw_text8x8(8, 5, p, CYAN)

    # text with wrapping — show only last N lines that fit
    lines   = _wrap_lines(text) if text else [""]
    max_vis = (TEXTBOX_H - TEXT_Y0 - 4) // LINE_H   # 5 lines
    vis     = lines[-max_vis:]                        # scroll: keep last lines

    for i, line in enumerate(vis):
        y = TEXT_Y0 + i * LINE_H
        if line:  # guard: draw_text8x8 crashes on empty string
            disp.draw_text8x8(8, y, line, WHITE)

    # cursor indicator — small block after last char
    last  = vis[-1] if vis else ""
    cur_x = 8 + len(last) * 8
    cur_y = TEXT_Y0 + max(0, len(vis) - 1) * LINE_H
    if 8 <= cur_x < 316 and cur_y < TEXTBOX_H:
        disp.fill_rectangle(cur_x, cur_y, 4, 8, CYAN)

# ===== DRAW KEY =====
def _draw_key(disp, k, highlighted=False):
    x, y, w, h, val, _, _ = k
    disp.fill_rectangle(x, y, w, h, RED if highlighted else KEY_BG)
    disp.draw_rectangle(x, y, w, h, WHITE)
    label = {"MODE": "MODE", "DEL": "DEL", "DONE": "DONE", " ": "SPC"}.get(val, val)
    lx = max(x, x + (w // 2) - len(label) * 4)
    ly = y + (h // 2) - 4
    if label: disp.draw_text8x8(lx, ly, label, WHITE)

def _draw_keyboard(disp, keys, cidx):
    disp.fill_rectangle(0, TEXTBOX_H, 320, 240 - TEXTBOX_H, BLACK)
    for i, k in enumerate(keys):
        _draw_key(disp, k, highlighted=(i == cidx))

# ===== CURSOR HELPERS =====
def _cursor_index(keys, crow, ccol):
    row_keys = [(i, k) for i, k in enumerate(keys) if k[5] == crow]
    if not row_keys: return 0
    ccol = min(ccol, len(row_keys) - 1)
    return row_keys[ccol][0]

def _hit_key(keys, tx, ty):
    for i, k in enumerate(keys):
        if k[0] <= tx <= k[0] + k[2] and k[1] <= ty <= k[1] + k[3]:
            return i
    return None

# ===== MAIN ENTRY POINT =====
def get_input(disp, prompt="", prefill=""):
    """
    Display keyboard, return typed string when DONE pressed.
    Returns None if B4 pressed while text is empty (cancel).
    """
    gc.collect()

    mode_idx = 0
    mode = _MODE_ORDER[mode_idx]
    keys = _build_keys(mode)
    text = prefill

    crow, ccol = 0, 0
    cidx = _cursor_index(keys, crow, ccol)

    _draw_textbox(disp, prompt, text)
    _draw_keyboard(disp, keys, cidx)

    _last_touch = None

    while True:
        # ---- touch ----
        tp = _touch_pixel()
        if tp and tp != _last_touch:
            _last_touch = tp
            hi = _hit_key(keys, tp[0], tp[1])
            if hi is not None:
                _draw_key(disp, keys[hi], highlighted=True)
                time.sleep(0.07)
                val = keys[hi][4]
                changed = _handle_val(val, text, mode_idx)
                if changed is False:                 # DONE
                    gc.collect(); return text
                elif changed is None:                # MODE switch
                    mode_idx = (mode_idx + 1) % len(_MODE_ORDER)
                    mode = _MODE_ORDER[mode_idx]
                    keys = _build_keys(mode)
                    crow, ccol = 0, 0
                    cidx = _cursor_index(keys, crow, ccol)
                    _draw_keyboard(disp, keys, cidx)
                else:
                    text = changed
                    _draw_key(disp, keys[hi])
                    _draw_textbox(disp, prompt, text)
        elif not tp:
            _last_touch = None

        # ---- buttons ----
        btn = _btn()
        if btn:
            rows     = sorted(set(k[5] for k in keys))
            row_keys = [k for k in keys if k[5] == crow]

            if btn == 1:    # RIGHT
                ccol = (ccol + 1) % len(row_keys)

            elif btn == 2:  # LEFT
                ccol = (ccol - 1) % len(row_keys)

            elif btn == 3:  # SELECT
                val     = keys[cidx][4]
                changed = _handle_val(val, text, mode_idx)
                if changed is False:
                    gc.collect(); return text
                elif changed is None:
                    mode_idx = (mode_idx + 1) % len(_MODE_ORDER)
                    mode = _MODE_ORDER[mode_idx]
                    keys = _build_keys(mode)
                    crow, ccol = 0, 0
                    cidx = _cursor_index(keys, crow, ccol)
                    _draw_keyboard(disp, keys, cidx)
                    continue
                else:
                    text = changed
                    _draw_textbox(disp, prompt, text)

            elif btn == 4:  # ROW UP / cancel
                if not text:
                    gc.collect(); return None
                ri   = rows.index(crow)
                crow = rows[(ri - 1) % len(rows)]
                ccol = min(ccol, len([k for k in keys if k[5] == crow]) - 1)

            cidx = _cursor_index(keys, crow, ccol)
            # redraw only changed keys
            for i, k in enumerate(keys):
                _draw_key(disp, k, highlighted=(i == cidx))

        time.sleep(0.02)

# ===== VAL HANDLER =====
def _handle_val(val, text, mode_idx):
    """
    Returns: new text string  — character added/deleted
             None             — mode switch requested
             False            — DONE
    """
    if val == "DONE": return False
    if val == "MODE": return None
    if val == "DEL":  return text[:-1]
    if val == " ":    return text + " "
    return text + val

