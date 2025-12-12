# button_module.py
import time
from machine import Pin

button1 = Pin(17, Pin.IN, Pin.PULL_UP)
button2 = Pin(19, Pin.IN, Pin.PULL_UP)
button3 = Pin(18, Pin.IN, Pin.PULL_UP)
button4 = Pin(21, Pin.IN, Pin.PULL_UP)

def button_input():
    button_pressed = 0
    if button1.value() == 0:  
        print("Button 1 Pressed!")
        button_pressed = 1
        while button1.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif button2.value() == 0:
        print("Button 2 Pressed!")
        button_pressed = 2
        while button2.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif button3.value() == 0:
        print("Button 3 Pressed!")
        button_pressed = 3
        while button3.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)

    elif button4.value() == 0:
        print("Button 4 Pressed!")
        button_pressed = 4
        while button4.value() == 0:
            time.sleep(0.01)
        time.sleep(0.05)
    
    return button_pressed

