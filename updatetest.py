import time
import os

VERSION_FILE = "version.txt"

def get_local_version():
    if VERSION_FILE not in os.listdir():
        return "0.0"
    with open(VERSION_FILE, "r") as f:
        return f.read().strip()

def main():
    ver = get_local_version()
    print("=== Update Test Script Running ===")
    print("Version installed:", ver)
    while True:
        print("Running version:", ver)
        time.sleep(1)

main()
