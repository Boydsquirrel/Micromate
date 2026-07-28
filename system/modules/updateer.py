# updateer.py — display-aware memory-safe updater for Micromate
import network
import machine
import time
import os
import gc

# ================= CONFIG =================
VERSION_FILE = "version.txt"
BASE_URL     = "http://noisy-disk-eb8d.cross-boyd.workers.dev/"
UPDATE_JSON  = "http://noisy-disk-eb8d.cross-boyd.workers.dev/version.json"
UPDATE_TXT   = BASE_URL + "update.txt"

# ================= COLOURS =================
BLACK  = 0x0000
WHITE  = 0xFFFF
CYAN   = 0x07FF
GREEN  = 0x07E0
RED    = 0xF800
GREY   = 0x4208
YELLOW = 0xFFE0

# ================= BUTTONS =================
# Using the same pins/pattern proven working in button_module.py
# (direct value check + explicit wait-for-release, no cross-call latched state)
from machine import Pin
_left   = Pin(17, Pin.IN, Pin.PULL_UP)
_right  = Pin(19, Pin.IN, Pin.PULL_UP)
_select = Pin(26, Pin.IN, Pin.PULL_UP)

def _wait_for_release(pin):
    while pin.value() == 0:
        time.sleep(0.01)
    time.sleep(0.05)  # debounce

def _left_pressed():
    if _left.value() == 0:
        _wait_for_release(_left)
        return True
    return False

def _right_pressed():
    if _right.value() == 0:
        _wait_for_release(_right)
        return True
    return False

def _select_pressed():
    if _select.value() == 0:
        _wait_for_release(_select)
        return True
    return False

# ================= DISPLAY HELPERS =================
def _show(disp, line1, line2="", line3="", color=WHITE):
    if not disp: return
    disp.clear(BLACK)
    disp.fill_rectangle(0, 0, 320, 20, CYAN)
    disp.draw_text8x8(8, 6, "Micromate Updater", BLACK)
    if line1: disp.draw_text8x8(10, 40, line1[:34], color)
    if line2: disp.draw_text8x8(10, 60, line2[:34], GREY)
    if line3: disp.draw_text8x8(10, 80, line3[:34], GREY)

def _progress(disp, label, done, total):
    if not disp: return
    disp.fill_rectangle(10, 100, 300, 30, BLACK)
    disp.draw_text8x8(10, 100, label[:28], WHITE)
    if total > 0:
        w = max(2, int((done / total) * 298))
        disp.fill_rectangle(10, 118, 298, 12, GREY)
        disp.fill_rectangle(10, 118, w,   12, CYAN)
        disp.draw_text8x8(10, 134, str(done) + "/" + str(total), GREY)

# ---- Download / Skip option boxes ----
_OPT_LABELS = ["Download", "Skip"]
_OPT_X      = [30, 180]
_OPT_Y      = 188
_OPT_W      = 120
_OPT_H      = 26

def _draw_option_box(disp, index, selected):
    if not disp: return
    x = _OPT_X[index]
    label = _OPT_LABELS[index]
    border = CYAN if selected else GREY
    text_c = CYAN if selected else WHITE
    disp.fill_rectangle(x, _OPT_Y, _OPT_W, _OPT_H, border)
    disp.fill_rectangle(x + 2, _OPT_Y + 2, _OPT_W - 4, _OPT_H - 4, BLACK)
    # rough centering
    disp.draw_text8x8(x + 12, _OPT_Y + 9, label, text_c)

def _draw_all_options(disp, selected):
    for i in range(len(_OPT_LABELS)):
        _draw_option_box(disp, i, i == selected)

def _prompt_choice(disp):
    """
    Returns "yes" (Download) or "no" (Skip).
    Navigate with left/right, confirm with select.
    Only redraws the two option boxes on change — not the whole screen.
    """
    if not disp:
        try:
            c = input("Update available! Install now? y/n: ").strip().lower()
            return "yes" if c in ("y", "yes") else "no"
        except:
            return "no"

    selected = 0  # default highlight = Download
    _draw_all_options(disp, selected)
    deadline = time.time() + 30
    while time.time() < deadline:
        if _left_pressed():
            new_sel = (selected - 1) % len(_OPT_LABELS)
            if new_sel != selected:
                old = selected
                selected = new_sel
                _draw_option_box(disp, old, False)
                _draw_option_box(disp, selected, True)
            deadline = time.time() + 30

        elif _right_pressed():
            new_sel = (selected + 1) % len(_OPT_LABELS)
            if new_sel != selected:
                old = selected
                selected = new_sel
                _draw_option_box(disp, old, False)
                _draw_option_box(disp, selected, True)
            deadline = time.time() + 30

        elif _select_pressed():
            return "yes" if selected == 0 else "no"

        time.sleep(0.05)

    return "no"

