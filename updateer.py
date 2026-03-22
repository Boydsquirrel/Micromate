# updateer.py — display-aware memory-safe updater for Micromate
import network
import machine
import time
import os
import gc

# ================= CONFIG =================
VERSION_FILE = "version.txt"
BASE_URL     = "http://divine-cake-5679.boydsquirrel.workers.dev/"
UPDATE_JSON  = "http://divine-cake-5679.boydsquirrel.workers.dev/version.json"
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
from machine import Pin
_b3 = Pin(18, Pin.IN, Pin.PULL_UP)
_b4 = Pin(4,  Pin.IN, Pin.PULL_UP)
_ls  = [1, 1]

def _btn():
    global _ls
    pins = [_b3, _b4]
    for i in range(2):
        v = pins[i].value()
        if v == 0 and _ls[i] == 1:
            _ls[i] = 0
            _ls = [pins[j].value() for j in range(2)]
            return i + 1
        _ls[i] = v
    return 0

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

    _show(disp, "Checking for updates...", color=CYAN)

    try:
        import urequests
        r   = urequests.get(UPDATE_JSON, timeout=8)
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
    local_ver  = get_local_version()
    print("Local:", local_ver, "  Server:", server_ver)

    if ver(local_ver) >= ver(server_ver):
        print("Already up to date.")
        _show(disp, "Already up to date", "v" + local_ver, color=GREEN)
        time.sleep(1)
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
        for cl in changelog_lines[:9]:
            if cl:
                disp.draw_text8x8(10, y, cl[:38], WHITE)
                y += 18
        disp.draw_text8x8(10, 218, "B3=Install  B4=Skip", GREY)

        deadline = time.time() + 30
        choice   = None
        while time.time() < deadline:
            b = _btn()
            if b == 1: choice = "yes"; break
            if b == 2: choice = "no";  break
            time.sleep(0.05)
        if choice is None:
            choice = "no"
    else:
        try:
            c = input("Update available! Install now? y/n: ").strip().lower()
            choice = "yes" if c in ("y", "yes") else "no"
        except:
            choice = "no"

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
        disp.draw_text8x8(8, 220, "B3 = OK", GREY)
        # wait for B3 or timeout
        deadline = time.time() + 30
        while time.time() < deadline:
            if _btn() == 1:
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
