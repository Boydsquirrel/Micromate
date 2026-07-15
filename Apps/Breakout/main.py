# breakout_enhanced.py
# Breakout — enhanced: power-ups, multi-level, visual polish, combo system
# Buttons wired directly to pins (pull-ups): pressed == 0

import time
from machine import Pin
try:
    import urandom as random
except ImportError:
    import random

# ===== BUTTON PINS =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)   # paddle left
button2 = Pin(19, Pin.IN, Pin.PULL_UP)   # paddle right
button3 = Pin(18, Pin.IN, Pin.PULL_UP)   # fire / confirm
button4 = Pin(4,  Pin.IN, Pin.PULL_UP)   # back / pause

# ===== SCREEN =====
SCREEN_W = 320
SCREEN_H = 240

# ===== HIGH SCORE =====
HIGHSCORE_PATH = "apps/breakout/highscore.txt"
TOP_SCORES_COUNT = 5

# ===== PLAY AREA — nothing may be drawn or erased outside these bounds =====
PLAY_Y0 = 16          # below header bar
PLAY_Y1 = SCREEN_H - 17  # above bottom status bar

# ===== COLORS (RGB565) =====
BG         = 0x0000
WHITE      = 0xFFFF
BLACK      = 0x0000
RED        = 0xF800
GREEN      = 0x07E0
BLUE       = 0x001F
YELLOW     = 0xFFE0
CYAN       = 0x07FF
MAGENTA    = 0xF81F
ORANGE     = 0xFC00
DARK_GREEN = 0x03E0
GREY       = 0x7BEF
DARK_GREY  = 0x39E7

BRICK_COLORS = [RED, ORANGE, YELLOW, GREEN, CYAN, MAGENTA]

PU_COLOR = {
    "wide":  CYAN,
    "laser": RED,
    "slow":  BLUE,
    "multi": YELLOW,
    "life":  GREEN,
    "fast":  ORANGE,
}

# ===== PADDLE =====
PADDLE_H   = 8
PADDLE_Y   = SCREEN_H - 28   # top of paddle

# ===== BALL =====
BALL_R   = 4
BALL_PAD = 1

# ===== BRICKS =====
BRICK_COLS      = 8
BRICK_W         = 34
BRICK_H         = 10
BRICK_SPACING_X = 6
BRICK_SPACING_Y = 6
BRICK_OFFSET_X  = 10
BRICK_OFFSET_Y  = 20

# ===== LASER =====
LASER_W     = 3
LASER_H     = 10
LASER_SPEED = 400.0

# ===== PHYSICS =====
BASE_BALL_SPEED = 180.0
PADDLE_SPEED    = 260.0
BASE_PADDLE_W   = 64

# ===== LEVELS =====
LEVELS = [
    {"rows": 3, "speed": 1.0,  "label": "1"},
    {"rows": 4, "speed": 1.1,  "label": "2"},
    {"rows": 5, "speed": 1.2,  "label": "3"},
    {"rows": 5, "speed": 1.3,  "label": "4"},
    {"rows": 6, "speed": 1.45, "label": "5"},
]

# ===== POWER-UP SETTINGS =====
POWERUP_CHANCE   = 0.22
POWERUP_TYPES    = ["wide", "laser", "slow", "multi", "life", "fast"]
POWERUP_DURATION = 8.0
WIDE_MULT        = 1.6
SLOW_MULT        = 0.6
POWERUP_W        = 16
POWERUP_H        = 8
POWERUP_SPEED    = 70.0

# ===== PARTICLES =====
MAX_PARTICLES    = 24   # hard cap — keeps frame time bounded
PARTICLE_COUNT   = 4    # spawned per brick (was 6)
PARTICLE_SIZE    = 3    # pixel size of each dot


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


# ==== BUZZER (optional) ====
def beep(freq, ms):
    pass


# ===================================================================
# Safe-draw helpers — all drawing goes through these so nothing ever
# bleeds into the header bar or status bar.

MAX_CHARS = SCREEN_W // 8

