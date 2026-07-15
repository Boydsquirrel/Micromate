# ─────────────────────────────────────────────────────────────────────────
#  editor.py  ──  MicroMate Text Editor  v1.0
#  Place at:  apps/editor/main.py      Entry: run(disp)
#
#  Features
#  ────────
#  • Scroll up/down through any file  (hold B1/B2 for fast scroll)
#  • Edit any line in-place           (keyboard module)
#  • Insert line below / above        • Duplicate line
#  • Delete line                      • Move line up / down
#  • 10-level undo                    • Find text  (navigate all hits)
#  • Go to line number                • Line-overflow indicator (›)
#  • Unsaved-changes marker (*)       • Save / Save As
#  • New file                         • Open file  (scrollable browser)
#  • Save-before-exit / open prompt
#
#  Controls  (main editing mode)
#  ──────────────────────────────
#  B1  UP      scroll cursor up   (hold = fast scroll)
#  B2  DOWN    scroll cursor down (hold = fast scroll)
#  B3  SELECT  edit current line
#  B4  MENU    open action menu
# ─────────────────────────────────────────────────────────────────────────

import gc
import os
import time
import keyboard
from machine import Pin


# ═════════════════════════════════════════════════════════════════════════
#  BUTTONS   B1=UP  B2=DOWN  B3=SELECT  B4=MENU/BACK
# ═════════════════════════════════════════════════════════════════════════
_b1 = Pin(17, Pin.IN, Pin.PULL_UP)
_b2 = Pin(19, Pin.IN, Pin.PULL_UP)
_b3 = Pin(18, Pin.IN, Pin.PULL_UP)
_b4 = Pin(16, Pin.IN, Pin.PULL_UP)

_bl = [1, 1, 1, 1]   # last seen pin levels
_hs = [0, 0, 0, 0]   # ticks when button first went low
_hr = [0, 0, 0, 0]   # ticks of last repeat fire

_HOLD_DELAY  = 450    # ms before repeat begins
_HOLD_REPEAT = 110    # ms between repeat events


def _poll():
    """Return 1-4 on button event, 0 otherwise.
    B1/B2 generate repeated events while held (smooth scrolling).
    B3/B4 fire once per press."""
    now  = time.ticks_ms()
    pins = (_b1, _b2, _b3, _b4)

    for i in range(2):                     # B1, B2 – hold-to-repeat
        v = pins[i].value()
        if v == 0:
            if _bl[i] == 1:                # fresh press
                _bl[i] = 0
                _hs[i]  = now
                _hr[i]  = now
                return i + 1
            if (time.ticks_diff(now, _hs[i]) >= _HOLD_DELAY and
                    time.ticks_diff(now, _hr[i]) >= _HOLD_REPEAT):
                _hr[i] = now
                return i + 1
        else:
            _bl[i] = 1

    for i in range(2, 4):                  # B3, B4 – single-fire
        v = pins[i].value()
        if v == 0 and _bl[i] == 1:
            _bl[i] = 0
            return i + 1
        if v == 1:
            _bl[i] = 1
    return 0


def _flush():
    """Sync button state after returning from keyboard / blocking prompt.
    If a button is still physically held, treat it as 'just pressed' so
    hold-repeat doesn't fire immediately; if released, mark it up."""
    now = time.ticks_ms()
    for i, p in enumerate((_b1, _b2, _b3, _b4)):
        v = p.value()
        _bl[i] = v
        if v == 0:          # still held: reset timers so repeat resets
            _hs[i] = now
            _hr[i] = now
        else:
            _hs[i] = 0
            _hr[i] = 0


# ═════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE  (RGB565)
# ═════════════════════════════════════════════════════════════════════════
C_BG     = 0x1082   # near-black background
C_HDR    = 0x000C   # deep-navy header bar
C_STAT   = 0x2104   # dark-grey status bar
C_HINT   = 0x0841   # darker-grey hint bar
C_SEL    = 0x0358   # blue  – selected line
C_TXT    = 0xC618   # light-grey body text
C_LNUM   = 0x4208   # dim-grey line numbers
C_LNSEL  = 0x07FF   # cyan  – active line number
C_BORDER = 0x2945   # column separator
C_MOD    = 0xFC00   # orange – unsaved indicator
C_SAVED  = 0x07E0   # green  – saved flash
C_OVER   = 0xFC60   # amber  – line-overflow arrow
C_FND    = 0x8400   # dark-gold – find-hit row
C_WHITE  = 0xFFFF
C_CYAN   = 0x07FF
C_YELLOW = 0xFFE0
C_GREEN  = 0x07E0
C_RED    = 0xF800
C_BLACK  = 0x0000
C_MBKG   = 0x10A3   # menu / overlay background
C_MSEL   = 0x0358   # menu selected item
C_MTXT   = 0xFFFF   # menu text
C_MDIM   = 0x8410   # dimmed text (hints, separators)
C_MSEP   = 0x4208   # menu separator lines


