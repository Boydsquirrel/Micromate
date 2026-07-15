
try:
    import gc
except ImportError:
    gc = None

MAGIC = b"SPR1"
NO_KEY = 0xFFFF


class SpriteError(Exception):
    pass


class Sprite:
    @staticmethod
    def peek_size(path):
        """Read just the header (no pixel data) and return (width,
        height, pixel_data_bytes) for a .spr file, without loading it.
        Useful for deciding preload vs streamed before committing."""
        with open(path, "rb") as f:
            header = f.read(10)
        if len(header) < 10 or header[0:4] != MAGIC:
            raise SpriteError(
                "{}: not a valid .spr file (bad magic)".format(path))
        width = int.from_bytes(header[4:6], "big")
        height = int.from_bytes(header[6:8], "big")
        return width, height, width * height * 2

    @staticmethod
    def fits_in_ram(path, safety_margin_bytes=20_000):
        if gc is None or not hasattr(gc, "mem_free"):
            return False
        _, _, pixel_bytes = Sprite.peek_size(path)
        gc.collect()
        free = gc.mem_free()
        return pixel_bytes + safety_margin_bytes <= free

    def __init__(self, path, preload=True):
        self.path = path
        self.preload = preload
        self._file = None

        f = open(path, "rb")
        header = f.read(10)
        if len(header) < 10 or header[0:4] != MAGIC:
            f.close()
            raise SpriteError(
                "{}: not a valid .spr file (bad magic)".format(path))
        self.width = int.from_bytes(header[4:6], "big")
        self.height = int.from_bytes(header[6:8], "big")
        self.key = int.from_bytes(header[8:10], "big")
        self._data_start = 10 
        self._row_bytes = self.width * 2

        expected = self.width * self.height * 2

        if preload:
            self.data = f.read()
            f.close()
            if len(self.data) != expected:
                raise SpriteError(
                    "{}: pixel data size {} != expected {} (w={} h={})".format(
                        path, len(self.data), expected,
                        self.width, self.height))
            self._view = memoryview(self.data)
        else:
            f.seek(0, 2)  # seek to end
            actual_size = f.tell() - self._data_start
            if actual_size != expected:
                f.close()
                raise SpriteError(
                    "{}: pixel data size {} != expected {} (w={} h={})".format(
                        path, actual_size, expected, self.width, self.height))
            self.data = None
            self._view = None
            self._file = f

        self.has_transparency = self.key != NO_KEY
        self.use_run_based_render = False
        if self.has_transparency and self.preload:
            row_runs, avg_run_length = self._build_row_runs_and_measure()
            MIN_AVG_RUN_LENGTH = 6
            if avg_run_length >= MIN_AVG_RUN_LENGTH:
                self._row_runs = row_runs
                self.use_run_based_render = True

    def _build_row_runs_and_measure(self):
        key_hi = (self.key >> 8) & 0xFF
        key_lo = self.key & 0xFF
        runs_per_row = []
        total_runs = 0
        total_opaque_px = 0
        for row in range(self.height):
            row_bytes = self.get_row(row)
            runs = []
            run_start = None
            for col in range(self.width):
                off = col * 2
                is_key = (row_bytes[off] == key_hi and row_bytes[off + 1] == key_lo)
                if is_key:
                    if run_start is not None:
                        runs.append((run_start, col))
                        total_runs += 1
                        total_opaque_px += col - run_start
                        run_start = None
                else:
                    if run_start is None:
                        run_start = col
            if run_start is not None:
                runs.append((run_start, self.width))
                total_runs += 1
                total_opaque_px += self.width - run_start
            runs_per_row.append(runs)
        avg_run_length = (total_opaque_px / total_runs) if total_runs else 0
        return runs_per_row, avg_run_length

    def get_row(self, row):
        if self.preload:
            start = row * self._row_bytes
            return self._view[start:start + self._row_bytes]
        else:
            offset = self._data_start + row * self._row_bytes
            self._file.seek(offset)
            return self._file.read(self._row_bytes)

    def get_rows(self, start_row, count):
        count = min(count, self.height - start_row)
        if count <= 0:
            return b""
        if self.preload:
            start = start_row * self._row_bytes
            return self._view[start:start + count * self._row_bytes]
        else:
            offset = self._data_start + start_row * self._row_bytes
            self._file.seek(offset)
            return self._file.read(count * self._row_bytes)

    def close(self):
        """Release the open file handle (streamed mode only). Safe to
        call even if preloaded or already closed."""
        if self._file is not None:
            self._file.close()
            self._file = None

    def __repr__(self):
        mode = "preloaded" if self.preload else "streamed"
        return "Sprite({!r}, {}x{}, key=0x{:04X}, {})".format(
            self.path, self.width, self.height, self.key, mode)


