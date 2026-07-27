"""Battery voltage / percentage reading."""

import time
from machine import Pin, ADC

try:
    _batt_adc = ADC(Pin(35))
    _batt_adc.atten(ADC.ATTN_11DB)
except:
    _batt_adc = None


def read_battery_voltage(samples=20, delay_ms=2):
    """Quick averaged read - intentionally NOT a full 1-second blocking
    loop like a standalone script could get away with, since this runs
    inside the UI loop and can't freeze the display/input for a second
    every time it's called. samples*delay_ms stays small (~40ms)."""
    if not _batt_adc:
        return None
    try:
        total = 0
        for _ in range(samples):
            total += _batt_adc.read()
            time.sleep_ms(delay_ms)
        average_raw = total / samples
        adc_voltage = (average_raw / 4095) * 3.3
        return adc_voltage * 2  # 1M + 1M divider
    except:
        return None


def battery_percent():
    """Rough linear map of single-cell LiPo voltage to percentage.
    Not accurate near the bottom of the curve (real LiPo discharge
    isn't linear), but good enough for a glance in the status bar."""
    v = read_battery_voltage()
    if v is None:
        return None
    if v >= 4.2:
        return 100
    if v <= 3.3:
        return 0
    return round((v - 3.3) / (4.2 - 3.3) * 100)
