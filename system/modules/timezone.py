"""
Timezone / DST helpers.

ntptime.settime() sets the RTC to UTC. If the weather app has a manual
location saved (see apps/settings), we use that location's country to
pick the right standard UTC offset + DST rule. If only auto-detect (IP
geolocation) is in use, there's no reliable country to key off of, so
we fall back to the old hardcoded EU (CET/CEST) assumption - same
behaviour as before, including the summer drift.
"""

import utime
import json

_LOCATION_FILE = "/apps/weather/location.json"

UTC_OFFSET_STANDARD = 1  # CET fallback, hours ahead of UTC


def _load_saved_location():
    try:
        with open(_LOCATION_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def _last_sunday(year, month):
    days_in_month = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = days_in_month[month - 1]
    while True:
        try:
            wd = utime.localtime(utime.mktime((year, month, day, 0, 0, 0, 0, 0)))[6]
        except:
            return day
        if wd == 6:  # Sunday (weekday 0=Monday .. 6=Sunday)
            return day
        day -= 1


def _nth_weekday_of_month(year, month, weekday, n):
    count = 0
    for day in range(1, 32):
        try:
            wd = utime.localtime(utime.mktime((year, month, day, 0, 0, 0, 0, 0)))[6]
        except:
            return None
        if wd == weekday:
            count += 1
            if count == n:
                return day
    return None


def _is_eu_dst(utc_t):
    year, month, day, hour = utc_t[0], utc_t[1], utc_t[2], utc_t[3]
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    if month == 3:
        dst_start_day = _last_sunday(year, 3)
        return (day > dst_start_day) or (day == dst_start_day and hour >= 1)
    if month == 10:
        dst_end_day = _last_sunday(year, 10)
        return (day < dst_end_day) or (day == dst_end_day and hour < 1)
    return False


def _is_us_dst(utc_t):
    # Approximate: 2nd Sunday March 07:00 UTC (2am EST) to
    # 1st Sunday November 06:00 UTC (2am EDT). Exact for US Eastern;
    # off by up to an hour on transition day itself for other US zones.
    year, month, day, hour = utc_t[0], utc_t[1], utc_t[2], utc_t[3]
    if month < 3 or month > 11:
        return False
    if 3 < month < 11:
        return True
    if month == 3:
        start_day = _nth_weekday_of_month(year, 3, 6, 2)
        return (day > start_day) or (day == start_day and hour >= 7)
    if month == 11:
        end_day = _nth_weekday_of_month(year, 11, 6, 1)
        return (day < end_day) or (day == end_day and hour < 6)
    return False


# Country code -> (standard UTC offset, dst rule). Not exhaustive, and
# multi-timezone countries (US, CA, RU, AU, BR, ...) are approximated
# with one representative offset. Add more entries here as needed.
_TZ_TABLE = {
    "NL": (1, "eu"), "DE": (1, "eu"), "FR": (1, "eu"), "BE": (1, "eu"),
    "ES": (1, "eu"), "IT": (1, "eu"), "AT": (1, "eu"), "CH": (1, "eu"),
    "PL": (1, "eu"), "SE": (1, "eu"), "DK": (1, "eu"), "NO": (1, "eu"),
    "PT": (0, "eu"), "IE": (0, "eu"), "GB": (0, "eu"),
    "FI": (2, "eu"), "GR": (2, "eu"), "RO": (2, "eu"), "BG": (2, "eu"),
    "US": (-5, "us"), "CA": (-5, "us"),
    "JP": (9, "none"), "CN": (8, "none"), "IN": (5.5, "none"),
    "AU": (10, "none"),
}


def _dst_offset_for_country(cc, utc_t):
    """Returns (standard_offset, dst_add) for a known country code,
    or None if the country isn't in the table (caller should fall back)."""
    entry = _TZ_TABLE.get(cc)
    if not entry:
        return None
    std_offset, rule = entry
    if rule == "eu":
        return std_offset, (1 if _is_eu_dst(utc_t) else 0)
    if rule == "us":
        return std_offset, (1 if _is_us_dst(utc_t) else 0)
    return std_offset, 0


def get_local_time():
    try:
        utc_t = utime.localtime()

        loc = _load_saved_location()
        if loc and loc.get("manual") and loc.get("cc"):
            result = _dst_offset_for_country(loc["cc"], utc_t)
            if result is not None:
                std_offset, dst_add = result
                offset_hours = std_offset + dst_add
                return utime.localtime(utime.mktime(utc_t) + int(offset_hours * 3600))
            # Manual location saved, but country not in our table -
            # fall through to the EU fallback below rather than
            # guessing further.

        # No manual location (auto-detect) or unknown country: fall
        # back to the old hardcoded EU assumption.
        offset_hours = UTC_OFFSET_STANDARD + (1 if _is_eu_dst(utc_t) else 0)
        return utime.localtime(utime.mktime(utc_t) + offset_hours * 3600)
    except:
        return utime.localtime()
