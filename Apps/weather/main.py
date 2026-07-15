import time
import gc
import urequests
from machine import Pin

# ===== BUTTONS =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)
button2 = Pin(19, Pin.IN, Pin.PULL_UP)
button3 = Pin(18, Pin.IN, Pin.PULL_UP)
button4 = Pin(16,  Pin.IN, Pin.PULL_UP)

_last_states = [1, 1, 1, 1]

def button_input():
    global _last_states
    pins = [button1, button2, button3, button4]
    for i in range(4):
        s = pins[i].value()
        if s == 0 and _last_states[i] == 1:
            _last_states[i] = 0
            return i + 1
        _last_states[i] = s
    return 0

# ===== COLOURS =====
WHITE  = 0xFFFF
BLACK  = 0x0000
CYAN   = 0x07FF
YELLOW = 0xFFE0
RED    = 0xF800
GREEN  = 0x07E0
GREY   = 0x4208
BLUE   = 0x001F
DKGREY = 0x1082

API_KEY = "" #your API key here

VIEW_CURRENT  = 0
VIEW_FORECAST = 1
VIEW_DETAIL   = 2
VIEW_SETTINGS = 3

# ===== SAVED LOCATION =====
# Persisted to /apps/weather/location.json
# Format: {"city": "Rotterdam", "cc": "NL", "lat": 51.9225, "lon": 4.4792, "manual": true}

_LOCATION_FILE = "/apps/weather/location.json"

def _load_saved_location():
    try:
        import ujson
        with open(_LOCATION_FILE, "r") as f:
            return ujson.load(f)
    except:
        return None

def _save_location(city, cc, lat, lon):
    try:
        import ujson
        d = {"city": city, "cc": cc, "lat": lat, "lon": lon, "manual": True}
        with open(_LOCATION_FILE, "w") as f:
            ujson.dump(d, f)
        return True
    except Exception as e:
        print("save_location error:", e)
        return False

def _clear_saved_location():
    try:
        import uos
        uos.remove(_LOCATION_FILE)
    except:
        pass

# ===== ICON SYSTEM =====
ICON_MAP = {
    "Clear":         "sun",
    "Clouds":        "cloud",
    "Rain":          "rain",
    "Drizzle":       "rain",
    "Snow":          "snow",
    "Thunderstorm":  "thunder",
    "Mist":          "cloud",
    "Fog":           "cloud",
    "Haze":          "cloud",
    "Smoke":         "cloud",
    "Dust":          "cloud",
    "Sand":          "cloud",
    "Ash":           "cloud",
    "Squall":        "wind",
    "Tornado":       "wind",
}

ICON_FALLBACK = {
    "sun":     "SUN",
    "cloud":   "CLDS",
    "rain":    "RAIN",
    "snow":    "SNOW",
    "thunder": "THDR",
    "wind":    "WIND",
}

def _icon_name(desc):
    return ICON_MAP.get(desc, "clouds")