# ================= VERSION HELPERS =================
def ver(v):
    try:
        return tuple(map(int, str(v).split(".")))
    except:
        return (0,)

def get_local_version():
    if VERSION_FILE not in os.listdir():
        with open(VERSION_FILE, "w") as f:
            f.write("0.0")
        return "0.0"
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip() or "0.0"
    except:
        return "0.0"

def save_local_version(v):
    with open(VERSION_FILE, "w") as f:
        f.write(str(v))

# ================= FOLDER CREATION =================
def _ensure_dirs(filepath):
    parts = filepath.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return
    path = ""
    for part in parts[:-1]:
        path = path + part if not path else path + "/" + part
        try:
            os.listdir(path)
        except:
            try:
                os.mkdir(path)
            except:
                pass

# ================= LIGHTWEIGHT HTTPS FETCH =================
def _https_get(url, timeout=8):
    """
    Raw socket HTTPS GET, no cert verification, chunk-to-file to avoid
    heap fragmentation from string concatenation.
    """
    try:
        import usocket
    except:
        import socket as usocket
    try:
        import ussl
    except:
        import ssl as ussl
    gc.collect()

    url = url.replace("https://", "")
    host, path = (url.split("/", 1) + ["/"])[:2]
    path = "/" + path if not path.startswith("/") else path

    TMPFILE = "_htmp.txt"
    sock = usocket.socket()
    sock.settimeout(timeout)
    try:
        addr = usocket.getaddrinfo(host, 443)[0][-1]
        sock.connect(addr)
        ssl_sock = ussl.wrap_socket(sock, server_hostname=host,
                                    cert_reqs=ussl.CERT_NONE)
        req = ("GET " + path + " HTTP/1.0\r\nHost: " + host +
               "\r\nConnection: close\r\n\r\n")
        ssl_sock.write(req.encode())

        # Write chunks straight to temp file — no in-memory accumulation
        header_done = False
        with open(TMPFILE, "w") as fout:
            while True:
                chunk = ssl_sock.read(512)
                if not chunk:
                    break
                if not header_done:
                    sep = b"\r\n\r\n"
                    if sep in chunk:
                        chunk = chunk.split(sep, 1)[1]
                        header_done = True
                    else:
                        continue
                fout.write(chunk.decode("utf-8", "ignore"))
                gc.collect()

        ssl_sock.close()
    except Exception as e:
        try: sock.close()
        except: pass
        try: os.remove(TMPFILE)
        except: pass
        raise e

    with open(TMPFILE, "r") as fin:
        body = fin.read()
    try: os.remove(TMPFILE)
    except: pass
    gc.collect()
    return body

# ================= DOWNLOAD =================
def download_file(url, filename, retries=2):
    _ensure_dirs(filename)
    gc.collect()
    import urequests
    for attempt in range(retries + 1):
        try:
            r = urequests.get(url, timeout=10)
            if r.status_code != 200:
                print("HTTP", r.status_code, "for", filename)
                r.close()
                if attempt < retries:
                    time.sleep(1)
                    continue
                return False

            tmp = filename + ".tmp"
            binary_exts = (".raw", ".bin", ".png", ".jpg", ".jpeg", ".ico")
            is_binary   = any(filename.lower().endswith(e) for e in binary_exts)

            if is_binary:
                with open(tmp, "wb") as f:
                    f.write(r.content)
            else:
                with open(tmp, "w") as f:
                    f.write(r.text)

            r.close()
            del r
            gc.collect()

            try: os.remove(filename)
            except: pass
            os.rename(tmp, filename)
            print("Saved:", filename)
            return True

        except Exception as e:
            print("Attempt", attempt + 1, "failed:", e)
            try: r.close()
            except: pass
            gc.collect()
            if attempt < retries:
                time.sleep(1)

    return False

