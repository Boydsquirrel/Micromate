# button_module.py
import time
from machine import Pin

right = Pin(17, Pin.IN, Pin.PULL_UP)
left = Pin(19, Pin.IN, Pin.PULL_UP)
select = Pin(18, Pin.IN, Pin.PULL_UP)
alt_b = Pin(26, Pin.IN, Pin.PULL_UP)
down = Pin(4, Pin.IN, Pin.PULL_UP)
up = Pin(16, Pin.IN, Pin.PULL_UP)

def button_input():
    button_pressed = 0
    if right.value() == 0:  
        print("right")
        button_pressed = 1
        while right.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif left.value() == 0:
        print("left")
        button_pressed = 2
        while left.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif select.value() == 0:
        print("select")
        button_pressed = 3
        while select.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif alt_b.value() == 0:
        print("alternate button")
        button_pressed = 4
        while alt_b.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)
    elif down.value() == 0:
        print("down")
        button_pressed = 4
        while down.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)
    elif up.value() == 0:
        print("up")
        button_pressed = 4
        while up.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)
    return button_pressed