def draw_icon(disp, x, y, desc, size=32):
    name  = _icon_name(desc)
    fpath = "/apps/weather/icons/" + name + "_" + str(size) + ".raw"
    try:
        with open(fpath, "rb") as f:
            buf = f.read(size * size * 2)
        disp.block(x, y, x + size - 1, y + size - 1, buf)
    except:
        label = ICON_FALLBACK.get(name, desc[:4])
        fc = YELLOW
        if name == "rain":    fc = CYAN
        if name == "snow":    fc = WHITE
        if name == "thunder": fc = RED
        if name == "wind":    fc = GREEN
        txt(disp, x, y + (size // 2) - 4, label, fc)

# ===== DRAW HELPERS =====
def txt(disp, x, y, s, c):
    disp.draw_text8x8(x, y, str(s), c)

def msg(disp, s, c=WHITE):
    disp.clear(BLACK)
    txt(disp, 10, 112, s, c)

def hline(disp, x, y, w, c):
    disp.fill_rectangle(x, y, w, 1, c)

def vline(disp, x, y, h, c):
    disp.fill_rectangle(x, y, 1, h, c)

# ===== WIFI =====

def connect_wifi(disp):
    """
    Connect to WiFi using wifi.wifi_manager(disp):
      - Tries auto-connect against saved networks first (networks.txt).
      - If that fails, opens the interactive network picker so the user
        can select and enter a password - exactly like the rest of the OS.
    Returns True if connected, False if it still failed after all that.
    """
    import network
    import wifi

    wlan = network.WLAN(network.STA_IF)

    if wlan.isconnected():
        print("WiFi: already connected")
        return True

    wifi.wifi_manager(disp)

    connected = wlan.isconnected()
    if not connected:
        print("WiFi: not connected after wifi_manager")
    return connected

# ===== SCREENS =====

def screen_current(disp, city, cc, w):
    temp  = w["main"]["temp"]
    feels = w["main"]["feels_like"]
    hum   = w["main"]["humidity"]
    desc  = w["weather"][0]["main"]
    disp.clear(BLACK)
    txt(disp, 10, 5,  "== Current Weather ==", CYAN)
    txt(disp, 10, 25, city + ", " + cc, WHITE)
    draw_icon(disp, 276, 5, desc, 32)
    txt(disp, 10, 50,  desc, YELLOW)
    txt(disp, 10, 70,  "Temp:  " + str(int(temp)) + "C", WHITE)
    txt(disp, 10, 90,  "Feels: " + str(int(feels)) + "C", WHITE)
    txt(disp, 10, 110, "Humid: " + str(hum) + "%", WHITE)
    txt(disp, 0, 225,  "B1=Exit B2=Forecast B3=Settings B4=Reload", GREY)

def screen_forecast(disp, days, sel):
    disp.clear(BLACK)
    txt(disp, 10, 2, "=== 5-Day Forecast ===", CYAN)
    for i in range(len(days)):
        d = days[i]
        y = 20 + i * 42
        if i == sel:
            disp.fill_rectangle(0, y - 1, 320, 40, DKGREY)
        c = YELLOW if i == sel else WHITE
        draw_icon(disp, 282, y + 4, d["desc"], 32)
        txt(disp, 8, y,      d["label"], c)
        txt(disp, 8, y + 16,
            d["desc"] + " " + str(int(d["tmin"])) + "-" + str(int(d["tmax"])) + "C", c)
    txt(disp, 0, 225, "B1=Back B2=Scroll B3=Open B4=Reload", GREY)

def _bar_colour(t):
    if t < 5:  return BLUE
    if t < 15: return CYAN
    if t < 25: return YELLOW
    return RED

def screen_detail(disp, label, entries):
    try:
        _screen_detail_inner(disp, label, entries)
    except Exception as e:
        disp.clear(BLACK)
        txt(disp, 6, 3,  "Detail crashed:", RED)
        err = str(e)
        txt(disp, 6, 30, err[:38], YELLOW)
        if len(err) > 38:
            txt(disp, 6, 50, err[38:76], YELLOW)
        txt(disp, 0, 225, "B1=Back", GREY)
        print("screen_detail error:", e)

def _screen_detail_inner(disp, label, entries):
    disp.clear(BLACK)
    txt(disp, 6, 3, "Detail: " + label, CYAN)

    if not entries:
        txt(disp, 10, 112, "No data", RED)
        txt(disp, 0, 225, "B1=Back", GREY)
        return

    GX = 34
    GY = 22
    GW = 282
    GH = 105

    temps = []
    for e in entries:
        temps.append(e["temp"])

    tmin = min(temps)
    tmax = max(temps)
    rng  = (tmax - tmin) if (tmax - tmin) > 0.5 else 1.0

    n    = len(entries)
    slot = GW // n
    bw   = max(4, slot - 3)

    hline(disp, GX,     GY + GH, GW, GREY)
    vline(disp, GX - 1, GY,      GH, GREY)

    txt(disp, 0, GY,           str(int(tmax)) + "C", GREY)
    txt(disp, 0, GY + GH - 8,  str(int(tmin)) + "C", GREY)

    for i in range(n):
        e  = entries[i]
        bh = int(((e["temp"] - tmin) / rng) * (GH - 6)) + 6
        x  = GX + i * slot + 1
        by = GY + GH - bh
        disp.fill_rectangle(x, by, bw, bh, _bar_colour(e["temp"]))
        txt(disp, x, GY + GH + 2, e["hour"][:2], GREY)

    SY = GY + GH + 16

    if n <= 4:
        picks = list(range(n))
    else:
        step  = max(1, n // 4)
        picks = [i * step for i in range(4)]

    for j in range(len(picks)):
        e  = entries[picks[j]]
        sx = 4 + j * 78
        txt(disp, sx, SY,      e["hour"], YELLOW)
        draw_icon(disp, sx, SY + 14, e["desc"], 16)

    txt(disp, 0, 225, "B1=Back B2=Next B3=Prev", GREY)

# ===== SETTINGS SCREEN =====
# Flow:
#   1. Show current location + two options: Search / Auto-detect
#   2. If Search: open keyboard, type city name, search OWM geocoding API
#   3. Show list of up to 5 matching cities to pick from
#   4. Confirm saves to file; Auto-detect clears the file

def _geocode_search(query):
    """Search OpenWeatherMap geocoding API. Returns list of {name, cc, lat, lon, display}"""
    try:
        url = ("http://api.openweathermap.org/geo/1.0/direct"
               "?q=" + query +
               "&limit=5&appid=" + API_KEY)
        r   = urequests.get(url)
        raw = r.json()
        r.close()
        del r
        gc.collect()

        results = []
        for item in raw:
            name  = item.get("name", "")
            cc    = item.get("country", "")
            state = item.get("state", "")
            lat   = item.get("lat", 0.0)
            lon   = item.get("lon", 0.0)
            if state:
                display = name + ", " + state + ", " + cc
            else:
                display = name + ", " + cc
            results.append({"name": name, "cc": cc, "lat": lat, "lon": lon, "display": display})
        return results
    except Exception as e:
        print("geocode_search error:", e)
        return []

def _draw_settings_main(disp, saved):
    disp.clear(BLACK)
    txt(disp, 10, 5,  "===== Settings =====", CYAN)
    txt(disp, 10, 25, "Location:", YELLOW)

    if saved and saved.get("manual"):
        city = saved.get("city", "Unknown")
        cc   = saved.get("cc", "")
        txt(disp, 10, 45, city + ", " + cc, WHITE)
        txt(disp, 10, 60, "(manual)", GREY)
    else:
        txt(disp, 10, 45, "Auto-detect", WHITE)

    # Menu options
    disp.fill_rectangle(0, 90, 320, 18, DKGREY)
    txt(disp, 10, 92,  "B2: Search for a city", WHITE)
    txt(disp, 10, 115, "B3: Use auto-detect", WHITE)
    txt(disp, 0,  225, "B1=Back", GREY)

def _draw_results(disp, results, sel):
    disp.clear(BLACK)
    txt(disp, 10, 2, "Select city:", CYAN)
    if not results:
        txt(disp, 10, 60, "No results found.", RED)
        txt(disp, 10, 80, "Try a different name.", GREY)
        txt(disp, 0, 225, "B1=Back", GREY)
        return
    for i, r in enumerate(results):
        y = 20 + i * 38
        if i == sel:
            disp.fill_rectangle(0, y - 2, 320, 36, DKGREY)
        c = YELLOW if i == sel else WHITE
        # Truncate display to fit screen (38 chars at 8px = 304px)
        d = r["display"]
        if len(d) > 37: d = d[:34] + "..."
        txt(disp, 8, y,      d, c)
        coord = str(round(r["lat"], 2)) + "," + str(round(r["lon"], 2))
        txt(disp, 8, y + 16, coord, GREY)
    txt(disp, 0, 225, "B1=Back B2=Down B3=Confirm", GREY)

def screen_settings(disp):
    """
    Run the settings screen. Returns (city, cc, lat, lon) if location was
    changed, or None if the user just backed out without changing anything.
    Returns ("AUTO", "", 0, 0) if auto-detect was chosen.
    """
    saved = _load_saved_location()
    _draw_settings_main(disp, saved)

    # --- Main settings menu loop ---
    while True:
        btn = button_input()
        time.sleep(0.01)

        if btn == 1:
            # Back to weather
            return None

        elif btn == 2:
            # Search for a city
            result = _settings_search_flow(disp)
            if result is not None:
                return result
            # Came back from search without saving — redraw main menu
            saved = _load_saved_location()
            _draw_settings_main(disp, saved)

        elif btn == 3:
            # Switch to auto-detect: clear saved location
            _clear_saved_location()
            msg(disp, "Auto-detect enabled.", GREEN)
            time.sleep(1)
            return ("AUTO", "", 0, 0)

def _settings_search_flow(disp):
    """
    Open keyboard, search, pick result.
    Returns (city, cc, lat, lon) on success, None on cancel.
    """
    # Import keyboard app
    try:
        import keyboard
    except ImportError:
        msg(disp, "keyboard.py not found!", RED)
        time.sleep(2)
        return None

    # Get search query from keyboard
    query = keyboard.get_input(disp, prompt="Search city:")
    if query is None or query.strip() == "":
        return None

    query = query.strip()
    msg(disp, "Searching: " + query[:20] + "...", CYAN)
    gc.collect()

    results = _geocode_search(query)
    gc.collect()

    sel = 0
    _draw_results(disp, results, sel)

    if not results:
        # No results — wait for B1 to go back
        while True:
            btn = button_input()
            time.sleep(0.01)
            if btn == 1:
                return None
        return None

    # --- Results picker loop ---
    while True:
        btn = button_input()
        time.sleep(0.01)

        if btn == 1:
            # Back to search / settings
            return None

        elif btn == 2:
            # Scroll down
            sel = (sel + 1) % len(results)
            _draw_results(disp, results, sel)

        elif btn == 3:
            # Confirm selection
            r = results[sel]
            msg(disp, "Saving: " + r["name"][:20], CYAN)
            time.sleep(0.5)
            _save_location(r["name"], r["cc"], r["lat"], r["lon"])

            # Confirmation screen
            disp.clear(BLACK)
            txt(disp, 10, 5,  "Location saved!", GREEN)
            txt(disp, 10, 30, r["name"] + ", " + r["cc"], WHITE)
            coord = str(round(r["lat"], 2)) + ", " + str(round(r["lon"], 2))
            txt(disp, 10, 50, coord, GREY)
            txt(disp, 10, 80, "Reloading weather...", CYAN)
            time.sleep(1)

            return (r["name"], r["cc"], r["lat"], r["lon"])

# ===== LOCATION =====

def get_location():
    """
    Returns (lat, lon, city, cc).
    Priority: saved manual location > ipinfo.io > ip-api.com > fallback.
    """
    # Check for saved manual location first
    saved = _load_saved_location()
    if saved and saved.get("manual"):
        city = saved.get("city", "Unknown")
        cc   = saved.get("cc", "GB")
        lat  = saved.get("lat", 0.0)
        lon  = saved.get("lon", 0.0)
        print("Location: saved manual ->", city, cc, lat, lon)
        return lat, lon, city, cc

    # Try ipinfo.io
    try:
        r = urequests.get("http://ipinfo.io/json")
        d = r.json()
        r.close()
        del r
        loc = d.get("loc", "")
        if loc and "," in loc:
            lat, lon = loc.split(",")
            city = d.get("city", "Unknown")
            cc   = d.get("country", "GB")
            del d
            gc.collect()
            print("Location from ipinfo.io:", city, cc, lat, lon)
            return float(lat), float(lon), city, cc
        del d
    except Exception as e:
        print("ipinfo.io failed:", e)

    # Fallback: ip-api.com
    try:
        r    = urequests.get("http://ip-api.com/json/")
        d    = r.json()
        r.close()
        del r
        lat  = d.get("lat")
        lon  = d.get("lon")
        city = d.get("city", "Unknown")
        cc   = d.get("countryCode", "GB")
        del d
        gc.collect()
        print("Location from ip-api.com:", city, cc, lat, lon)
        return lat, lon, city, cc
    except Exception as e:
        print("ip-api.com failed:", e)

    return None, None, "Unknown", "GB"

# ===== DATA FETCHING =====

def fetch_current(city, cc):
    try:
        url = ("http://api.openweathermap.org/data/2.5/weather"
               "?q=" + city + "," + cc +
               "&appid=" + API_KEY + "&units=metric")
        r = urequests.get(url)
        d = r.json()
        r.close()
        del r
        gc.collect()
        return d
    except Exception as e:
        print("fetch_current error:", e)
        return None

def fetch_forecast(lat, lon):
    try:
        url = ("http://api.openweathermap.org/data/2.5/forecast"
               "?lat=" + str(lat) + "&lon=" + str(lon) +
               "&appid=" + API_KEY + "&units=metric&cnt=40")
        r   = urequests.get(url)
        raw = r.json()
        r.close()
        del r
        gc.collect()

        day_map   = {}
        day_order = []

        for e in raw["list"]:
            date = e["dt_txt"][:10]
            hour = e["dt_txt"][11:16]
            temp = e["main"]["temp"]
            desc = e["weather"][0]["main"]

            if date not in day_map:
                day_map[date] = {
                    "tmin": temp, "tmax": temp,
                    "desc": desc, "entries": []
                }
                day_order.append(date)

            dm = day_map[date]
            if temp < dm["tmin"]: dm["tmin"] = temp
            if temp > dm["tmax"]: dm["tmax"] = temp
            dm["entries"].append({"hour": hour, "temp": temp, "desc": desc})

        del raw
        gc.collect()

        DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

        def day_label(date_str):
            try:
                y = int(date_str[0:4])
                m = int(date_str[5:7])
                d = int(date_str[8:10])
                t = [0,3,2,5,0,3,5,1,4,6,2,4]
                if m < 3:
                    y -= 1
                dow = (y + y//4 - y//100 + y//400 + t[m-1] + d) % 7
                dow = (dow + 6) % 7
                return DOW[dow] + " " + date_str[5:]
            except:
                return date_str[5:]

        days = []
        for date in day_order[1:6]:
            dm = day_map[date]
            days.append({
                "label":   day_label(date),
                "desc":    dm["desc"],
                "tmin":    dm["tmin"],
                "tmax":    dm["tmax"],
                "entries": dm["entries"]
            })

        del day_map
        gc.collect()
        return days
    except:
        return None

# ===== ENTRY POINT =====

def run(disp):
    gc.collect()

    # --- Connect to WiFi before doing anything else ---
    if not connect_wifi(disp):
        # WiFi failed — show error and bail out rather than hanging on network calls
        msg(disp, "No WiFi. Exiting.", RED)
        time.sleep(2)
        return

    st = {
        "view": VIEW_CURRENT,
        "sel":  0,
        "lat":  None, "lon": None,
        "city": None, "cc":  None,
        "curr": None,
        "days": None,
    }

    def fetch_all(force=False):
        if st["lat"] is None or force:
            msg(disp, "Detecting location...")
            la, lo, ci, cc = get_location()

            if la is None:
                msg(disp, "Location failed", RED)
                time.sleep(1)
                ci, cc, la, lo = "Unknown", "GB", 0.0, 0.0

            st["lat"]  = la;  st["lon"] = lo
            st["city"] = ci;  st["cc"]  = cc

        msg(disp, "Fetching weather...")
        st["curr"] = fetch_current(st["city"], st["cc"])
        if not st["curr"] or "main" not in st["curr"]:
            msg(disp, "Weather failed", RED)
            time.sleep(1)
            st["curr"] = None

        msg(disp, "Fetching forecast...")
        st["days"] = fetch_forecast(st["lat"], st["lon"])
        if not st["days"]:
            msg(disp, "Forecast failed", RED)
            time.sleep(1)

        gc.collect()

    def render():
        v = st["view"]
        if v == VIEW_CURRENT:
            if st["curr"]:
                screen_current(disp, st["city"], st["cc"], st["curr"])
            else:
                msg(disp, "No weather data", RED)
        elif v == VIEW_FORECAST:
            if st["days"]:
                screen_forecast(disp, st["days"], st["sel"])
            else:
                msg(disp, "No forecast data", RED)
        elif v == VIEW_DETAIL:
            if st["days"] and st["sel"] < len(st["days"]):
                day = st["days"][st["sel"]]
                screen_detail(disp, day["label"], day["entries"])
            else:
                msg(disp, "No detail data", RED)

    fetch_all()
    render()

    while True:
        btn = button_input()

        if btn == 1:
            if st["view"] == VIEW_DETAIL:
                st["view"] = VIEW_FORECAST
                render()
            elif st["view"] == VIEW_FORECAST:
                st["view"] = VIEW_CURRENT
                render()
            elif st["view"] == VIEW_CURRENT:
                break

        elif btn == 2:
            if st["view"] == VIEW_CURRENT:
                st["view"] = VIEW_FORECAST
                render()
            elif st["view"] == VIEW_FORECAST and st["days"]:
                st["sel"] = (st["sel"] + 1) % len(st["days"])
                render()
            elif st["view"] == VIEW_DETAIL and st["days"]:
                if st["sel"] < len(st["days"]) - 1:
                    st["sel"] += 1
                    render()

        elif btn == 3:
            if st["view"] == VIEW_CURRENT:
                # Open settings
                result = screen_settings(disp)
                if result is not None:
                    if result[0] == "AUTO":
                        # Switched to auto-detect: clear cached location and reload
                        st["lat"] = None
                    else:
                        # New manual location
                        city, cc, lat, lon = result
                        st["city"] = city
                        st["cc"]   = cc
                        st["lat"]  = lat
                        st["lon"]  = lon
                    fetch_all(force=True)
                st["view"] = VIEW_CURRENT
                render()
            elif st["view"] == VIEW_FORECAST:
                st["view"] = VIEW_DETAIL
                render()
            elif st["view"] == VIEW_DETAIL and st["days"]:
                if st["sel"] > 0:
                    st["sel"] -= 1
                    render()

        elif btn == 4:
            fetch_all(force=True)
            render()

        time.sleep(0.01)

    gc.collect()
    return