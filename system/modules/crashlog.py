"""Simple crash logger used for app crashes and boot-time errors."""

import os
import sys
import utime


def log_crash(app_name, error):
    try:
        # prevent log getting too big
        try:
            if "crash.log" in os.listdir() and os.stat("crash.log")[6] > 5000:
                os.remove("crash.log")
        except:
            pass

        with open("crash.log", "a") as f:
            f.write("=== CRASH ===\n")
            f.write("App: " + str(app_name) + "\n")

            try:
                t = utime.localtime()
                f.write("Time: {:02d}:{:02d}:{:02d}\n".format(t[3], t[4], t[5]))
            except:
                pass

            f.write("Error: " + str(error) + "\n")
            f.write("Traceback:\n")
            sys.print_exception(error, f)
            f.write("\n\n")
    except:
        pass