class SpriteHandle:


    __slots__ = ("sprite", "x", "y", "visible", "z")

    def __init__(self, sprite, x, y, z=0, visible=True):
        self.sprite = sprite  
        self.x = x
        self.y = y
        self.z = z         
        self.visible = visible

    def bbox(self):
        """Return (x0, y0, x1, y1) - x1/y1 exclusive. Only valid when
        self.sprite is not None - callers must check that first (the
        Scene's render loop already does)."""
        return (self.x, self.y,
                self.x + self.sprite.width, self.y + self.sprite.height)


class Scene:
    """Band-based compositor. Owns one reusable band buffer in RAM and
    blits it to the display, one band at a time, every render() call.
    """

    def __init__(self, disp, band_height=32, screen_width=None,
                 screen_height=None, background_color=0x0000,
                 screen_x_offset=0, screen_y_offset=0,
                 invert_colors=False):
        self.disp = disp
        self.screen_width = screen_width or disp.width
        self.screen_height = screen_height or disp.height
        self.screen_x_offset = screen_x_offset
        self.screen_y_offset = screen_y_offset
        self.background = None
        self.background_color = background_color 
        self.handles = []
        self.invert_colors = invert_colors  
        self.band_height = band_height  
        self._band_buf = self._allocate_band_buffer(band_height)
        self._invert_buf = None
        self._bg_color_pair = bytes([
            (background_color >> 8) & 0xFF, background_color & 0xFF])

    def _allocate_band_buffer(self, requested_band_height):
        height = requested_band_height
        last_error = None
        while height >= 1:
            try:
                buf = bytearray(self.screen_width * height * 2)
                if height != requested_band_height:
                    print("Scene: band_height {} didn't fit in available "
                          "heap (fragmentation) - using {} instead".format(
                              requested_band_height, height))
                self.band_height = height
                return buf
            except MemoryError as e:
                last_error = e
                height = height // 2
        raise last_error

    def set_background(self, sprite):
        if sprite.width != self.screen_width:
            raise SpriteError(
                "background width {} != screen width {}".format(
                    sprite.width, self.screen_width))
        if sprite.height > self.screen_height:
            raise SpriteError(
                "background height {} is taller than screen height {}".format(
                    sprite.height, self.screen_height))
        self.background = sprite

    def add_sprite(self, sprite, x, y, z=0, visible=True):
        handle = SpriteHandle(sprite, x, y, z, visible)
        self.handles.append(handle)
        return handle

    def remove_sprite(self, handle):
        self.handles.remove(handle)

    def _fill_color_inplace(self, buf, start, length):
        if length <= 0:
            return
        pair = self._bg_color_pair
        buf[start:start + 2] = pair
        filled = 2
        while filled < length:
            take = min(filled, length - filled)
            buf[start + filled:start + filled + take] = buf[start:start + take]
            filled += take

    def _composite_band(self, band_y0, band_h):
        """Fill self._band_buf with background + all overlapping sprites
        for the horizontal strip [band_y0, band_y0+band_h)."""
        buf = self._band_buf
        bw = self.screen_width
        if self.background is not None:
            bg = self.background
            rows_available = max(0, min(band_h, bg.height - band_y0))
            if rows_available > 0:
                bulk = bg.get_rows(band_y0, rows_available)
                buf[0:len(bulk)] = bulk
            if rows_available < band_h:
                gap_start = rows_available * bw * 2
                gap_len = (band_h - rows_available) * bw * 2
                self._fill_color_inplace(buf, gap_start, gap_len)
        else:
            self._fill_color_inplace(buf, 0, len(buf))
        ordered = sorted(
            (h for h in self.handles if h.visible and h.sprite is not None),
            key=lambda h: h.z,
        )
        for h in ordered:
            sp = h.sprite
            x0, y0, x1, y1 = h.bbox()
            band_y1 = band_y0 + band_h
            if y1 <= band_y0 or y0 >= band_y1:
                continue
            if x1 <= 0 or x0 >= bw:
                continue

            row_start = max(0, band_y0 - y0)        
            row_end = min(sp.height, band_y1 - y0) 
            col_start = max(0, -x0)                 
            col_end = min(sp.width, bw - x0)       
            if col_end <= col_start:
                continue

            key = sp.key
            has_key = sp.has_transparency
            row_runs = sp._row_runs  

            for sy in range(row_start, row_end):
                dest_y = y0 + sy - band_y0
                dest_row_offset = dest_y * bw * 2

                if not has_key:
                    src_row = sp.get_row(sy)
                    src_start = col_start * 2
                    src_end = col_end * 2
                    dest_start = dest_row_offset + (x0 + col_start) * 2
                    buf[dest_start:dest_start + (src_end - src_start)] = \
                        src_row[src_start:src_end]
                elif row_runs is not None:
                    src_row = None 
                    for run_start, run_end in row_runs[sy]:
                        rs = max(run_start, col_start)
                        re = min(run_end, col_end)
                        if re <= rs:
                            continue
                        if src_row is None:
                            src_row = sp.get_row(sy)
                        dest_start = dest_row_offset + (x0 + rs) * 2
                        buf[dest_start:dest_start + (re - rs) * 2] = \
                            src_row[rs * 2:re * 2]
                else:
                    src_row = sp.get_row(sy)
                    key_hi = (key >> 8) & 0xFF
                    key_lo = key & 0xFF
                    run_start = None
                    for sx in range(col_start, col_end):
                        off = sx * 2
                        is_key = (src_row[off] == key_hi and
                                  src_row[off + 1] == key_lo)
                        if is_key:
                            if run_start is not None:
                                rs2 = run_start * 2
                                re2 = sx * 2
                                dest_start = (dest_row_offset +
                                              (x0 + run_start) * 2)
                                buf[dest_start:dest_start + (re2 - rs2)] = \
                                    src_row[rs2:re2]
                                run_start = None
                        else:
                            if run_start is None:
                                run_start = sx
                    if run_start is not None:
                        rs2 = run_start * 2
                        re2 = col_end * 2
                        dest_start = dest_row_offset + (x0 + run_start) * 2
                        buf[dest_start:dest_start + (re2 - rs2)] = \
                            src_row[rs2:re2]

    def render(self):
        y = 0
        bh = self.band_height
        sh = self.screen_height
        xoff = self.screen_x_offset
        yoff = self.screen_y_offset
        while y < sh:
            this_band_h = min(bh, sh - y)
            self._composite_band(y, this_band_h)
            if this_band_h == bh:
                buf_to_send = self._band_buf
            else:
                buf_to_send = memoryview(self._band_buf)[
                    :self.screen_width * this_band_h * 2]
            if self.invert_colors:
                buf_to_send = self._invert_into(buf_to_send)
            self.disp.block(xoff, yoff + y,
                             xoff + self.screen_width - 1,
                             yoff + y + this_band_h - 1,
                             buf_to_send)
            y += this_band_h

    def _invert_into(self, buf):
        n = len(buf)
        if self._invert_buf is None or len(self._invert_buf) < n:
            self._invert_buf = bytearray(len(self._band_buf))
        out = self._invert_buf
        for i in range(n):
            out[i] = buf[i] ^ 0xFF
        return memoryview(out)[:n] if n != len(out) else out
