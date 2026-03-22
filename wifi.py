import network
import time
import os
from machine import Pin

FILE = "networks.txt"
KEY  = b'SquirR3LSFOL'

# ===== XOR CRYPTO =====
def xor_encrypt(data):
    d   = data.encode()
    enc = bytes([d[i] ^ KEY[i % len(KEY)] for i in range(len(d))])
    return enc.hex()

def xor_decrypt(hex_string):
    enc = bytes.fromhex(hex_string)
    dec = bytes([enc[i] ^ KEY[i % len(KEY)] for i in range(len(enc))])
    return dec.decode()

# ===== NETWORK FILE =====
def load_saved_networks():
    if FILE not in os.listdir():
        return {}
    nets = {}
    with open(FILE, "r") as f:
        for line in f:
            if "," in line:
                ssid, enc_pwd = line.strip().split(",", 1)
                try:
                    nets[ssid] = xor_decrypt(enc_pwd)
                except:
                    pass
    return nets

def save_network(ssid, pwd):
    nets = load_saved_networks()
    nets[ssid] = pwd
    with open(FILE, "w") as f:
        for s, p in nets.items():
            f.write(s + "," + xor_encrypt(p) + "\n")

# ===== SCAN =====
def scan_networks():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    raw   = wlan.scan()
    ssids = []
    seen  = {}
    for item in raw:
        name = item[0].decode()
        if name and name not in seen:
            seen[name] = True
            ssids.append(name)
    return ssids

# ===== CONNECT =====
def connect(ssid, pwd):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, pwd)
    for _ in range(20):
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    return False

# ===== COLOURS =====
BLACK  = 0x0000
WHITE  = 0xFFFF
CYAN   = 0x07FF
RED    = 0xF800
GREEN  = 0x07E0
GREY   = 0x4208
YELLOW = 0xFFE0

# ===== BUTTONS =====
_b1 = Pin(17, Pin.IN, Pin.PULL_UP)  # UP
_b2 = Pin(19, Pin.IN, Pin.PULL_UP)  # DOWN
_b3 = Pin(18, Pin.IN, Pin.PULL_UP)  # SELECT
_b4 = Pin(4,  Pin.IN, Pin.PULL_UP)  # BACK / CANCEL
_ls  = [1, 1, 1, 1]

def _btn():
    global _ls
    pins = [_b1, _b2, _b3, _b4]
    for i in range(4):
        v = pins[i].value()
        if v == 0 and _ls[i] == 1:
            _ls[i] = 0
            _ls = [pins[j].value() for j in range(4)]
            return i + 1
        _ls[i] = v
    return 0

# ===== UI HELPERS =====
PAGE_SIZE = 6   # networks visible at once

def _draw_header(disp, title):
    disp.fill_rectangle(0, 0, 320, 20, CYAN)
    disp.draw_text8x8(8, 6, title[:38], BLACK)

def _draw_status(disp, msg, color=WHITE):
    disp.fill_rectangle(0, 220, 320, 20, BLACK)
    disp.draw_text8x8(8, 226, msg[:38], color)

def _draw_hint(disp, hint):
    _draw_status(disp, hint, GREY)

