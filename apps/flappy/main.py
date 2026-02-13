import time
import random
from machine import Pin

# ===== CONFIG =====
W = 320
H = 240

WHITE = 0xFFFF
GREEN = 0x07E0
BLACK = 0x0000

PIPE_WIDTH = 22
PIPE_GAP = 70
PIPE_SPACING = 140
PIPE_SPEED = 3         # faster movement
PIPE_COUNT = 4

GRAVITY = 1
FLAP = -8              # snappier flap
FRAME_DELAY = 0.015    # ~66 FPS

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

# ===== GAME RUN =====
def run(disp):
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

    disp.clear(BLACK)
    # initial draw
    for p in pipes:
        p.draw_at(disp)
    disp.fill_rectangle(bx, prev_by, 8, 8, WHITE)
    # draw initial score
    disp.draw_text8x8(4, 4, f"Score: {score}", WHITE)

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

        # draw/update score only if changed (minimal erase)
        if score != prev_score:
            # clear small area for score (assumes 8x8 per char, length small)
            disp.fill_rectangle(0, 0, 90, 10, BLACK)
            disp.draw_text8x8(4, 4, f"Score: {score}", WHITE)
            prev_score = score

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

    # game over
    disp.clear(BLACK)
    disp.draw_text8x8(100, 120, "Game Over", WHITE)
    time.sleep(1.5)
    disp.clear(BLACK)


