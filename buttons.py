# button_module.py
import time
from machine import Pin

right = Pin(19, Pin.IN, Pin.PULL_UP)
left = Pin(17, Pin.IN, Pin.PULL_UP)
select = Pin(26, Pin.IN, Pin.PULL_UP)
alt_b = Pin(18, Pin.IN, Pin.PULL_UP)
down = Pin(4, Pin.IN, Pin.PULL_UP)
up = Pin(16, Pin.IN, Pin.PULL_UP)


def _wait_for_release(pin):
    while pin.value() == 0:
        time.sleep(0.01)
    time.sleep(0.05)  # debounce


def button_input():
    if right.value() == 0:
        print("right")
        _wait_for_release(right)
        return "right"

    elif left.value() == 0:
        print("left")
        _wait_for_release(left)
        return "left"

    elif select.value() == 0:
        print("select")
        _wait_for_release(select)
        return "select"

    elif alt_b.value() == 0:
        print("alternate button")
        _wait_for_release(alt_b)
        return "alt"

    elif down.value() == 0:
        print("down")
        _wait_for_release(down)
        return "down"

    elif up.value() == 0:
        print("up")
        _wait_for_release(up)
        return "up"

    return None
 
