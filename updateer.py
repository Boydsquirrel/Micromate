import network, time, urequests, machine, os
from wifi import wifi_manager  # your WiFi code
import usocket as socket

VERSION_FILE = "version.txt"
UPDATE_JSON  = "https://raw.githubusercontent.com/Boydsquirrel/micromate/main/version.json"
BASE_URL     = "https://raw.githubusercontent.com/Boydsquirrel/micromate/main/"
UPDATE_LOG_URL = "https://raw.githubusercontent.com/Boydsquirrel/micromate/main/update.txt"
UPDATED_FILE = "updated.txt"
PREV_UPDATES_FILE = "previous_updates.txt"

# ===== Version helpers =====
def ver(v):
    return tuple(map(int, v.split(".")))

def get_local_version():
    if VERSION_FILE not in os.listdir():
        with open(VERSION_FILE, "w") as f:
            f.write("0.0")
        return "0.0"
    return open(VERSION_FILE).read().strip() or "0.0"

def save_local_version(v):
    with open(VERSION_FILE, "w") as f:
        f.write(v)

# ===== Download a file =====
def download_file(url, filename):
    print("Downloading:", filename)
    try:
        r = urequests.get(url, timeout=5)
        if r.status_code != 200:
            print("HTTP error:", r.status_code)
            r.close()
            return False
        tmp = filename + ".tmp"
        with open(tmp, "w") as f:
            f.write(r.text)
        os.rename(tmp, filename)
        r.close()
        print("Saved:", filename)
        return True
    except Exception as e:
        print("Failed:", e)
        return False

# ===== Check for updates =====
def check_for_update():
    print("Checking for updates…")
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("Connecting WiFi for update check…")
        wifi_manager()

    try:
        r = urequests.get(UPDATE_JSON, timeout=5)
        data = r.json()
        r.close()
    except Exception as e:
        print("Couldn't fetch version.json:", e)
        return False

    server_ver = str(data.get("version", "0.0"))
    files_list = data.get("files", ["main.py"])
    local_ver = get_local_version()
    print("Local:", local_ver, "Server:", server_ver)

    if ver(local_ver) >= ver(server_ver):
        print("Up to date.")
        return False

    print("New update found!")
    for file_name in files_list:
        if not download_file(BASE_URL + file_name, file_name):
            print("Update failed on:", file_name)
            return False

    # Flag update so we can fetch log later
    with open(UPDATED_FILE, "w") as f:
        f.write("1\n")

    save_local_version(server_ver)
    print("Update done. Rebooting…")
    time.sleep(1)
    machine.reset()
    return True

# ===== Run updater =====
def run_updater():
    print("Booting updater…")
    wifi_manager()
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        check_for_update()
        wlan.active(False)
    else:
        print("Skipping update, no WiFi.")

# ===== Post-boot update log fetch =====
def show_update_log():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)

    if UPDATED_FILE in os.listdir():
        with open(UPDATED_FILE, "r") as f:
            flag = f.read().strip()
        if flag == "1":
            # Ensure WiFi is connected
            if not wlan.isconnected():
                print("Reconnecting WiFi for update log…")
                wifi_manager()

            # Resolve GitHub host
            try:
                addr = socket.getaddrinfo("raw.githubusercontent.com", 443)[0][-1]
                print("GitHub resolved to:", addr)
            except Exception as e:
                print("DNS resolution failed:", e)
                return

            # Attempt to fetch update log with retries
            for attempt in range(3):
                try:
                    r = urequests.get(UPDATE_LOG_URL, timeout=10)
                    if r.status_code == 200:
                        update_log = r.text
                        print("\n=== UPDATE LOG ===")
                        print(update_log)
                        print("==================\n")
                        r.close()

                        # Append to previous_updates.txt
                        try:
                            with open(PREV_UPDATES_FILE, "a") as f:
                                f.write(f"--- Update fetched on {time.localtime()} ---\n")
                                f.write(update_log + "\n\n")
                        except Exception as e:
                            print("Failed to write to previous_updates.txt:", e)

                        # Reset flag
                        with open(UPDATED_FILE, "w") as f:
                            f.write("0\n")
                        break
                    else:
                        print("HTTP error fetching update log:", r.status_code)
                        r.close()
                except Exception as e:
                    print(f"Attempt {attempt+1} failed:", e)
                    time.sleep(2)
            else:
                print("Failed to fetch update log after 3 attempts.")

