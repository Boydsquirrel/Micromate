from machine import ADC, Pin, PWM
import time

try:
    _pwm = PWM(Pin(21))
    _pwm.freq(1000)
    _pwm.duty_u16(int(0.5 * 65535))   # 10% brightness
except:
    print("error chaning brightnesss")



# Same calibration as the launcher
adc = ADC(Pin(35))
adc.atten(ADC.ATTN_11DB)


def read_voltage(samples=20):
    total = 0
    for _ in range(samples):
        total += adc.read()
        time.sleep_ms(2)

    raw = total / samples
    adc_voltage = (raw / 4095) * 3.3
    return adc_voltage * 2


def battery_percent():
    v = read_voltage()

    if v >= 4.2:
        return 100
    if v <= 3.3:
        return 0

    return round((v - 3.3) / (4.2 - 3.3) * 100)


def run(disp):
    BG = 0x0000
    WHITE = 0xFFFF
    GREEN = 0x07E0
    RED = 0xF800
    YELLOW = 0xFFE0

    while True:
        pct = battery_percent()
        volts = read_voltage()

        if pct > 50:
            colour = GREEN
        elif pct > 20:
            colour = YELLOW
        else:
            colour = RED

        disp.clear(BG)

        disp.draw_text8x8(85, 30, "Battery", WHITE)

        # Large percentage
        disp.draw_text8x8(110, 90, "{}%".format(pct), colour)

        # Voltage
        disp.draw_text8x8(95, 150, "{:.2f} V".format(volts), WHITE)

        # Simple battery outline
        x = 90
        y = 185
        w = 140
        h = 20

        disp.draw_rectangle(x, y, w, h, WHITE)
        disp.fill_rectangle(x + w, y + 6, 5, 8, WHITE)

        fill = int((w - 4) * pct / 100)
        disp.fill_rectangle(x + 2, y + 2, fill, h - 4, colour)

        time.sleep(1)
