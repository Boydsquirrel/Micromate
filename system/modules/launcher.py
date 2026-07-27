"""
Runs and relaunches apps.

execute_app() actually calls an app's run(disp) - no flag writing, no
reset. It's meant to be used either right after a fast-boot reset (the
launch flag already told us what to run), or directly by launch_app()
for apps that don't need a reset.

launch_app() is the normal entry point from the carousel: it decides
whether the app needs a clean-heap reset first (via app_wants_reset)
and either resets into it or runs it in-place.
"""

import gc
import sys
import time

import crashlog
import bootflags


def app_wants_reset(app_name):
    # for apps that need the extra ram from a reset
    try:
        import os
        return "reset.flag" in os.listdir("apps/" + app_name)
    except:
        return False


def execute_app(app_name, disp, bg_color=0x0000, text_color=0xFFFF):
    try:
        try:
            disp.fill_rectangle(0, 0, 320, 240, bg_color)
        except:
            pass

        gc.collect()

        module_name = "apps." + app_name + ".main"

        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
        except:
            pass

        module = __import__(module_name, None, None, ["run"])

        if hasattr(module, "run"):
            module.run(disp)
        else:
            raise Exception("no run() in app")

    except Exception as e:
        print("App crashed:", app_name)
        sys.print_exception(e)

        crashlog.log_crash(app_name, e)

        try:
            STATUS_H = 28
            disp.fill_rectangle(0, STATUS_H + 2, 320, 240 - (STATUS_H + 2), bg_color)
            disp.draw_text8x8(10, 100, "App crashed", text_color)
            disp.draw_text8x8(10, 120, app_name[:20], 0xF800)
            disp.draw_text8x8(10, 140, str(e)[:38], text_color)
        except:
            pass

        time.sleep(2)


def launch_app(app, disp, draw_status_bar):
    if app_wants_reset(app.name):
        bootflags.write_launch_target_and_reset(app.name)
        # machine.reset() does not return - if we ever get here, the
        # reset itself failed (see write_launch_target_and_reset's
        # fallback).
        print("launch_app: reset failed, app not launched:", app.name)
    else:
        execute_app(app.name, disp)
        draw_status_bar()
