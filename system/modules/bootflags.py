"""
Handles the launch-flag file used to pass a target app name across a
machine.reset(), so an app can get a clean heap by starting from a
fresh boot instead of running inside the carousel's memory space.
"""

import os
import machine

LAUNCH_FLAG_FILE = "/launch.flag"
CAROUSEL_TARGET = "CAROUSEL"


def read_and_clear_launch_target():
    try:
        with open(LAUNCH_FLAG_FILE, "r") as f:
            target = f.read().strip()
        os.remove(LAUNCH_FLAG_FILE)
        return target if target else None
    except:
        return None


def write_launch_target_and_reset(target):
    try:
        with open(LAUNCH_FLAG_FILE, "w") as f:
            f.write(target)
    except Exception as e:
        print("Failed to write launch flag, staying put:", e)
        return
    machine.reset()
