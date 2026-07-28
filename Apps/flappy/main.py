#flappy bird  game
import os
import time
import random
from machine import Pin

# ===== CONFIG =====
W = 320
H = 240

WHITE = 0xFFFF
GREEN = 0x07E0
BLACK = 0x0000
YELLOW = 0xFFE0

PIPE_WIDTH = 22
PIPE_GAP = 70
PIPE_SPACING = 140
PIPE_SPEED = 3         # faster movement
PIPE_COUNT = 4

GRAVITY = 1
FLAP = -8              # snappier flap
FRAME_DELAY = 0.015    # ~66 FPS

# highscore file lives with the app, not in the general text-files folder
_HS_DIR  = "/apps/flappy/"
_HS_PATH = _HS_DIR + "highscore.txt"

# ===== BUTTONS (non-blocking, edge detect) =====
button1 = Pin(17, Pin.IN, Pin.PULL_UP)
button2 = Pin(19, Pin.IN, Pin.PULL_UP)
button3 = Pin(18, Pin.IN, Pin.PULL_UP)
button4 = Pin(4, Pin.IN, Pin.PULL_UP)
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


# ===== HIGHSCORE PERSISTENCE =====
def _ensure_dir():
    """Create apps/flappy/ if it doesn't exist yet. Safe to call repeatedly."""
    try:
        os.mkdir("apps")
    except OSError:
        pass
    try:
        os.mkdir(_HS_DIR.rstrip("/"))
    except OSError:
        pass


def _load_highscore():
    """Return the stored highscore, or 0 if none exists / file is bad."""
    try:
        with open(_HS_PATH, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def _save_highscore(score):
    """Write the new highscore. Returns True on success."""
    _ensure_dir()
    try:
        with open(_HS_PATH, "w") as f:
            f.write(str(score))
        return True
    except OSError:
        return False


# ===== PIPE CLASS with minimal erase to avoid flicker =====
class Pipe:
    def __init__(self, x):
        self.x = x
        self.prev_x = x
        self.gap_y = random.randint(40, H - PIPE_GAP - 40)

    def update(self):
        self.prev_x = self.x
        self.x -= PIPE_SPEED
        wrapped = False
        if self.x < -PIPE_WIDTH:
            # wrap to right side
            self.x = W
            self.gap_y = random.randint(40, H - PIPE_GAP - 40)
            wrapped = True
        return wrapped

    def draw_at(self, disp):
        # draw full pipe at current x
        disp.fill_rectangle(self.x, 0, PIPE_WIDTH, self.gap_y, GREEN)
        disp.fill_rectangle(
            self.x,
            self.gap_y + PIPE_GAP,
            PIPE_WIDTH,
            H - (self.gap_y + PIPE_GAP),
            GREEN
        )

    def erase_trailing(self, disp):
        # only erase the rightmost vertical strip that the pipe left behind (width = PIPE_SPEED)
        # if wrapped, erase the whole previous rectangle to avoid remnants.
        if self.prev_x <= self.x:
            # wrapped (prev_x small negative or less than new x) -> clear full prev area
            disp.fill_rectangle(self.prev_x, 0, PIPE_WIDTH, self.gap_y, BLACK)
            disp.fill_rectangle(
                self.prev_x,
                self.gap_y + PIPE_GAP,
                PIPE_WIDTH,
                H - (self.gap_y + PIPE_GAP),
                BLACK
            )
            return

        # normal move left: the exposed area is the rightmost strip of width PIPE_SPEED at prev_x + PIPE_WIDTH - PIPE_SPEED .. prev_x + PIPE_WIDTH -1
        strip_x = self.prev_x + PIPE_WIDTH - PIPE_SPEED
        if strip_x < 0:
            # clamp
            strip_x = 0
        # erase top strip
        disp.fill_rectangle(strip_x, 0, PIPE_SPEED, self.gap_y, BLACK)
        # erase bottom strip
        disp.fill_rectangle(
            strip_x,
            self.gap_y + PIPE_GAP,
            PIPE_SPEED,
            H - (self.gap_y + PIPE_GAP),
            BLACK
        )

    def right_edge_prev(self):
        return self.prev_x + PIPE_WIDTH

    def right_edge(self):
        return self.x + PIPE_WIDTH

    def collides(self, bx, by):
        if bx + 8 > self.x and bx < self.x + PIPE_WIDTH:
            if not (self.gap_y < by < self.gap_y + PIPE_GAP):
                return True
        return False


# ===== HUD =====
def _draw_hud(disp, score, highscore):
    # cleared width covers "Score: 999  Best: 999" comfortably
    disp.fill_rectangle(0, 0, 200, 10, BLACK)
    disp.draw_text8x8(4, 4, "Score:{}  Best:{}".format(score, highscore), WHITE)


# ===== GAME RUN =====
def run(disp):
    highscore = _load_highscore()

    # bird
    bx = 60
    by = 120.0
    bv = 0.0
    prev_by = int(by)

    # create pipes
    pipes = []
    start_x = W
    for i in range(PIPE_COUNT):
        pipes.append(Pipe(start_x + i * PIPE_SPACING))

    # scoring
    score = 0
    prev_score = -1  # force initial draw
    prev_highscore = -1

    disp.clear(BLACK)
    # initial draw
    for p in pipes:
        p.draw_at(disp)
    disp.fill_rectangle(bx, prev_by, 8, 8, WHITE)
    # draw initial score/highscore
    _draw_hud(disp, score, highscore)
    prev_score = score
    prev_highscore = highscore

    while True:
        btn = button_input()
        if btn == 1:
            disp.clear(BLACK)
            return
        if btn == 3:
            bv = FLAP

        # physics
        bv += GRAVITY
        by += bv

        # erase bird old position (minimal)
        disp.fill_rectangle(bx, int(prev_by), 8, 8, BLACK)

        # move & draw pipes (draw at new positions FIRST)
        for p in pipes:
            wrapped = p.update()
            p.draw_at(disp)

        # erase trailing leftovers AFTER drawing pipes (this prevents a black flash)
        for p in pipes:
            p.erase_trailing(disp)

        # draw bird at new pos
        disp.fill_rectangle(bx, int(by), 8, 8, WHITE)

        # scoring: count when pipe just passed the bird (right edge crosses left of bird)
        for p in pipes:
            # if previously the pipe's right edge was >= bird and now it's < bird, it just passed
            if p.right_edge_prev() >= bx and p.right_edge() < bx:
                score += 1
                if score > highscore:
                    highscore = score

        # draw/update HUD only if changed (minimal erase)
        if score != prev_score or highscore != prev_highscore:
            _draw_hud(disp, score, highscore)
            prev_score = score
            prev_highscore = highscore

        # collision
        if by < 0 or by > H:
            break
        collision = False
        for p in pipes:
            if p.collides(bx, int(by)):
                collision = True
                break
        if collision:
            break

        prev_by = by
        time.sleep(FRAME_DELAY)

    # persist highscore if this run beat it
    old_highscore = _load_highscore()
    new_best = highscore > old_highscore
    if new_best:
        _save_highscore(highscore)

    # game over
    disp.clear(BLACK)
    disp.draw_text8x8(100, 110, "Game Over", WHITE)
    disp.draw_text8x8(88, 126, "Score: {}".format(score), WHITE)
    if new_best:
        disp.draw_text8x8(84, 142, "New Best: {}".format(highscore), YELLOW)
    else:
        disp.draw_text8x8(84, 142, "Best: {}".format(highscore), WHITE)
    time.sleep(1.8)
    disp.clear(BLACK)