# ═════════════════════════════════════════════════════════════════════════
#  LAYOUT  (320 × 240 px)
# ═════════════════════════════════════════════════════════════════════════
_SW  = 320;  _SH  = 240   # screen

_HY  = 0;    _HH  = 16    # header bar
_TY  = 16;   _TH  = 193   # text area   →  193 ÷ 11 = 17 visible rows
_SY  = 209;  _SH2 = 15    # status bar
_NY  = 224;  _NHT = 16    # hint bar      (224 + 16 = 240 ✓)

_LH  = 11                  # text-row height (px)
_VIS = _TH // _LH          # 17 visible rows

_LNW = 32                  # line-number column width
_TX  = _LNW + 2            # text column x  = 34
_TC  = (_SW - _TX) // 8    # chars visible per row = 35

# Menu geometry
_MIH = 12    # item row height (px)
_MSH = 6     # separator height (px)
_MHH = 18    # title-block height (px)

# File browser
_BVS = 13    # visible rows in browser


# ═════════════════════════════════════════════════════════════════════════
#  APP STATE
# ═════════════════════════════════════════════════════════════════════════
_ST_EDIT   = 0
_ST_MENU   = 1
_ST_BROWSE = 2
_ST_FIND   = 3

_lines  = [""]
_fname  = "untitled.txt"
_mod    = False
_cur    = 0       # cursor line index
_scr    = 0       # first visible line (scroll offset)
_undo   = []
_MAXU   = 10

_state  = _ST_EDIT
_msel   = 0

_bfiles = []      # [(name, size), ...]
_bsel   = 0
_bscr   = 0

_fterm  = ""      # last search term
_fhits  = []      # list of matching line indices
_fpos   = 0       # current hit index


# ═════════════════════════════════════════════════════════════════════════
#  MENU DEFINITION
# ═════════════════════════════════════════════════════════════════════════
_MITEMS = [
    ("Edit Line",    "ed"),
    ("Insert Below", "ib"),
    ("Insert Above", "ia"),
    ("Duplicate",    "dup"),
    ("Delete Line",  "del"),
    ("Move Line Up", "mu"),
    ("Move Line Dn", "md"),
    None,
    ("Undo",         "undo"),
    None,
    ("Find...",      "find"),
    ("Go to Line",   "goto"),
    None,
    ("Save",         "save"),
    ("Save As...",   "sas"),
    ("New File",     "new"),
    ("Open File",    "open"),
    None,
    ("Exit",         "exit"),
]

_MNAV = sum(1 for x in _MITEMS if x is not None)
_MH   = _MHH + sum(_MIH if x else _MSH for x in _MITEMS) + 4


# ═════════════════════════════════════════════════════════════════════════
#  FILE I/O
# ═════════════════════════════════════════════════════════════════════════
def _load(path):
    global _lines, _fname, _mod, _cur, _scr, _undo
    try:
        with open(path, "r") as f:
            raw = f.read()
        _lines = raw.split("\n")
        if _lines and _lines[-1] == "":
            _lines.pop()
        if not _lines:
            _lines = [""]
    except OSError:
        _lines = [""]
    _fname = path.strip("/").split("/")[-1]
    _mod   = False
    _cur   = 0
    _scr   = 0
    _undo  = []


def _write(path=None):
    """Write current buffer. Returns True on success."""
    global _mod, _fname
    if path is None:
        path = "/" + _fname
    try:
        with open(path, "w") as f:
            f.write("\n".join(_lines) + "\n")
        _fname = path.lstrip("/").split("/")[-1]
        _mod   = False
        return True
    except OSError:
        return False


def _ls():
    """List text-editable files from /."""
    EXTS = ("txt", "py", "json", "log", "md", "cfg", "ini", "csv")
    out  = []
    try:
        for name in sorted(os.listdir("/")):
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext in EXTS:
                try:
                    sz = os.stat("/" + name)[6]
                except:
                    sz = 0
                out.append((name, sz))
    except:
        pass
    return out


