"""Draws the top status bar: day, battery %, wifi icon, clock."""

import network

import timezone
import battery

STATUS_H = 28
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_disp = None
_bg = 0x0000
_text_color = 0xFFFF

_last_drawn_minute = -1
_last_wifi_state = None


def init(disp, bg_color, text_color):
    """Call once, after the display object exists."""
    global _disp, _bg, _text_color
    _disp = disp
    _bg = bg_color
    _text_color = text_color


def draw_wifi_status(connected):
    global _last_wifi_state
    if connected == _last_wifi_state or _disp is None:
        return
    _last_wifi_state = connected
    x, y = 300, 5
    try:
        _disp.fill_rectangle(x, y, 15, 15, _bg)
        color = 0x07E0 if connected else 0xF800
        _disp.draw_line(x, y + 15, x + 4, y + 11, color)
        _disp.draw_line(x + 5, y + 15, x + 9, y + 9, color)
        _disp.draw_line(x + 10, y + 15, x + 14, y + 5, color)
    except:
        pass


def update_clock():
    global _last_drawn_minute
    if _disp is None:
        return
    try:
        t = timezone.get_local_time()
        if t[4] == _last_drawn_minute:
            return
        _last_drawn_minute = t[4]
        day_str = days[t[6]] if 0 <= t[6] < 7 else ""
        time_str = "{:02d}:{:02d}".format(t[3], t[4])
        _disp.fill_rectangle(5, 0, 195, STATUS_H, _bg)
        _disp.fill_rectangle(205, 0, 38, STATUS_H, _bg)  # battery area
        _disp.fill_rectangle(245, 0, 55, STATUS_H, _bg)
        _disp.draw_text8x8(5, 8, day_str, _text_color)

        pct = battery.battery_percent()
        if pct is not None:
            batt_str = "{:d}%".format(pct)
            batt_color = 0x07E0 if pct > 20 else 0xF800  # green, red if low
            _disp.draw_text8x8(207, 8, batt_str, batt_color)

        _disp.draw_text8x8(250, 8, time_str, _text_color)
    except:
        pass


def draw_status_bar():
    global _last_drawn_minute, _last_wifi_state
    _last_drawn_minute = -1
    _last_wifi_state = None
    if _disp is None:
        return
    try:
        _disp.fill_rectangle(0, 0, 320, STATUS_H, _bg)
    except:
        pass
    update_clock()
    draw_wifi_status(network.WLAN(network.STA_IF).isconnected())
