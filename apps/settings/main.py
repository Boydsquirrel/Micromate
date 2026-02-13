import os
import json
import time
import buttons
from machine import Pin, PWM

SETTINGS_PATH = "/system/settings.json"

# ===== LOAD / SAVE =====
def load_settings():
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except:
        return {"brightness": 100, "sleep": 0}

def save_settings(settings):
    try:
        if "system" not in os.listdir("/"):
            os.mkdir("/system")
    except:
        pass

    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)

# ===== BACKLIGHT =====
def make_backlight():
    try:
        pwm = PWM(Pin(21))
        pwm.freq(1000)
        return pwm
    except:
        return None

backlight = make_backlight()

def apply_brightness(value):
    if backlight:
        duty = int((value / 100) * 65535)
        backlight.duty_u16(duty)
    else:
        p = Pin(21, Pin.OUT)
        p.value(1 if value > 0 else 0)

# ===== UI =====
SLIDER_X = 60
SLIDER_Y1 = 110
SLIDER_Y2 = 170
SLIDER_W = 200
SLIDER_H = 10

KNOB_W = 12
KNOB_H = 22

TRACK_COLOR = 0xFFFF
BG_COLOR = 0x0000
KNOB_COLOR = 0xF800
TEXT_COLOR = 0xFFFF
SELECT_COLOR = 0x07E0

def draw_static_ui(disp, selected):
    disp.fill_rectangle(0, 0, 320, 240, BG_COLOR)

    disp.draw_text8x8(110, 20, "Settings", TEXT_COLOR)

    # Brightness
    color = SELECT_COLOR if selected == 0 else TEXT_COLOR
    disp.draw_text8x8(80, 70, "Brightness", color)
    disp.fill_rectangle(SLIDER_X, SLIDER_Y1, SLIDER_W, SLIDER_H, TRACK_COLOR)

    # Sleep timer
    color = SELECT_COLOR if selected == 1 else TEXT_COLOR
    disp.draw_text8x8(80, 140, "Auto Sleep (sec)", color)
    disp.fill_rectangle(SLIDER_X, SLIDER_Y2, SLIDER_W, SLIDER_H, TRACK_COLOR)

def draw_slider(disp, value, y, suffix=""):
    disp.fill_rectangle(SLIDER_X - 15, y - 20, SLIDER_W + 30, 60, BG_COLOR)
    disp.fill_rectangle(SLIDER_X, y, SLIDER_W, SLIDER_H, TRACK_COLOR)

    value = max(0, min(100, value))
    knob_x = SLIDER_X + int((value / 100) * SLIDER_W)
    knob_y = y - (KNOB_H // 2) + (SLIDER_H // 2)

    disp.fill_rectangle(
        knob_x - KNOB_W // 2,
        knob_y,
        KNOB_W,
        KNOB_H,
        KNOB_COLOR
    )

    disp.fill_rectangle(120, y + 25, 100, 12, BG_COLOR)
    disp.draw_text8x8(130, y + 25, str(value) + suffix, TEXT_COLOR)

# ===== MAIN =====
def run(disp):
    settings = load_settings()

    brightness = settings.get("brightness", 100)
    sleep_time = settings.get("sleep", 0)

    selected = 0  # 0=brightness, 1=sleep

    apply_brightness(brightness)
    draw_static_ui(disp, selected)

    draw_slider(disp, brightness, SLIDER_Y1, "%")
    draw_slider(disp, sleep_time, SLIDER_Y2, "")

    hold_counter = 0
    last_btn = None

    while True:
        btn = buttons.button_input()

        if btn == last_btn and btn in (1, 2):
            hold_counter += 1
        else:
            hold_counter = 0

        step = 1
        if hold_counter > 5:
            step = 3
        if hold_counter > 20:
            step = 6

        if btn == 1:  # left
            if selected == 0:
                brightness = max(0, brightness - step)
            else:
                sleep_time = max(0, sleep_time - step)

        elif btn == 2:  # right
            if selected == 0:
                brightness = min(100, brightness + step)
            else:
                sleep_time = min(300, sleep_time + step)

        elif btn == 3:  # save + exit
            settings["brightness"] = brightness
            settings["sleep"] = sleep_time
            save_settings(settings)
            return

        elif btn == 4:  # switch selection
            selected = (selected + 1) % 2
            draw_static_ui(disp, selected)

        draw_slider(disp, brightness, SLIDER_Y1, "%")
        draw_slider(disp, sleep_time, SLIDER_Y2, "")

        apply_brightness(brightness)

        last_btn = btn
        time.sleep(0.05)