# ═════════════════════════════════════════════════════════════════════════
#  UNDO
# ═════════════════════════════════════════════════════════════════════════
def _upush(op, idx, **kw):
    e = {"op": op, "i": idx}
    e.update(kw)
    _undo.append(e)
    if len(_undo) > _MAXU:
        _undo.pop(0)


def _upop():
    """Revert the last operation. Returns True if something was undone."""
    global _mod, _cur
    if not _undo:
        return False
    e      = _undo.pop()
    op, i  = e["op"], e["i"]
    if   op == "ed":  _lines[i] = e["o"]
    elif op == "ins": del _lines[i]
    elif op == "del": _lines.insert(i, e["t"])
    elif op == "dup":
        if i + 1 < len(_lines):
            del _lines[i + 1]
    elif op == "mu":     # line moved from i → i-1, undo: swap i-1 and i back
        if i > 0:
            _lines[i - 1], _lines[i] = _lines[i], _lines[i - 1]
    elif op == "md":     # line moved from i → i+1, undo: swap i and i+1 back
        if i < len(_lines) - 1:
            _lines[i], _lines[i + 1] = _lines[i + 1], _lines[i]
    _cur = max(0, min(i, len(_lines) - 1))
    _mod = True
    return True


# ═════════════════════════════════════════════════════════════════════════
#  CURSOR / SCROLL
# ═════════════════════════════════════════════════════════════════════════
def _clamp():
    global _cur
    _cur = max(0, min(_cur, len(_lines) - 1))


def _snap():
    """Scroll so the cursor is always visible."""
    global _scr
    _clamp()
    if _cur < _scr:
        _scr = _cur
    elif _cur >= _scr + _VIS:
        _scr = _cur - _VIS + 1
    if _scr < 0:
        _scr = 0


# ═════════════════════════════════════════════════════════════════════════
#  DRAW HELPERS
# ═════════════════════════════════════════════════════════════════════════
def _draw_header(d):
    d.fill_rectangle(0, _HY, _SW, _HH, C_HDR)
    nm = _fname if len(_fname) <= 22 else _fname[:19] + "..."
    if _mod:
        d.draw_text8x8(4,  _HY + 4, "*", C_MOD)
        d.draw_text8x8(12, _HY + 4, nm,  C_WHITE)
    else:
        d.draw_text8x8(4, _HY + 4, nm, C_WHITE)
    info = "{}/{}L".format(_cur + 1, len(_lines))
    d.draw_text8x8(_SW - len(info) * 8 - 4, _HY + 4, info, C_CYAN)


def _draw_row(d, li, row, sel, fnd):
    """Draw one text-area row for line index li at screen row row."""
    y  = _TY + row * _LH
    bg = C_SEL if sel else (C_FND if fnd else C_BG)
    d.fill_rectangle(0, y, _SW, _LH, bg)
    # Line number (capped at 999 to stay in 3-char column)
    d.draw_text8x8(1, y + 1, "{:3d}".format(min(li + 1, 999)),
                   C_LNSEL if sel else C_LNUM)
    # Column separator
    d.fill_rectangle(_LNW, y, 1, _LH, C_BORDER)
    # Text content
    if li < len(_lines) and _lines[li]:
        t   = _lines[li]
        col = C_WHITE if sel else C_TXT
        if len(t) <= _TC:
            d.draw_text8x8(_TX, y + 1, t, col)
        else:
            d.draw_text8x8(_TX, y + 1, t[:_TC - 1], col)
            d.draw_text8x8(_TX + (_TC - 1) * 8, y + 1, ">", C_OVER)


def _draw_textarea(d):
    d.fill_rectangle(0, _TY, _SW, _TH, C_BG)
    for row in range(_VIS):
        li = _scr + row
        if li >= len(_lines):
            # Past end: just draw separator stub
            d.fill_rectangle(_LNW, _TY + row * _LH, 1, _LH, C_BORDER)
            continue
        _draw_row(d, li, row, li == _cur,
                  _state == _ST_FIND and li in _fhits)