def _safe_text(disp, x, y, text, color):
    if not text:
        return
    x = max(0, x)
    if y < PLAY_Y0 or y + 8 > PLAY_Y1 + 16:   # allow header/status text too
        # For text drawn inside header (y<PLAY_Y0) or status bar we allow it;
        # the guard is only against going negative or off screen entirely.
        if y < 0 or y >= SCREEN_H:
            return
    max_chars = (SCREEN_W - x) // 8
    if max_chars <= 0:
        return
    disp.draw_text8x8(x, y, text[:max_chars], color)

def _centered_x(text):
    return max(0, (SCREEN_W - len(text) * 8) // 2)

def _play_fill(disp, x, y, w, h, color):
    """fill_rectangle clamped to the play area — never touches header/status."""
    y0 = max(y, PLAY_Y0)
    y1 = min(y + h, PLAY_Y1)
    if y1 <= y0:
        return
    x0 = max(x, 0)
    x1 = min(x + w, SCREEN_W)
    if x1 <= x0:
        return
    disp.fill_rectangle(x0, y0, x1 - x0, y1 - y0, color)


# ===================================================================
class Particle:
    """Tiny dot that moves for a short lifetime."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'color', 'alive',
                 'px', 'py')   # px/py = last drawn pixel position

    def __init__(self, x, y, color):
        self.x    = float(x)
        self.y    = float(y)
        self.color = color
        self.vx   = (random.getrandbits(8) - 128) * 0.7
        self.vy   = (random.getrandbits(8) - 128) * 0.7
        self.life = 0.35 + (random.getrandbits(6) / 63.0) * 0.25
        self.alive = True
        self.px   = -1   # -1 means not yet drawn
        self.py   = -1

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        if self.life <= 0:
            self.alive = False


class PowerUp:
    __slots__ = ('x', 'y', 'kind', 'alive', 'prev_rect')

    def __init__(self, x, y, kind):
        self.x    = float(x)
        self.y    = float(y)
        self.kind = kind
        self.alive = True
        self.prev_rect = None

    def update(self, dt):
        self.y += POWERUP_SPEED * dt
        if self.y > PLAY_Y1:
            self.alive = False

    def rect(self):
        return (int(self.x - POWERUP_W // 2), int(self.y - POWERUP_H // 2),
                POWERUP_W, POWERUP_H)


class Laser:
    __slots__ = ('x', 'y', 'alive', 'prev_rect')

    def __init__(self, x, y):
        self.x    = x
        self.y    = float(y)
        self.alive = True
        self.prev_rect = None

    def update(self, dt):
        self.y -= LASER_SPEED * dt
        if self.y + LASER_H < PLAY_Y0:
            self.alive = False

    def rect(self):
        return (int(self.x - LASER_W // 2), int(self.y), LASER_W, LASER_H)


class Brick:
    __slots__ = ('x', 'y', 'w', 'h', 'row', 'alive', 'color')

    def __init__(self, x, y, row):
        self.x     = x
        self.y     = y
        self.w     = BRICK_W
        self.h     = BRICK_H
        self.row   = row
        self.alive = True
        self.color = BRICK_COLORS[row % len(BRICK_COLORS)]


# ===================================================================
class Breakout:

    def __init__(self, disp):
        self.disp = disp
        self.level_idx = 0
        self.total_score = 0
        self.lives = 3
        self._load_level()

    # ---------------------------------------------------------------- setup

    def _load_level(self):
        lvl = LEVELS[self.level_idx % len(LEVELS)]
        self.speed_mult = lvl["speed"]
        self.brick_rows = lvl["rows"]
        self.ball_speed = BASE_BALL_SPEED * self.speed_mult

        self.px       = SCREEN_W // 2
        self.paddle_w = BASE_PADDLE_W

        self.balls    = []
        self._spawn_ball()

        self.lasers        = []
        self.laser_cooldown = 0.0
        self.laser_active  = False

        self.powerups  = []
        self.pw_timer  = {}

        self.particles = []

        self.score       = self.total_score
        self.combo       = 0
        self.combo_timer = 0.0

        # prev_paddle: last drawn rect so we can erase precisely
        self.prev_paddle = None

        self._build_bricks()

    def _spawn_ball(self, from_x=None, from_y=None):
        if from_x is None:
            from_x = SCREEN_W // 2
            from_y = PADDLE_Y - BALL_R - 2
        sign = -1 if random.getrandbits(1) == 0 else 1
        vx = sign * 0.6 * self.ball_speed
        vy = -0.8 * self.ball_speed
        # [x, y, vx, vy, prev_rect]
        self.balls.append([float(from_x), float(from_y), vx, vy, None])

    def _build_bricks(self):
        self.bricks = []
        for r in range(self.brick_rows):
            for c in range(BRICK_COLS):
                x = BRICK_OFFSET_X + c * (BRICK_W + BRICK_SPACING_X)
                y = BRICK_OFFSET_Y + r * (BRICK_H + BRICK_SPACING_Y)
                if x + BRICK_W <= SCREEN_W - 8:
                    self.bricks.append(Brick(x, y, r))

    # ---------------------------------------------------------------- helpers

    def _rects_overlap(self, ax, ay, aw, ah, bx, by, bw, bh):
        return not (ax + aw <= bx or bx + bw <= ax or
                    ay + ah <= by or by + bh <= ay)

    def _redraw_bricks_in_rect(self, rx, ry, rw, rh):
        """Redraw any alive bricks that overlap the given rect."""
        for br in self.bricks:
            if not br.alive:
                continue
            if self._rects_overlap(rx, ry, rw, rh, br.x, br.y, br.w, br.h):
                self._draw_brick(br)

    def _erase_play_rect(self, x, y, w, h):
        """Erase a region then restore bricks and paddle within it."""
        _play_fill(self.disp, x, y, w, h, BG)
        self._redraw_bricks_in_rect(x, y, w, h)
        if self.prev_paddle:
            px, py, pw, ph = self.prev_paddle
            if self._rects_overlap(x, y, w, h, px, py, pw, ph):
                self._draw_paddle_now(px, py, pw, ph)

    # ---------------------------------------------------------------- drawing

    def _draw_brick(self, b):
        d = self.disp
        d.fill_rectangle(b.x, b.y, b.w, b.h, b.color)
        d.fill_rectangle(b.x, b.y, b.w, 1, WHITE)
        d.fill_rectangle(b.x, b.y + b.h - 1, b.w, 1, DARK_GREY)

    def _draw_paddle_now(self, x, y, w, h):
        d = self.disp
        d.fill_rectangle(x, y, w, h, GREEN)
        d.fill_rectangle(x, y, w, 2, CYAN)
        d.fill_rectangle(x, y + h - 2, w, 2, DARK_GREEN)

    def draw_static(self):
        d = self.disp
        d.fill_rectangle(0, 0, SCREEN_W, SCREEN_H, BG)
        # header bar
        d.fill_rectangle(0, 0, SCREEN_W, 16, DARK_GREY)
        _safe_text(d, 4,   4, "SCORE:", WHITE)
        _safe_text(d, 140, 4, "LVL:",   WHITE)
        _safe_text(d, 220, 4, "LIVES:", WHITE)
        # bottom bar
        d.fill_rectangle(0, SCREEN_H - 16, SCREEN_W, 16, DARK_GREY)
        self._draw_hud()
        for b in self.bricks:
            self._draw_brick(b)
        self.draw_paddle(force=True)
        for i in range(len(self.balls)):
            self._draw_ball_idx(i, force=True)

    def _draw_hud(self):
        d = self.disp
        d.fill_rectangle(56,  4, 80, 8, DARK_GREY)
        _safe_text(d, 56,  4, str(self.score), YELLOW)
        d.fill_rectangle(172, 4, 40, 8, DARK_GREY)
        _safe_text(d, 172, 4, LEVELS[self.level_idx % len(LEVELS)]["label"], CYAN)
        d.fill_rectangle(276, 4, 40, 8, DARK_GREY)
        _safe_text(d, 276, 4, str(self.lives), RED)
        # bottom bar combo + power-up pips
        d.fill_rectangle(4, SCREEN_H - 12, SCREEN_W - 8, 8, DARK_GREY)
        if self.combo >= 2:
            _safe_text(d, 4, SCREEN_H - 12, "COMBO x" + str(self.combo), ORANGE)
        xi = 160
        for kind in ("wide", "laser", "slow", "multi"):
            if self.pw_timer.get(kind, 0) > 0:
                d.fill_rectangle(xi, SCREEN_H - 12, 6, 8, PU_COLOR.get(kind, WHITE))
                xi += 8

    def draw_paddle(self, force=False):
        d = self.disp
        pw = self.paddle_w
        x  = int(self.px - pw // 2)
        y  = PADDLE_Y
        rect = (x, y, pw, PADDLE_H)
        if force or rect != self.prev_paddle:
            # Erase old paddle first — but only if it differs from new position.
            # On respawn prev_paddle was cleared, so we fill the whole paddle row
            # to make sure any ghost from the previous life is gone.
            if self.prev_paddle and self.prev_paddle != rect:
                ox, oy, ow, oh = self.prev_paddle
                _play_fill(d, ox, oy, ow, oh, BG)
                self._redraw_bricks_in_rect(ox, oy, ow, oh)
            elif force:
                # Respawn / force: wipe the entire paddle row in play area
                _play_fill(d, 0, PADDLE_Y, SCREEN_W, PADDLE_H, BG)
            self._draw_paddle_now(x, y, pw, PADDLE_H)
            self.prev_paddle = rect

    def _draw_ball_idx(self, idx, force=False):
        d    = self.disp
        ball = self.balls[idx]
        bx   = int(ball[0])
        by   = int(ball[1])
        prev = ball[4]
        r    = BALL_R + BALL_PAD
        rect = (bx - r, by - r, r * 2, r * 2)
        if force or rect != prev:
            if prev:
                ox, oy, ow, oh = prev
                self._erase_play_rect(ox, oy, ow, oh)
            # glow ring + ball
            _play_fill(d, bx - BALL_R - 1, by - BALL_R - 1,
                       BALL_R * 2 + 2, BALL_R * 2 + 2, ORANGE)
            _play_fill(d, bx - BALL_R, by - BALL_R,
                       BALL_R * 2, BALL_R * 2, YELLOW)
            ball[4] = rect

    # ---------------------------------------------------------------- particles

    def _spawn_particles(self, bx, by, color):
        # Respect the hard cap — drop oldest ones if needed
        need = PARTICLE_COUNT
        if len(self.particles) + need > MAX_PARTICLES:
            # erase and remove the oldest (front of list)
            remove = len(self.particles) + need - MAX_PARTICLES
            for p in self.particles[:remove]:
                if p.px >= 0:
                    _play_fill(self.disp, p.px, p.py,
                               PARTICLE_SIZE, PARTICLE_SIZE, BG)
                    self._redraw_bricks_in_rect(p.px, p.py,
                                               PARTICLE_SIZE, PARTICLE_SIZE)
            self.particles = self.particles[remove:]
        cx = bx + BRICK_W // 2
        cy = by + BRICK_H // 2
        for _ in range(need):
            self.particles.append(Particle(cx, cy, color))

    def draw_particles(self):
        d    = self.disp
        dead = []
        for i, p in enumerate(self.particles):
            npx = int(p.x)
            npy = int(p.y)

            if not p.alive:
                # erase last drawn position
                if p.px >= 0:
                    _play_fill(d, p.px, p.py, PARTICLE_SIZE, PARTICLE_SIZE, BG)
                    self._redraw_bricks_in_rect(p.px, p.py,
                                               PARTICLE_SIZE, PARTICLE_SIZE)
                dead.append(i)
                continue

            # only redraw if pixel-position actually changed
            if npx == p.px and npy == p.py:
                continue

            # erase old
            if p.px >= 0:
                _play_fill(d, p.px, p.py, PARTICLE_SIZE, PARTICLE_SIZE, BG)
                self._redraw_bricks_in_rect(p.px, p.py,
                                           PARTICLE_SIZE, PARTICLE_SIZE)

            # draw new (only if inside play area)
            if PLAY_Y0 <= npy < PLAY_Y1 and 0 <= npx < SCREEN_W:
                _play_fill(d, npx, npy, PARTICLE_SIZE, PARTICLE_SIZE, p.color)
                p.px = npx
                p.py = npy
            else:
                p.px = -1   # off-screen — don't try to erase next frame

        # remove dead in reverse order
        for i in reversed(dead):
            self.particles.pop(i)

    # ---------------------------------------------------------------- powerups / lasers

    def draw_powerups(self):
        d    = self.disp
        dead = []
        for i, pu in enumerate(self.powerups):
            if not pu.alive:
                if pu.prev_rect:
                    rx, ry, rw, rh = pu.prev_rect
                    _play_fill(d, rx, ry, rw, rh, BG)
                    self._redraw_bricks_in_rect(rx, ry, rw, rh)
                    pu.prev_rect = None
                dead.append(i)
                continue
            r = pu.rect()
            if r != pu.prev_rect:
                if pu.prev_rect:
                    ox, oy, ow, oh = pu.prev_rect
                    _play_fill(d, ox, oy, ow, oh, BG)
                    self._redraw_bricks_in_rect(ox, oy, ow, oh)
                rx, ry, rw, rh = r
                col = PU_COLOR.get(pu.kind, WHITE)
                _play_fill(d, rx, ry, rw, rh, col)
                _safe_text(d, rx + 4, ry + 1, pu.kind[0].upper(), BLACK)
                pu.prev_rect = r
        for i in reversed(dead):
            self.powerups.pop(i)

    def draw_lasers(self):
        d    = self.disp
        dead = []
        for i, las in enumerate(self.lasers):
            if not las.alive:
                if las.prev_rect:
                    rx, ry, rw, rh = las.prev_rect
                    _play_fill(d, rx, ry, rw, rh, BG)
                    self._redraw_bricks_in_rect(rx, ry, rw, rh)
                    las.prev_rect = None
                dead.append(i)
                continue
            r = las.rect()
            if r != las.prev_rect:
                if las.prev_rect:
                    ox, oy, ow, oh = las.prev_rect
                    _play_fill(d, ox, oy, ow, oh, BG)
                    self._redraw_bricks_in_rect(ox, oy, ow, oh)
                rx, ry, rw, rh = r
                _play_fill(d, rx, ry, rw, rh, RED)
                las.prev_rect = r
        for i in reversed(dead):
            self.lasers.pop(i)

    # ---------------------------------------------------------------- power-up logic

    def _apply_powerup(self, kind):
        beep(880, 80)
        if kind == "wide":
            self.paddle_w = int(BASE_PADDLE_W * WIDE_MULT)
            self.pw_timer["wide"] = POWERUP_DURATION
            self.draw_paddle(force=True)
        elif kind == "laser":
            self.laser_active = True
            self.pw_timer["laser"] = POWERUP_DURATION
        elif kind == "slow":
            for b in self.balls:
                mag = (b[2] ** 2 + b[3] ** 2) ** 0.5
                if mag > 0:
                    b[2] = b[2] / mag * self.ball_speed * SLOW_MULT
                    b[3] = b[3] / mag * self.ball_speed * SLOW_MULT
            self.pw_timer["slow"] = POWERUP_DURATION
        elif kind == "multi":
            for _ in range(2):
                if self.balls:
                    self._spawn_ball(self.balls[0][0], self.balls[0][1])
            self.pw_timer["multi"] = 0.1
        elif kind == "life":
            self.lives = min(self.lives + 1, 9)
            self._draw_hud()
        elif kind == "fast":
            for b in self.balls:
                mag = (b[2] ** 2 + b[3] ** 2) ** 0.5
                if mag > 0:
                    b[2] = b[2] / mag * self.ball_speed * 1.4
                    b[3] = b[3] / mag * self.ball_speed * 1.4

    def _tick_powerup_timers(self, dt):
        expired = []
        for kind in self.pw_timer:
            self.pw_timer[kind] -= dt
            if self.pw_timer[kind] <= 0:
                expired.append(kind)
        for kind in expired:
            del self.pw_timer[kind]
            if kind == "wide":
                self.paddle_w = BASE_PADDLE_W
                self.draw_paddle(force=True)
            elif kind == "laser":
                self.laser_active = False

    # ---------------------------------------------------------------- respawn

    def _respawn(self):
        """Clean slate after losing a ball — erase everything live first."""
        d = self.disp
        # erase any remaining particles
        for p in self.particles:
            if p.px >= 0:
                _play_fill(d, p.px, p.py, PARTICLE_SIZE, PARTICLE_SIZE, BG)
        self.particles = []
        # erase power-ups
        for pu in self.powerups:
            if pu.prev_rect:
                rx, ry, rw, rh = pu.prev_rect
                _play_fill(d, rx, ry, rw, rh, BG)
        self.powerups = []
        # erase lasers
        for las in self.lasers:
            if las.prev_rect:
                rx, ry, rw, rh = las.prev_rect
                _play_fill(d, rx, ry, rw, rh, BG)
        self.lasers = []
        # wipe the entire paddle row so the old ghost paddle is gone
        _play_fill(d, 0, PADDLE_Y, SCREEN_W, PADDLE_H, BG)
        self.prev_paddle = None
        # reset power-up state
        self.laser_active = False
        self.pw_timer.clear()
        # reset paddle width
        self.paddle_w = BASE_PADDLE_W
        self.px = SCREEN_W // 2
        # spawn fresh ball
        self.balls = []
        self._spawn_ball()
        # redraw paddle + ball cleanly
        self.draw_paddle(force=True)
        self._draw_ball_idx(0, force=True)
        self._draw_hud()

    # ---------------------------------------------------------------- main update

    def update(self, dt):
        d = self.disp

        self._tick_powerup_timers(dt)

        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0
                self._draw_hud()

        # paddle
        moved = False
        if not button1.value():
            self.px -= PADDLE_SPEED * dt;  moved = True
        if not button2.value():
            self.px += PADDLE_SPEED * dt;  moved = True
        half = self.paddle_w // 2
        self.px = clamp(self.px, half, SCREEN_W - half)
        self.draw_paddle()

        # laser fire
        self.laser_cooldown -= dt
        if self.laser_active and not button3.value() and self.laser_cooldown <= 0:
            lx = int(self.px)
            ly = PADDLE_Y - LASER_H - 1
            self.lasers.append(Laser(lx - 10, ly))
            self.lasers.append(Laser(lx + 10, ly))
            self.laser_cooldown = 0.3
            beep(440, 30)

        # update lasers
        for las in self.lasers:
            if not las.alive:
                continue
            las.update(dt)
            lr = las.rect()
            lrx, lry, lrw, lrh = lr
            for b in self.bricks:
                if not b.alive:
                    continue
                if self._rects_overlap(lrx, lry, lrw, lrh, b.x, b.y, b.w, b.h):
                    las.alive = False
                    b.alive = False
                    _play_fill(d, b.x, b.y, b.w, b.h, BG)
                    self._spawn_particles(b.x, b.y, b.color)
                    self._handle_brick_break(b)
                    break
        self.draw_lasers()

        # update power-ups
        for pu in self.powerups:
            if not pu.alive:
                continue
            pu.update(dt)
            pr = pu.rect()
            prx, pry, prw, prh = pr
            paddle_rect = (int(self.px - self.paddle_w // 2), PADDLE_Y,
                           self.paddle_w, PADDLE_H)
            if self._rects_overlap(prx, pry, prw, prh, *paddle_rect):
                pu.alive = False
                self._apply_powerup(pu.kind)
        self.draw_powerups()

        # update particles (physics only — draw handled separately)
        for p in self.particles:
            p.update(dt)
        self.draw_particles()

        # update balls
        dead_balls = []
        for i, ball in enumerate(self.balls):
            bx, by, vx, vy, _ = ball

            bx += vx * dt
            by += vy * dt

            # walls
            if bx - BALL_R <= 0:
                bx = BALL_R + 1;  vx = -vx;  beep(300, 15)
            elif bx + BALL_R >= SCREEN_W:
                bx = SCREEN_W - BALL_R - 1;  vx = -vx;  beep(300, 15)

            # top wall (header boundary)
            if by - BALL_R <= PLAY_Y0:
                by = PLAY_Y0 + BALL_R + 1;  vy = -vy;  beep(300, 15)

            # paddle collision
            phalf = self.paddle_w // 2
            px_l  = self.px - phalf
            if (px_l <= bx <= px_l + self.paddle_w and
                    PADDLE_Y <= by + BALL_R <= PADDLE_Y + PADDLE_H):
                by = PADDLE_Y - BALL_R - 1
                vy = -abs(vy)
                hit = (bx - px_l) / self.paddle_w
                vx += (hit - 0.5) * 120.0
                mag = (vx ** 2 + vy ** 2) ** 0.5
                if mag != 0:
                    spd = self.ball_speed * (SLOW_MULT if "slow" in self.pw_timer else 1.0)
                    vx = vx / mag * spd
                    vy = vy / mag * spd
                beep(500, 20)

            # brick collisions
            for b in self.bricks:
                if not b.alive:
                    continue
                if b.x <= bx <= b.x + b.w and b.y <= by <= b.y + b.h:
                    b.alive = False
                    _play_fill(d, b.x, b.y, b.w, b.h, BG)
                    self._spawn_particles(b.x, b.y, b.color)
                    self._handle_brick_break(b)
                    vy = -vy
                    beep(600, 20)
                    break

            if by - BALL_R > SCREEN_H:
                # erase ball before marking dead
                prev = ball[4]
                if prev:
                    ox, oy, ow, oh = prev
                    _play_fill(d, ox, oy, ow, oh, BG)
                    self._redraw_bricks_in_rect(ox, oy, ow, oh)
                dead_balls.append(i)
            else:
                ball[0] = bx;  ball[1] = by;  ball[2] = vx;  ball[3] = vy
                self._draw_ball_idx(i)

        for i in reversed(dead_balls):
            self.balls.pop(i)

        if not self.balls:
            self.lives -= 1
            beep(200, 300)
            if self.lives <= 0:
                return False
            self._respawn()
            return True

        # level clear?
        if all(not b.alive for b in self.bricks):
            beep(880, 100);  beep(1100, 100);  beep(1320, 200)
            self.total_score = self.score
            self.level_idx  += 1
            d.fill_rectangle(60, 90, 200, 40, DARK_GREY)
            _safe_text(d, 80, 105, "LEVEL CLEAR!", YELLOW)
            time.sleep(1.5)
            self._load_level()
            self.draw_static()

        return True

    def _handle_brick_break(self, b):
        pts = 10 * (1 + b.row)
        self.combo += 1
        self.combo_timer = 1.2
        if self.combo > 1:
            pts += (self.combo - 1) * 5
        self.score += pts
        self._draw_hud()
        if random.getrandbits(8) < int(POWERUP_CHANCE * 256):
            kind = POWERUP_TYPES[random.getrandbits(8) % len(POWERUP_TYPES)]
            self.powerups.append(PowerUp(b.x + b.w // 2, b.y + b.h // 2, kind))


# ===================================================================
# HIGH SCORE HELPERS

def _ensure_dir(path):
    import os
    cur = ""
    for part in path.split("/")[:-1]:
        if not part:
            continue
        cur = cur + "/" + part if cur else part
        try:
            os.mkdir(cur)
        except OSError:
            pass

def load_scores():
    try:
        with open(HIGHSCORE_PATH, "r") as f:
            scores = []
            for line in f:
                line = line.strip()
                if line:
                    try:
                        scores.append(int(line))
                    except ValueError:
                        pass
        scores.sort(reverse=True)
        return scores[:TOP_SCORES_COUNT]
    except OSError:
        return []

def save_scores(scores):
    _ensure_dir(HIGHSCORE_PATH)
    try:
        with open(HIGHSCORE_PATH, "w") as f:
            for s in scores[:TOP_SCORES_COUNT]:
                f.write(str(s) + "\n")
    except OSError:
        pass

def submit_score(new_score):
    scores = load_scores()
    scores.append(new_score)
    scores.sort(reverse=True)
    scores = scores[:TOP_SCORES_COUNT]
    save_scores(scores)
    return scores

def is_high_score(new_score):
    scores = load_scores()
    return len(scores) < TOP_SCORES_COUNT or new_score > scores[-1]

def show_highscores(disp, current_score=None):
    scores = load_scores()
    disp.fill_rectangle(0, 0, SCREEN_W, SCREEN_H, BG)
    disp.fill_rectangle(0, 0, SCREEN_W, 18, DARK_GREY)
    title = "HIGH SCORES"
    _safe_text(disp, _centered_x(title), 5, title, YELLOW)
    rank_colors = [YELLOW, CYAN, WHITE, GREY, GREY]
    for i, s in enumerate(scores):
        y   = 30 + i * 22
        col = rank_colors[i] if i < len(rank_colors) else GREY
        if current_score is not None and s == current_score and col != YELLOW:
            col = GREEN
        _safe_text(disp, 40, y, str(i + 1) + ".", col)
        _safe_text(disp, 80, y, str(s),            col)
    if not scores:
        _safe_text(disp, 60, 60, "NO SCORES YET", GREY)
    if current_score is not None and is_high_score(current_score):
        msg = "NEW HIGH SCORE!"
        disp.fill_rectangle(0, SCREEN_H - 36, SCREEN_W, 18, DARK_GREY)
        _safe_text(disp, _centered_x(msg), SCREEN_H - 32, msg, GREEN)
    _safe_text(disp, 20, SCREEN_H - 14, "BTN3/BTN4: BACK", GREY)
    while button3.value() and button4.value():
        time.sleep(0.05)
    while not button3.value() or not button4.value():
        time.sleep(0.05)


# ===================================================================
def show_screen(disp, lines, colors=None, bg=DARK_GREY):
    disp.fill_rectangle(0, 0, SCREEN_W, SCREEN_H, bg)
    for i, line in enumerate(lines):
        if not line:
            continue
        y   = 80 + i * 20
        col = colors[i] if colors else WHITE
        _safe_text(disp, _centered_x(line), y, line, col)


def run(disp):
    top    = load_scores()
    hs_str = "BEST: " + str(top[0]) if top else "BEST: ---"
    show_screen(disp,
                ["BREAKOUT", "ENHANCED", hs_str, "", "BTN3: START", "BTN4: SCORES"],
                [YELLOW, CYAN, GREY, WHITE, GREEN, CYAN])
    while button3.value() and button4.value():
        time.sleep(0.05)
    if not button4.value():
        show_highscores(disp)
        return run(disp)
    while not button3.value():
        time.sleep(0.05)

    while True:
        game = Breakout(disp)
        game.draw_static()

        last  = time.ticks_ms()
        alive = True
        while alive:
            now = time.ticks_ms()
            dt  = time.ticks_diff(now, last) / 1000.0
            if dt > 0.05:
                dt = 0.05
            alive = game.update(dt)
            last  = now
            time.sleep(0.016)

        final_score = game.score
        submit_score(final_score)

        scores    = load_scores()
        new_best  = bool(scores and scores[0] == final_score)
        best_disp = str(scores[0]) if scores else str(final_score)
        show_screen(disp,
                    ["NEW BEST!" if new_best else "GAME OVER",
                     "SCORE: " + str(final_score),
                     "BEST:  " + best_disp,
                     "",
                     "BTN3: RETRY",
                     "BTN4: SCORES"],
                    [YELLOW if new_best else RED, YELLOW, CYAN, WHITE, GREEN, CYAN])
        while button3.value() and button4.value():
            time.sleep(0.05)
        if not button4.value():
            while not button4.value():
                time.sleep(0.05)
            show_highscores(disp, current_score=final_score)
            return run(disp)
        while not button3.value():
            time.sleep(0.05)