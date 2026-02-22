import time
import gc
from machine import Pin

# ===== BUTTON SETUP (match system) =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)
button2 = Pin(19, Pin.IN, Pin.PULL_UP)
button3 = Pin(18, Pin.IN, Pin.PULL_UP)
button4 = Pin(4, Pin.IN, Pin.PULL_UP)

_last_states = [1, 1, 1, 1]

def button_input():
    global _last_states
    pins = [button1, button2, button3, button4]

    for i in range(4):
        state = pins[i].value()
        if state == 0 and _last_states[i] == 1:
            _last_states[i] = 0
            return i + 1
        _last_states[i] = state

    return 0


# ===== REQUIRED ENTRY POINT =====
def run(disp):
    gc.collect()

    running = True

    # ---- your setup code here ----


    while running:

        btn = button_input()

        # Button 1 = exit app (system convention)
        if btn == 1:
            running = False

        # ---- your update logic here ----


        # ---- your drawing code here ----


        time.sleep(0.01)  # small delay to prevent CPU maxing

    # Clean exit back to home
    gc.collect()
    return