def _draw_status(d):
    d.fill_rectangle(0, _SY, _SW, _SH2, C_STAT)
    if _state == _ST_FIND and _fhits:
        pos = (_fhits.index(_cur) + 1) if _cur in _fhits else 0
        txt = "FIND:{} {} of {}".format(_fterm[:14], pos, len(_fhits))
    else:
        ll  = len(_lines[_cur]) if _cur < len(_lines) else 0
        tot = sum(len(x) for x in _lines)
        txt = "Ln:{} Chars:{} Total:{}B".format(_cur + 1, ll, tot)
    d.draw_text8x8(4, _SY + 3, txt[:38], C_TXT)


def _draw_hint(d):
    d.fill_rectangle(0, _NY, _SW, _NHT, C_HINT)
    if   _state == _ST_EDIT:   t = "UP/DN:scroll  SEL:edit  B4:menu"
    elif _state == _ST_MENU:   t = "UP/DN:select  SEL:run  B4:close"
    elif _state == _ST_BROWSE: t = "UP/DN:browse  SEL:open  B4:cancel"
    elif _state == _ST_FIND:   t = "UP/DN:jump  SEL:edit  B4:exit find"
    else:                       t = ""
    if t:
        d.draw_text8x8(4, _NY + 4, t, C_MDIM)


def _full(d):
    """Full-screen redraw."""
    d.fill_rectangle(0, 0, _SW, _SH, C_BG)
    _draw_header(d)
    _draw_textarea(d)
    _draw_status(d)
    _draw_hint(d)


def _partial(d, old_li, new_li):
    """Fast partial redraw: only the two changed rows + header + status.
    Used for cursor movement when the scroll offset has not changed."""
    for li in (old_li, new_li):
        row = li - _scr
        if 0 <= row < _VIS:
            _draw_row(d, li, row, li == _cur,
                      _state == _ST_FIND and li in _fhits)
    _draw_header(d)
    _draw_status(d)