def _draw_network_list(disp, nets, sel, page_start, saved):
    disp.fill_rectangle(0, 22, 320, 196, BLACK)
    visible = nets[page_start:page_start + PAGE_SIZE]
    for i, ssid in enumerate(visible):
        idx  = page_start + i
        y    = 24 + i * 32
        is_sel   = idx == sel
        is_saved = ssid in saved
        bg = GREY if is_sel else BLACK
        disp.fill_rectangle(0, y, 320, 30, bg)
        if is_sel:
            disp.draw_rectangle(0, y, 320, 30, CYAN)
        # saved dot
        dot_c = GREEN if is_saved else GREY
        disp.fill_rectangle(6, y + 11, 8, 8, dot_c)
        # ssid text — truncate to fit
        label = ssid[:34] if len(ssid) > 34 else ssid
        disp.draw_text8x8(20, y + 11, label, YELLOW if is_sel else WHITE)
    # scroll indicator
    total = len(nets)
    if total > PAGE_SIZE:
        bar_h = max(10, (PAGE_SIZE * 196) // total)
        bar_y = 22 + (page_start * 196) // total
        disp.fill_rectangle(315, 22, 5, 196, GREY)
        disp.fill_rectangle(315, bar_y, 5, bar_h, CYAN)

def _status_screen(disp, line1, line2="", color=WHITE):
    disp.clear(BLACK)
    _draw_header(disp, "WiFi")
    if line1:
        disp.draw_text8x8(10, 100, line1[:38], color)
    if line2:
        disp.draw_text8x8(10, 116, line2[:38], GREY)

# ===== AUTO CONNECT =====
def try_auto_connect(disp=None):
    saved = load_saved_networks()
    if disp:
        _status_screen(disp, "Scanning networks...", color=CYAN)
    nets = scan_networks()
    for ssid in nets:
        if ssid in saved:
            if disp:
                _status_screen(disp, "Connecting to:", ssid, CYAN)
            if connect(ssid, saved[ssid]):
                if disp:
                    _status_screen(disp, "Connected!", ssid, GREEN)
                    time.sleep(1)
                return True
    return False

# ===== MANUAL SELECT =====
def manual_mode(disp):
    import keyboard as kb

    _status_screen(disp, "Scanning...", color=CYAN)
    nets  = scan_networks()
    saved = load_saved_networks()

    if not nets:
        _status_screen(disp, "No networks found", color=RED)
        time.sleep(2)
        return

    sel        = 0
    page_start = 0

    # initial draw
    disp.clear(BLACK)
    _draw_header(disp, "Select Network")
    _draw_network_list(disp, nets, sel, page_start, saved)
    _draw_hint(disp, "B1=Up B2=Dn B3=Connect B4=Exit")

    while True:
        btn = _btn()

        if btn == 1:   # UP
            if sel > 0:
                sel -= 1
                if sel < page_start:
                    page_start = sel
                _draw_network_list(disp, nets, sel, page_start, saved)

        elif btn == 2:  # DOWN
            if sel < len(nets) - 1:
                sel += 1
                if sel >= page_start + PAGE_SIZE:
                    page_start = sel - PAGE_SIZE + 1
                _draw_network_list(disp, nets, sel, page_start, saved)

        elif btn == 3:  # SELECT
            ssid = nets[sel]
            # check if we have a saved password first
            if ssid in saved:
                _status_screen(disp, "Connecting to:", ssid, CYAN)
                if connect(ssid, saved[ssid]):
                    _status_screen(disp, "Connected!", ssid, GREEN)
                    time.sleep(1)
                    return
                else:
                    _status_screen(disp, "Wrong password?", ssid, RED)
                    time.sleep(1)
                    # fall through to ask for password

            # ask for password via keyboard
            pwd = kb.get_input(disp, prompt="Password: " + ssid[:20])
            if pwd is None:
                # cancelled — redraw list
                disp.clear(BLACK)
                _draw_header(disp, "Select Network")
                _draw_network_list(disp, nets, sel, page_start, saved)
                _draw_hint(disp, "B1=Up B2=Dn B3=Connect B4=Exit")
                continue

            _status_screen(disp, "Connecting to:", ssid, CYAN)
            if connect(ssid, pwd):
                save_network(ssid, pwd)
                saved = load_saved_networks()
                _status_screen(disp, "Connected + saved!", ssid, GREEN)
                time.sleep(1)
                return
            else:
                _status_screen(disp, "Failed to connect", ssid, RED)
                time.sleep(1)
                disp.clear(BLACK)
                _draw_header(disp, "Select Network")
                _draw_network_list(disp, nets, sel, page_start, saved)
                _draw_hint(disp, "B1=Up B2=Dn B3=Connect B4=Exit")

        elif btn == 4:  # BACK
            return

        time.sleep(0.02)

# ===== MAIN ENTRY =====
def wifi_manager(disp=None):
    if not try_auto_connect(disp):
        if disp:
            manual_mode(disp)
