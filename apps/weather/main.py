import urequests
import time
import buttons

# ————— YOUR SETTINGS —————
API_KEY = "API KEY"
CITY    = "CITY"
COUNTRY = "COUNTRY"

WHITE  = 0xFFFF
BLACK  = 0x0000
CYAN   = 0x07FF
YELLOW = 0xFFE0

def fetch_weather():
    try:
        # construct OpenWeatherMap API URL
        url = (
            "http://api.openweathermap.org/data/2.5/weather?"
            "q={},{}&appid={}&units=metric"
        ).format(CITY, COUNTRY, API_KEY)
        
        resp = urequests.get(url)
        data = resp.json()
        resp.close()
        return data
    except Exception as e:
        print("Weather fetch error:", e)
        return None

def run(disp):
    disp.clear(BLACK)
    disp.draw_text8x8(60, 110, "Fetching weather...", WHITE)
    
    weather = fetch_weather()
    if not weather or "main" not in weather:
        disp.clear(BLACK)
        disp.draw_text8x8(40, 120, "Failed to load weather", WHITE)
        time.sleep(2)
        return
    
    # extract useful stuff
    temp  = weather["main"]["temp"]
    hum   = weather["main"]["humidity"]
    desc  = weather["weather"][0]["main"]
    
    # display
    disp.clear(BLACK)
    disp.draw_text8x8(10, 10, "Weather", CYAN)
    disp.draw_text8x8(10, 30, f"{CITY}, {COUNTRY}", WHITE)
    disp.draw_text8x8(10, 50, f"{desc}", YELLOW)
    disp.draw_text8x8(10, 70, f"Temp: {temp} C", WHITE)
    disp.draw_text8x8(10, 90, f"Humidity: {hum}%", WHITE)
    
    disp.draw_text8x8(10, 210, "Btn1 = Exit", WHITE)
    while True:
        if buttons.button_input() == 1:
            disp.clear(BLACK)
            return
        time.sleep(0.1)