# ═════════════════════════════════════════════════════════════════════════
#  MENU
# ═════════════════════════════════════════════════════════════════════════
def _draw_menu(d):
    mw = 200
    mx = (_SW - mw) // 2           # 60
    my = max(2, (_SH - _MH) // 2)
    # Drop shadow
    d.fill_rectangle(mx + 3, my + 3, mw, _MH, C_BLACK)
    # Box
    d.fill_rectangle(mx, my, mw, _MH, C_MBKG)
    d.draw_rectangle(mx, my, mw, _MH, C_CYAN)
    # Title
    title = "  MENU  "
    d.draw_text8x8(mx + (mw - len(title) * 8) // 2, my + 4, title, C_CYAN)
    d.fill_rectangle(mx + 4, my + _MHH - 2, mw - 8, 1, C_MSEP)
    # Items
    y  = my + _MHH
    ni = 0
    for item in _MITEMS:
        if item is None:
            d.fill_rectangle(mx + 8, y + 3, mw - 16, 1, C_MSEP)
            y += _MSH
        else:
            label, _ = item
            sel      = (ni == _msel)
            if sel:
                d.fill_rectangle(mx + 2, y, mw - 4, _MIH - 1, C_MSEL)
                d.draw_text8x8(mx + 8,       y + 2, label, C_WHITE)
                d.draw_text8x8(mx + mw - 14, y + 2, ">",   C_CYAN)
            else:
                d.draw_text8x8(mx + 8, y + 2, label, C_MTXT)
            ni += 1
            y  += _MIH


def _maction():
    """Return the action string of the currently selected menu item."""
    ni = 0
    for item in _MITEMS:
        if item is None:
            continue
        if ni == _msel:
            return item[1]
        ni += 1
    return None


# ═════════════════════════════════════════════════════════════════════════
#  FILE BROWSER
# ═════════════════════════════════════════════════════════════════════════
def _draw_browser(d):
    d.fill_rectangle(0, 0, _SW, _SH, C_BLACK)
    # Header
    d.fill_rectangle(0, 0, _SW, 16, C_HDR)
    d.draw_text8x8(4, 4, "Open File", C_CYAN)
    n    = len(_bfiles)
    info = "{} file{}".format(n, "" if n == 1 else "s")
    d.draw_text8x8(_SW - len(info) * 8 - 4, 4, info, C_MDIM)

    if not _bfiles:
        d.draw_text8x8(10, 50, "No editable files in /", C_TXT)
        d.fill_rectangle(0, _NY, _SW, _NHT, C_HINT)
        d.draw_text8x8(4, _NY + 4, "B4:back", C_MDIM)
        return

    rh = 15
    for i in range(_BVS):
        fi = _bscr + i
        if fi >= n:
            break
        name, sz = _bfiles[fi]
        sel = (fi == _bsel)
        y   = 18 + i * rh
        if sel:
            d.fill_rectangle(2, y, _SW - 4, rh - 1, C_SEL)
        trunc = name if len(name) <= 30 else name[:27] + "..."
        d.draw_text8x8(8, y + 3, trunc, C_WHITE if sel else C_TXT)
        szs = "{}K".format(sz // 1024) if sz >= 1024 else "{}B".format(sz)
        d.draw_text8x8(_SW - len(szs) * 8 - 6, y + 3, szs, C_MDIM)

    # Scrollbar
    if n > _BVS:
        area = _SH - 34
        bh   = max(10, area * _BVS // n)
        by   = 17 + (area - bh) * _bscr // max(1, n - _BVS)
        d.fill_rectangle(_SW - 4, 17,  4, area, C_BORDER)
        d.fill_rectangle(_SW - 4, by,  4, bh,   C_CYAN)

    d.fill_rectangle(0, _NY, _SW, _NHT, C_HINT)
    d.draw_text8x8(4, _NY + 4, "UP/DN:select  SEL:open  B4:cancel", C_MDIM)


# ═════════════════════════════════════════════════════════════════════════
#  SAVE-PROMPT OVERLAY
# ═════════════════════════════════════════════════════════════════════════
def _save_prompt(d):
    pw, ph = 234, 68
    px = (_SW - pw) // 2
    py = (_SH - ph) // 2
    d.fill_rectangle(px + 3, py + 3, pw, ph, C_BLACK)
    d.fill_rectangle(px, py, pw, ph, C_MBKG)
    d.draw_rectangle(px, py, pw, ph, C_YELLOW)
    d.draw_text8x8(px + 8, py +  8, "Unsaved changes!", C_YELLOW)
    d.draw_text8x8(px + 8, py + 24, "B1:Save   B2:Discard", C_WHITE)
    d.draw_text8x8(px + 8, py + 40, "B4:Cancel (go back)", C_MDIM)


def _prompt_choice(d):
    """Block until user picks Save / Discard / Cancel.
    Returns 'save', 'discard', or 'cancel'."""
    _save_prompt(d)
    while True:
        b = _poll()
        if b in (1, 2, 4):
            _flush()
            if b == 1: return "save"
            if b == 2: return "discard"
            return "cancel"
        time.sleep(0.015)


# ═════════════════════════════════════════════════════════════════════════
#  EDITOR ACTIONS
# ═════════════════════════════════════════════════════════════════════════
def _act_edit(d):
    global _mod
    old = _lines[_cur]
    res = keyboard.get_input(
        d,
        prompt="Edit [{}/{}]:".format(_cur + 1, len(_lines)),
        prefill=old)
    _flush()
    if res is not None and res != old:
        _upush("ed", _cur, o=old)
        _lines[_cur] = res
        _mod = True
    _full(d)


def _act_ins_below(d):
    global _cur, _mod
    res = keyboard.get_input(
        d, prompt="Insert after line {}:".format(_cur + 1))
    _flush()
    if res is not None:
        ni = _cur + 1
        _lines.insert(ni, res)
        _upush("ins", ni)
        _cur = ni
        _mod = True
        _snap()
    _full(d)


def _act_ins_above(d):
    global _mod
    res = keyboard.get_input(
        d, prompt="Insert before line {}:".format(_cur + 1))
    _flush()
    if res is not None:
        _lines.insert(_cur, res)
        _upush("ins", _cur)
        _mod = True
        _snap()
    _full(d)


def _act_del(d):
    global _cur, _mod
    if len(_lines) == 1:
        # Can't delete the last line – clear it instead
        _upush("ed", 0, o=_lines[0])
        _lines[0] = ""
    else:
        _upush("del", _cur, t=_lines[_cur])
        del _lines[_cur]
        _cur = min(_cur, len(_lines) - 1)
    _mod = True
    _snap()
    _full(d)


def _act_dup(d):
    global _cur, _mod
    _lines.insert(_cur + 1, _lines[_cur])
    _upush("dup", _cur)
    _cur += 1
    _mod  = True
    _snap()
    _full(d)


def _act_mu(d):
    global _cur, _mod
    if _cur > 0:
        _upush("mu", _cur)
        _lines[_cur], _lines[_cur - 1] = _lines[_cur - 1], _lines[_cur]
        _cur -= 1
        _mod  = True
        _snap()
    _full(d)


def _act_md(d):
    global _cur, _mod
    if _cur < len(_lines) - 1:
        _upush("md", _cur)
        _lines[_cur], _lines[_cur + 1] = _lines[_cur + 1], _lines[_cur]
        _cur += 1
        _mod  = True
        _snap()
    _full(d)


def _act_save(d):
    ok = _write()
    _full(d)
    msg = "Saved: " + _fname if ok else "Save FAILED!"
    d.draw_text8x8(4, _SY + 3, msg[:38], C_SAVED if ok else C_RED)
    time.sleep(0.9)
    _draw_status(d)


def _act_sas(d):
    res = keyboard.get_input(d, prompt="Save as:", prefill=_fname)
    _flush()
    if res:
        if "." not in res:
            res += ".txt"
        path = ("/" + res) if not res.startswith("/") else res
        ok   = _write(path)
        _full(d)
        msg = "Saved: " + _fname if ok else "Save FAILED!"
        d.draw_text8x8(4, _SY + 3, msg[:38], C_SAVED if ok else C_RED)
        time.sleep(0.9)
        _draw_status(d)
    else:
        _full(d)


def _act_new(d):
    global _lines, _fname, _mod, _cur, _scr, _undo
    if _mod:
        ch = _prompt_choice(d)
        if ch == "save":
            _write()
        elif ch == "cancel":
            _full(d)
            return
    res = keyboard.get_input(d, prompt="New file name:", prefill="")
    _flush()
    if res:
        if "." not in res:
            res += ".txt"
        _lines = [""]
        _fname = res
        _mod   = False
        _cur   = 0
        _scr   = 0
        _undo  = []
    _full(d)


def _act_open(d):
    global _state, _bfiles, _bsel, _bscr
    _bfiles = _ls()
    _bsel   = 0
    _bscr   = 0
    _state  = _ST_BROWSE
    _draw_browser(d)


def _act_find(d):
    global _state, _fterm, _fhits, _fpos, _cur
    res = keyboard.get_input(d, prompt="Find text:", prefill=_fterm)
    _flush()
    if res is None:
        _full(d)
        return
    _fterm = res
    if _fterm:
        term   = _fterm.lower()
        _fhits[:] = [i for i, l in enumerate(_lines) if term in l.lower()]
        if _fhits:
            _fpos  = 0
            _cur   = _fhits[0]
            _snap()
            _state = _ST_FIND
        else:
            _full(d)
            d.draw_text8x8(4, _SY + 3,
                           ("Not found: " + _fterm)[:38], C_RED)
            time.sleep(1.0)
            _draw_status(d)
            return
    _full(d)


def _act_goto(d):
    global _cur
    res = keyboard.get_input(
        d, prompt="Go to line (1-{}):".format(len(_lines)))
    _flush()
    if res:
        try:
            n    = int(res.strip())
            _cur = max(0, min(n - 1, len(_lines) - 1))
            _snap()
        except ValueError:
            pass
    _full(d)


def _act_undo(d):
    if _upop():
        _snap()
        _full(d)
    else:
        _full(d)
        d.draw_text8x8(4, _SY + 3, "Nothing to undo.", C_MDIM)
        time.sleep(0.7)
        _draw_status(d)


# ═════════════════════════════════════════════════════════════════════════
#  ACTION DISPATCH
# ═════════════════════════════════════════════════════════════════════════
def _dispatch(d, act):
    """Execute a menu action. Returns True if the editor should quit."""
    if   act == "ed":   _act_edit(d)
    elif act == "ib":   _act_ins_below(d)
    elif act == "ia":   _act_ins_above(d)
    elif act == "dup":  _act_dup(d)
    elif act == "del":  _act_del(d)
    elif act == "mu":   _act_mu(d)
    elif act == "md":   _act_md(d)
    elif act == "undo": _act_undo(d)
    elif act == "find": _act_find(d)
    elif act == "goto": _act_goto(d)
    elif act == "save": _act_save(d)
    elif act == "sas":  _act_sas(d)
    elif act == "new":  _act_new(d)
    elif act == "open": _act_open(d)
    elif act == "exit":
        if _mod:
            ch = _prompt_choice(d)
            if ch == "save":
                _write()
                return True
            elif ch == "discard":
                return True
            else:        # cancel
                _full(d)
                return False
        return True
    return False


# ═════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═════════════════════════════════════════════════════════════════════════
def run(disp):
    global _lines, _fname, _mod, _cur, _scr, _undo
    global _state, _msel
    global _bfiles, _bsel, _bscr
    global _fterm, _fhits, _fpos

    # ── Reset all state ───────────────────────────────────────────────
    _lines  = [""]
    _fname  = "untitled.txt"
    _mod    = False
    _cur    = 0
    _scr    = 0
    _undo   = []
    _state  = _ST_EDIT
    _msel   = 0
    _bfiles = []
    _bsel   = 0
    _bscr   = 0
    _fterm  = ""
    _fhits  = []
    _fpos   = 0

    _flush()
    gc.collect()
    _full(disp)

    _gcn = 0

    while True:
        b = _poll()

        # ── EDIT STATE ────────────────────────────────────────────────
        if _state == _ST_EDIT:
            if b == 1:                     # UP
                if _cur > 0:
                    old     = _cur
                    old_scr = _scr
                    _cur   -= 1
                    _snap()
                    if _scr == old_scr:
                        _partial(disp, old, _cur)
                    else:
                        _full(disp)

            elif b == 2:                   # DOWN
                if _cur < len(_lines) - 1:
                    old     = _cur
                    old_scr = _scr
                    _cur   += 1
                    _snap()
                    if _scr == old_scr:
                        _partial(disp, old, _cur)
                    else:
                        _full(disp)

            elif b == 3:                   # SELECT → edit
                _act_edit(disp)

            elif b == 4:                   # MENU
                _state = _ST_MENU
                _msel  = 0
                _draw_menu(disp)

        # ── MENU STATE ────────────────────────────────────────────────
        elif _state == _ST_MENU:
            if b == 1:
                _msel = (_msel - 1) % _MNAV
                _draw_menu(disp)
            elif b == 2:
                _msel = (_msel + 1) % _MNAV
                _draw_menu(disp)
            elif b == 3:
                act    = _maction()
                _state = _ST_EDIT
                if _dispatch(disp, act):
                    return
            elif b == 4:
                _state = _ST_EDIT
                _full(disp)

        # ── FILE BROWSER STATE ────────────────────────────────────────
        elif _state == _ST_BROWSE:
            if b == 1:
                if _bsel > 0:
                    _bsel -= 1
                    if _bsel < _bscr:
                        _bscr = _bsel
                    _draw_browser(disp)
            elif b == 2:
                if _bsel < len(_bfiles) - 1:
                    _bsel += 1
                    if _bsel >= _bscr + _BVS:
                        _bscr = _bsel - _BVS + 1
                    _draw_browser(disp)
            elif b == 3:
                if _bfiles:
                    path    = "/" + _bfiles[_bsel][0]
                    do_open = True
                    if _mod:
                        ch = _prompt_choice(disp)
                        if ch == "save":
                            _write()
                        elif ch == "cancel":
                            do_open = False
                            _draw_browser(disp)
                    if do_open:
                        _load(path)
                        _state = _ST_EDIT
                        _full(disp)
            elif b == 4:
                _state = _ST_EDIT
                _full(disp)

        # ── FIND STATE ────────────────────────────────────────────────
        elif _state == _ST_FIND:
            if b == 1:                     # prev hit
                if _fhits:
                    _fpos = (_fpos - 1) % len(_fhits)
                    _cur  = _fhits[_fpos]
                    _snap()
                    _full(disp)
            elif b == 2:                   # next hit
                if _fhits:
                    _fpos = (_fpos + 1) % len(_fhits)
                    _cur  = _fhits[_fpos]
                    _snap()
                    _full(disp)
            elif b == 3:                   # edit matched line
                _act_edit(disp)
                # Rebuild hit list in case the edit changed a match
                term      = _fterm.lower()
                _fhits[:] = [i for i, l in enumerate(_lines)
                             if term in l.lower()]
                if not _fhits:
                    _state = _ST_EDIT
                elif _cur not in _fhits:
                    _fpos = 0
                    _cur  = _fhits[0]
                else:
                    _fpos = _fhits.index(_cur)
                _snap()
                _full(disp)
            elif b == 4:                   # exit find mode
                _state = _ST_EDIT
                _fhits[:] = []
                _full(disp)

        # ── PERIODIC GC ───────────────────────────────────────────────
        _gcn += 1
        if _gcn >= 80:
            gc.collect()
            _gcn = 0

        time.sleep(0.015)