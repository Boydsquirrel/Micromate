
import gc
import time
import math

from sprite import Scene


class Carousel:
    CENTER_X = 160
    CENTER_Y = 120
    SPACING  = 100
    ANIM_STEPS = 6
    ICON_SIZE = 32
    SLOT_OFFSETS = [-2, -1, 0, 1, 2]

    def __init__(self, ctx):
        self.disp             = ctx["disp"]
        self.list_apps         = ctx["list_apps"]
        self.launch_app        = ctx["launch_app"]
        self.draw_status_bar   = ctx["draw_status_bar"]
        self.update_clock      = ctx["update_clock"]
        self.draw_wifi_status  = ctx["draw_wifi_status"]
        STATUS_H               = ctx["STATUS_H"]
        self.BG                = ctx["BG"]
        self.TEXT_COLOR        = ctx["TEXT_COLOR"]
        self.ACCENT            = ctx["ACCENT"]
        self.DIM               = ctx["DIM"]

        self.DRAW_Y   = STATUS_H + 2
        self.DRAW_H   = 240 - self.DRAW_Y
        self.ICON_Y   = self.CENTER_Y - 16
        self.BORDER_T = self.CENTER_Y - 40
        self.TEXT_Y   = self.CENTER_Y + 44
        self.TEXT_H   = 20
        self.ANIM_Y   = self.BORDER_T - 2
        ICON_W_H      = 4
        self.ANIM_H   = (self.ICON_Y + 32 + ICON_W_H) - self.ANIM_Y
        self.ICON_LOCAL_Y = self.ICON_Y - self.ANIM_Y

        self.apps = []
        self.selected = 0

        gc.collect()
        print("ANIM_H =", self.ANIM_H,
              "| band buf = 320 *", self.ANIM_H, "* 2 =", 320 * self.ANIM_H * 2, "bytes")
        print("Free heap before Scene:", gc.mem_free())
        self.scene = Scene(self.disp, band_height=16,
                            screen_width=320, screen_height=self.ANIM_H,
                            background_color=self.BG,
                            screen_y_offset=self.ANIM_Y,
                            invert_colors=False)
        self.slot_handles = [
            self.scene.add_sprite(None, 0, self.ICON_LOCAL_Y, visible=False)
            for _ in self.SLOT_OFFSETS
        ]

    def update_slot_sprites(self):
        """Point each of the 5 fixed slot handles at the correct app's
        icon Sprite for the current self.selected index. Call this
        whenever selected changes or the app list is (re)loaded."""
        if not self.apps:
            for h in self.slot_handles:
                h.visible = False
            return
        n = len(self.apps)
        for slot_i, i in enumerate(self.SLOT_OFFSETS):
            idx = (self.selected + i) % n
            app = self.apps[idx]
            h = self.slot_handles[slot_i]
            if app.icon:
                h.sprite = app.icon
                h.visible = True
            else:
                h.visible = False

    def position_slots(self, offset):
        for slot_i, i in enumerate(self.SLOT_OFFSETS):
            x = self.CENTER_X + i * self.SPACING + offset
            self.slot_handles[slot_i].x = x - 16  # 32-wide icon, centered

    def draw_labels_and_border(self, offset, full_clear=False):
        disp = self.disp
        if full_clear:
            try: disp.fill_rectangle(0, self.DRAW_Y, 320, self.DRAW_H, self.BG)
            except: pass
        else:
            try: disp.fill_rectangle(0, self.TEXT_Y, 320, self.TEXT_H, self.BG)
            except: pass

        for i in range(-2, 3):
            if not self.apps: break
            idx = (self.selected + i) % len(self.apps)
            app = self.apps[idx]
            x   = self.CENTER_X + i * self.SPACING + offset
            if x < -64 or x > 384: continue
            if i == 0 and offset == 0:
                try: disp.draw_rectangle(x-40, self.BORDER_T, 80, 80, self.ACCENT)
                except: pass
            tc = self.TEXT_COLOR if (i == 0 and offset == 0) else self.DIM
            try:
                nc = app.name[:16]
                tx = max(0, min(312, x - len(nc)*4))
                disp.draw_text8x8(int(tx), self.TEXT_Y+4, nc, tc)
            except: pass

    def draw_frame(self, offset, full_clear=False):
        self.position_slots(offset)
        self.scene.render()
        self.draw_labels_and_border(offset, full_clear=full_clear)

    def animate_scroll(self, direction):
        if not self.apps or len(self.apps) <= 1:
            return
        gc.collect()
        try: self.disp.fill_rectangle(0, self.TEXT_Y, 320, self.TEXT_H, self.BG)
        except: pass
        dist = self.SPACING * direction
        for s in range(self.ANIM_STEPS + 1):
            t     = s / self.ANIM_STEPS
            eased = int(round((0.5 - 0.5 * math.cos(math.pi * t)) * dist))
            self.position_slots(eased)
            self.scene.render()

    def render_home(self):
        gc.collect()
        self.apps = self.list_apps()
        if not self.apps:
            try:
                self.disp.fill_rectangle(0, self.DRAW_Y, 320, self.DRAW_H, self.BG)
                self.disp.draw_text8x8(88, self.CENTER_Y, "No apps found",
                                        self.TEXT_COLOR)
            except: pass
            return
        self.selected %= len(self.apps)
        self.update_slot_sprites()
        self.draw_status_bar()
        self.draw_frame(0, full_clear=True)

    def handle_button(self, btn):
        if not self.apps or btn == 0:
            return False

        gc.collect()
        print("--- handle_button({}) | free heap BEFORE: {} ---".format(
            btn, gc.mem_free()))

        if btn == 1:
            self.animate_scroll(1)
            self.selected = (self.selected - 1) % len(self.apps)
            self.update_slot_sprites()
            self.draw_frame(0)
            gc.collect()
        elif btn == 2:
            self.animate_scroll(-1)
            self.selected = (self.selected + 1) % len(self.apps)
            self.update_slot_sprites()
            self.draw_frame(0)
            gc.collect()
        elif btn == 3:
            self.launch_app(self.apps[self.selected])
            import json
            try:
                with open("/system/settings.json") as f:
                    new = json.load(f)
                if new.get("ui", "carousel") != "carousel":
                    return True  # exit to dispatcher
            except: pass
            self.render_home()
        elif btn == 4:
            self.render_home()

        gc.collect()
        print("--- handle_button({}) | free heap AFTER:  {} | selected={} ---".format(
            btn, gc.mem_free(), self.selected))

        return False


def run(ctx):
    import buttons
    import network

    carousel = Carousel(ctx)
    carousel.render_home()

    while True:
        carousel.update_clock()
        try:
            carousel.draw_wifi_status(network.WLAN(network.STA_IF).isconnected())
        except: pass

        btn = buttons.button_input()
        if btn:
            print("raw button_input() returned:", btn)
        should_exit = carousel.handle_button(btn)
        if should_exit:
            return

        gc.collect()
        time.sleep(0.01)