# ================= UPDATE CHECK =================
def check_for_update(disp=None):
    gc.collect()
    gc.collect()
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("Wi-Fi not connected, skipping update.")
        return False

    local_ver = get_local_version()

    try:
        import urequests
        r   = urequests.get(UPDATE_JSON + "?from=" + local_ver, timeout=8)
        raw = r.text
        r.close()
        del r
        gc.collect()
        json_start = raw.find("{")
        if json_start == -1:
            print("No JSON in response")
            return False
        import ujson
        data = ujson.loads(raw[json_start:])
        del raw
        gc.collect()
    except Exception as e:
        print("Failed to fetch version.json:", e)
        if disp:
            _show(disp, "Update check failed", str(e)[:34], color=RED)
            time.sleep(1)
        return False

    server_ver = str(data.get("version", "0.0"))
    files      = data.get("files", [])
    print("Local:", local_ver, "  Server:", server_ver)

    if ver(local_ver) >= ver(server_ver):
        print("Already up to date.")
        return False

    # fetch changelog
    changelog_lines = []
    try:
        import urequests as _ureq
        _cr = _ureq.get(UPDATE_TXT, timeout=6)
        cl_raw = _cr.text
        _cr.close()
        del _cr
        for line in cl_raw.splitlines():
            line = line.strip()
            if line and not line.startswith("VERSION"):
                changelog_lines.append(line[:38])
            if len(changelog_lines) >= 12:
                break
        del cl_raw
        gc.collect()
    except:
        pass

    if disp:
        disp.clear(BLACK)
        disp.fill_rectangle(0, 0, 320, 20, CYAN)
        disp.draw_text8x8(8, 6, "Update Available!", BLACK)
        ver_str = ("v" + local_ver + " -> v" + server_ver)[:28]
        disp.draw_text8x8(10, 30, ver_str, YELLOW)
        y = 50
        for cl in changelog_lines[:7]:
            if cl:
                disp.draw_text8x8(10, y, cl[:38], WHITE)
                y += 18

    choice = _prompt_choice(disp)

    if choice != "yes":
        print("Update skipped.")
        _show(disp, "Update skipped", color=GREY)
        time.sleep(1)
        return False

    print("Updating", len(files), "files...")
    for i, f in enumerate(files):
        _show(disp, "Updating...", "v" + local_ver + " -> v" + server_ver, color=CYAN)
        _progress(disp, f, i, len(files))
        if not download_file(BASE_URL + f, f):
            _show(disp, "Update failed!", f, color=RED)
            time.sleep(2)
            return False

    save_local_version(server_ver)

    # Save changelog so it shows once on next boot
    try:
        with open("pending_log.txt", "w") as f:
            f.write("=== v" + server_ver + " ===\n")
            for line in changelog_lines:
                if line:
                    f.write(line + "\n")
    except:
        pass

    _show(disp, "Update complete!", "v" + server_ver + " installed", "Rebooting...", color=GREEN)
    print("Update complete. Rebooting...")
    time.sleep(2)
    machine.reset()

# ================= PENDING LOG =================
def show_pending_log(disp=None):
    """
    Call on boot. If a pending_log.txt exists, show it once on screen,
    append it to changelog_history.txt, then delete it.
    """
    if "pending_log.txt" not in os.listdir():
        return

    try:
        with open("pending_log.txt", "r") as f:
            lines = f.read().splitlines()
    except:
        return

    # Append to history file
    try:
        with open("changelog_history.txt", "a") as f:
            f.write("\n")
            for line in lines:
                f.write(line + "\n")
    except:
        pass

    # Show on screen
    if disp:
        disp.clear(BLACK)
        disp.fill_rectangle(0, 0, 320, 20, CYAN)
        disp.draw_text8x8(8, 6, "What's New!", BLACK)
        y = 30
        for line in lines[:12]:
            if line:
                disp.draw_text8x8(8, y, line[:38], WHITE if not line.startswith("===") else YELLOW)
                y += 16
        disp.draw_text8x8(8, 220, "Select = OK", GREY)
        # wait for select or timeout
        deadline = time.time() + 30
        while time.time() < deadline:
            if _select_pressed():
                break
            time.sleep(0.05)
    else:
        print("Changelog:")
        for line in lines:
            print(" ", line)

    # Delete pending file
    try:
        os.remove("pending_log.txt")
    except:
        pass

# ================= PUBLIC API =================
def run_updater(disp=None):
    show_pending_log(disp)
    check_for_update(disp)
