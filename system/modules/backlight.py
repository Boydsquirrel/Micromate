"""Backlight brightness control (PWM with a plain on/off Pin fallback)."""

from machine import Pin, PWM

_pwm_backlight = None
_backlight_pin = None


def init(brightness):
    """Set up the backlight hardware. Call once at boot with the
    starting brightness (0-100) from settings."""
    global _pwm_backlight, _backlight_pin
    try:
        _pwm = PWM(Pin(21))
        _pwm.freq(1000)
        _pwm.duty_u16(int((brightness / 100) * 65535))
        _pwm_backlight = _pwm
    except:
        try:
            _backlight_pin = Pin(21, Pin.OUT)
            _backlight_pin.value(1 if brightness > 0 else 0)
        except:
            _backlight_pin = None


def apply_brightness(brightness):
    try:
        if _pwm_backlight:
            _pwm_backlight.duty_u16(int((max(0, min(100, brightness)) / 100) * 65535))
        elif _backlight_pin:
            _backlight_pin.value(1 if brightness > 0 else 0)
    except:
        pass
