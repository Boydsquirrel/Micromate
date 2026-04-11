import usocket
import uselect
import os
import gc
import time
import network
from machine import Pin

# Config
BTN_STOP_PIN   = 0           # GPIO for stop button (active-low / pull-up)
SERVER_PORT    = 80          # Falls back to 8080 if 80 is busy
MAX_UPLOAD     = 180 * 1024  # 180 KB max upload body (leave ~20 KB headroom)
MAX_VIEW       = 6  * 1024   # 6 KB max text preview
MAX_LIST_ITEMS = 150         # Max entries shown in a directory listing
MEM_MIN        = 12 * 1024   # Reject request if free RAM below this

BG    = 0x0000
WHITE = 0xFFFF
GREEN = 0x07E0
RED   = 0xF800
CYAN  = 0x07FF
YELL  = 0xFFE0
GRAY  = 0x7BEF
DBLUE = 0x000F


def run(disp):

    def cls():
        disp.fill_rectangle(0, 0, 320, 240, BG)

    def txt(s, x, y, col=WHITE):
        s = str(s)[:40]
        if s:
            disp.draw_text8x8(x, y, s, col, BG)

    def stat_bar(msg, col=WHITE):
        disp.fill_rectangle(0, 220, 320, 20, BG)
        msg = str(msg)[:40]
        if msg:
            disp.draw_text8x8(0, 224, msg, col, BG)

    def update_stats(req_count):
        disp.fill_rectangle(0, 110, 320, 72, BG)
        txt("Requests:  " + str(req_count), 10, 114, WHITE)
        try:
            txt("Root files: " + str(len(os.listdir('/'))), 10, 130, WHITE)
        except:
            pass
        txt("Free RAM:  " + str(gc.mem_free() // 1024) + " KB", 10, 146, GRAY)

    # WiFi check
    wlan = network.WLAN(network.STA_IF)
    cls()
    if not wlan.isconnected():
        txt("No WiFi connection!", 10, 100, RED)
        txt("Connect WiFi first.", 10, 116, GRAY)
        time.sleep(3)
        return

    ip = wlan.ifconfig()[0]

    disp.fill_rectangle(0, 0, 320, 18, DBLUE)
    txt("WEBSERVER", 4, 5, CYAN)
    txt("IP:  " + ip,        10, 24, GREEN)
    txt("URL: http://" + ip, 10, 40, YELL)
    disp.fill_rectangle(0, 55, 320, 1, GRAY)
    txt("BOOT btn: stop",     10, 60, GRAY)
    disp.fill_rectangle(0, 74, 320, 1, GRAY)

    try:
        btn_stop = Pin(BTN_STOP_PIN, Pin.IN, Pin.PULL_UP)
    except:
        btn_stop = None

    srv = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
    srv.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
    port = SERVER_PORT
    try:
        srv.bind(('', port))
    except:
        port = 8080
        srv.bind(('', port))

    srv.listen(2)
    srv.setblocking(False)

    if port != 80:
        txt("Port 80 busy -> 8080", 10, 78, YELL)
        txt("URL: http://{}:8080".format(ip), 10, 40, YELL)

    txt("Status: RUNNING", 10, 82, GREEN)
    req_count = 0
    update_stats(req_count)

    # URL helpers
    def urldec(s):
        out = []
        i = 0
        s = s.replace('+', ' ')
        while i < len(s):
            if s[i] == '%' and i + 2 < len(s):
                try:
                    out.append(chr(int(s[i+1:i+3], 16)))
                    i += 3
                    continue
                except:
                    pass
            out.append(s[i])
            i += 1
        return ''.join(out)

    def parse_qs(qs):
        d = {}
        if not qs:
            return d
        for pair in qs.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                d[urldec(k)] = urldec(v)
        return d

    def htmlesc(s):
        return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

    def urlenc(s):
        safe = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/=')
        return ''.join([c if c in safe else '%{:02X}'.format(ord(c)) for c in str(s)])

    # ── Chunked send — PRIMARY ENOBUFS FIX ───────────────────────────────────
    # Never pass a large buffer to conn.send() directly.
    # send_all() breaks it into CHUNK-byte pieces and retries on ENOBUFS (105).
    CHUNK = 512

    def send_all(conn, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        mv    = memoryview(data)
        total = len(mv)
        sent  = 0
        while sent < total:
            retries = 0
            while retries < 20:
                try:
                    n = conn.send(mv[sent:sent + CHUNK])
                    sent += n
                    break
                except OSError as e:
                    if e.args[0] == 105:   # ENOBUFS
                        time.sleep_ms(10)
                        retries += 1
                    else:
                        raise
            else:
                raise OSError(105, 'send buffer full after retries')

    # HTTP helpers
    def send_headers(conn, code=200, ct='text/html', length=None, extra=''):
        phrases = {200:'OK', 302:'Found', 400:'Bad Request',
                   404:'Not Found', 413:'Payload Too Large',
                   503:'Service Unavailable', 500:'Internal Server Error'}
        h  = 'HTTP/1.1 {} {}\r\n'.format(code, phrases.get(code, 'OK'))
        h += 'Content-Type: {}; charset=utf-8\r\n'.format(ct)
        if extra:
            h += extra          # caller ensures trailing \r\n
        if length is not None:
            h += 'Content-Length: {}\r\n'.format(length)
        h += 'Connection: close\r\n\r\n'
        send_all(conn, h)

    def send_str(conn, code, ct, body):
        b = body.encode('utf-8')
        send_headers(conn, code, ct, len(b))
        send_all(conn, b)

    def redirect(conn, loc):
        send_all(conn,
            'HTTP/1.1 302 Found\r\nLocation: {}\r\nConnection: close\r\n\r\n'.format(loc))

    # Minimal CSS
    CSS = ('<style>'
           '*{box-sizing:border-box}'
           'body{font-family:monospace;background:#0d0d0d;color:#bbb;margin:0;padding:8px}'
           'h2{color:#0ff;margin:4px 0 10px;border-bottom:1px solid #222;padding-bottom:4px}'
           'nav a{display:inline-block;padding:3px 8px;border:1px solid #0a0;color:#0c0;'
           'text-decoration:none;margin:2px;font-size:.8em}'
           'nav a:hover{background:#0c0;color:#000}'
           'a.b{padding:2px 6px;border:1px solid #555;color:#aaa;text-decoration:none;'
           'font-size:.8em;margin:1px}'
           'a.b:hover{background:#555;color:#fff}'
           'a.d{border-color:#833;color:#c44}'
           'a.d:hover{background:#c44;color:#fff}'
           'table{width:100%;border-collapse:collapse;font-size:.82em}'
           'th{background:#1a1a1a;color:#0ff;padding:4px 6px;text-align:left}'
           'td{padding:3px 6px;border-bottom:1px solid #1c1c1c}'
           'tr:hover td{background:#141414}'
           '.card{background:#141414;padding:8px;margin:6px 0;border-left:3px solid #0a0}'
           'input[type=text],input[type=file]{background:#161616;color:#0d0;border:1px solid #444;'
           'padding:5px;width:100%;margin:4px 0}'
           'input[type=submit]{background:#161616;color:#0c0;border:1px solid #0a0;'
           'padding:5px 14px;cursor:pointer;margin-top:6px}'
           'input[type=submit]:hover{background:#0c0;color:#000}'
           'pre{background:#111;padding:8px;overflow:auto;max-height:65vh;font-size:.8em;'
           'border:1px solid #222;white-space:pre-wrap;word-break:break-all}'
           'progress{width:100%;height:8px;accent-color:#0c0}'
           '.w{color:#fa0;font-size:.8em}.ok{color:#0c0}.er{color:#c44}'
           'footer{color:#333;font-size:.72em;margin-top:14px;'
           'border-top:1px solid #1a1a1a;padding-top:6px}'
           '</style>')

    NAV = ('<nav>'
           '<a href="/">Files</a> '
           '<a href="/upload">Upload</a> '
           '<a href="/sysinfo">Sysinfo</a> '
           '<a href="/mkdir">New Dir</a>'
           '</nav>')

    def page_head(title):
        return ('<!DOCTYPE html><html><head>'
                '<meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>{t}</title>' + CSS +
                '</head><body>' + NAV +
                '<h2>{t}</h2>').replace('{t}', htmlesc(title))

    PAGE_FOOT = '<footer>MicroMate WebServer &mdash; {}</footer></body></html>'.format(ip)

    # Stream a page in pieces — body_parts is an iterable of strings.
    # Nothing is ever held as one giant string; each part is sent as it's built.
    def stream_page(conn, title, body_parts):
        send_headers(conn, 200, 'text/html')
        send_all(conn, page_head(title))
        for part in body_parts:
            if part:
                send_all(conn, part)
        send_all(conn, PAGE_FOOT)

    def error_page(conn, code, msg):
        title = 'Error {}'.format(code)
        send_str(conn, code, 'text/html',
                 page_head(title) + '<p class="er">{}</p>'.format(htmlesc(msg)) + PAGE_FOOT)

    # File listing — generator so rows are built and sent one at a time
    def gen_file_rows(browse_path):
        yield '<p style="color:#555;font-size:.85em">Path: <b style="color:#aaa">{}</b></p>'.format(
            htmlesc(browse_path))
        yield '<table><tr><th>Name</th><th>Bytes</th><th>Actions</th></tr>'

        if browse_path != '/':
            parent = '/'.join(browse_path.rstrip('/').split('/')[:-1]) or '/'
            yield '<tr><td><a class="b" href="/browse?p={}">&uarr; ..</a></td><td></td><td></td></tr>'.format(
                urlenc(parent))

        try:
            items = sorted(os.listdir(browse_path))
        except Exception as e:
            yield '<tr><td colspan="3" class="er">Cannot list: {}</td></tr></table>'.format(htmlesc(str(e)))
            return

        if len(items) > MAX_LIST_ITEMS:
            yield '<tr><td colspan="3" class="w">Showing first {} of {} items.</td></tr>'.format(
                MAX_LIST_ITEMS, len(items))
            items = items[:MAX_LIST_ITEMS]

        for name in items:
            fp  = browse_path.rstrip('/') + '/' + name
            enc = urlenc(fp)
            try:
                st  = os.stat(fp)
                isd = bool(st[0] & 0x4000)
                sz  = '&mdash;' if isd else '{:,}'.format(st[6])
            except:
                isd = False
                sz  = '?'

            cell = ('<a class="b" href="/browse?p={}">[{}]</a>'.format(enc, htmlesc(name))
                    if isd else htmlesc(name))
            acts = ''
            if not isd:
                acts += '<a class="b" href="/dl?p={}">DL</a> '.format(enc)
                acts += '<a class="b" href="/view?p={}">View</a> '.format(enc)
            acts += '<a class="b d" href="/del?p={}" onclick="return confirm(\'Delete {}?\')">Del</a>'.format(
                enc, htmlesc(name))

            yield '<tr><td>{}</td><td style="color:#555">{}</td><td>{}</td></tr>'.format(cell, sz, acts)
            gc.collect()  # per-row collect prevents OOM on large directories

        enc_path = urlenc(browse_path)
        yield '</table>'
        yield ('<p style="margin-top:8px">'
               '<a class="b" href="/upload?p={}">Upload here</a> '
               '<a class="b" href="/mkdir?p={}">New dir here</a></p>').format(enc_path, enc_path)

    def sysinfo_body():
        cfg   = wlan.ifconfig()
        free  = gc.mem_free()
        used  = gc.mem_alloc()
        total = free + used
        b  = '<div class="card"><b>Network</b><br>IP: {} &nbsp; Mask: {} &nbsp; GW: {}</div>'.format(
            cfg[0], cfg[1], cfg[2])
        b += ('<div class="card"><b>RAM</b><br>Free: {} KB &nbsp; Used: {} KB<br>'
              '<progress value="{}" max="{}"></progress></div>').format(
            free//1024, used//1024, used, total)
        try:
            sv = os.statvfs('/')
            tb = sv[0] * sv[2]
            fb = sv[0] * sv[3]
            b += ('<div class="card"><b>Flash</b><br>Total: {} KB &nbsp; '
                  'Used: {} KB &nbsp; Free: {} KB<br>'
                  '<progress value="{}" max="{}"></progress></div>').format(
                tb//1024, (tb-fb)//1024, fb//1024, tb-fb, tb)
        except:
            pass
        b += '<div class="card"><b>Server</b><br>Requests: {} &nbsp; Max upload: {} KB</div>'.format(
            req_count, MAX_UPLOAD//1024)
        try:
            b += '<div class="card"><b>Root</b><br>{}</div>'.format(
                ', '.join(htmlesc(i) for i in sorted(os.listdir('/'))))
        except:
            pass
        return b

    # Multipart parser
    def parse_multipart(data, ct):
        if 'boundary=' not in ct:
            return []
        raw_b    = ct.split('boundary=')[1].strip().strip('"')
        boundary = ('--' + raw_b).encode()
        parts    = []
        for seg in bytes(data).split(boundary)[1:]:
            if seg.startswith(b'--'):
                break
            if seg.startswith(b'\r\n'):
                seg = seg[2:]
            hdr_end = seg.find(b'\r\n\r\n')
            if hdr_end < 0:
                continue
            hdr_raw = seg[:hdr_end].decode('utf-8', 'ignore')
            content = seg[hdr_end + 4:]
            if content.endswith(b'\r\n'):
                content = content[:-2]
            hdrs = {}
            for line in hdr_raw.split('\r\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    hdrs[k.strip().lower()] = v.strip()
            parts.append((hdrs, content))
            gc.collect()
        return parts

    # Request handler
    def handle(conn):
        nonlocal req_count

        gc.collect()  # collect BEFORE allocating anything for this request

        # Memory guard
        if gc.mem_free() < MEM_MIN:
            gc.collect()
            if gc.mem_free() < MEM_MIN:
                try:
                    send_str(conn, 503, 'text/plain',
                             'Low memory ({} B free). Try again.'.format(gc.mem_free()))
                except:
                    pass
                return

        try:
            conn.settimeout(8.0)

            # Read headers (cap at 8 KB)
            raw = bytearray()
            while b'\r\n\r\n' not in raw:
                chunk = conn.recv(512)
                if not chunk:
                    break
                raw += chunk
                if len(raw) > 8192:
                    break

            sep = bytes(raw).find(b'\r\n\r\n')
            if sep < 0:
                return

            hdr_raw = raw[:sep].decode('utf-8', 'ignore')
            body    = bytearray(raw[sep + 4:])  # bytearray from the start
            del raw
            gc.collect()

            lines    = hdr_raw.split('\r\n')
            req_line = lines[0].split(' ')
            if len(req_line) < 2:
                return

            method    = req_line[0]
            full_path = req_line[1]
            path, _, qs = full_path.partition('?')
            query = parse_qs(qs)

            hdrs = {}
            for line in lines[1:]:
                if ':' in line:
                    k, v = line.split(':', 1)
                    hdrs[k.strip().lower()] = v.strip()

            content_length = int(hdrs.get('content-length', 0))

            req_count += 1
            stat_bar(method + ' ' + path[:28], CYAN)

            # GET
            if method == 'GET':

                if path in ('/', '/browse'):
                    browse_p = urldec(query.get('p', '/'))
                    stream_page(conn, 'Files: ' + browse_p, gen_file_rows(browse_p))

                elif path == '/upload':
                    dest = urldec(query.get('p', '/'))
                    stream_page(conn, 'Upload', [
                        '<form method="POST" action="/upload" enctype="multipart/form-data">'
                        '<input type="hidden" name="dest" value="{}">'.format(htmlesc(dest)),
                        '<div class="card"><p>Upload to: <b>{}</b></p>'.format(htmlesc(dest)),
                        '<input type="file" name="file" multiple><br>',
                        '<input type="submit" value="Upload"></div></form>',
                        '<p class="w">Max ~{} KB per request (ESP32 RAM limit).</p>'.format(MAX_UPLOAD // 1024)
                    ])

                elif path == '/mkdir':
                    dest = urldec(query.get('p', '/'))
                    stream_page(conn, 'New Directory', [
                        '<form method="POST" action="/mkdir">'
                        '<input type="hidden" name="dest" value="{}">'.format(htmlesc(dest)),
                        '<div class="card"><p>Create directory inside: <b>{}</b></p>'.format(htmlesc(dest)),
                        '<input type="text" name="name" placeholder="folder name" autocomplete="off"><br>',
                        '<input type="submit" value="Create"></div></form>'
                    ])

                elif path == '/sysinfo':
                    stream_page(conn, 'System Info', [sysinfo_body()])

                elif path == '/view':
                    fp = urldec(query.get('p', ''))
                    if not fp:
                        error_page(conn, 400, 'Missing p param')
                        return
                    try:
                        st = os.stat(fp)
                        sz = st[6]
                    except Exception as e:
                        error_page(conn, 404, str(e))
                        return
                    fname = fp.split('/')[-1]
                    try:
                        with open(fp, 'rb') as f:
                            raw_data = f.read(MAX_VIEW)
                        pct = sum(1 for b in raw_data if 32 <= b < 127 or b in (9, 10, 13))
                        is_text = len(raw_data) == 0 or (pct / len(raw_data)) > 0.85
                        if is_text:
                            parts = []
                            if sz > MAX_VIEW:
                                parts.append('<p class="w">Showing first {} KB of {} KB.</p>'.format(
                                    MAX_VIEW//1024, sz//1024))
                            parts.append('<pre>' + htmlesc(raw_data.decode('utf-8','replace')) + '</pre>')
                        else:
                            parts = ['<p class="w">Binary file ({} bytes) — download to inspect.</p>'.format(sz)]
                    except Exception as e:
                        parts = ['<p class="er">Read error: {}</p>'.format(htmlesc(str(e)))]
                    parts.append('<a class="b" href="/dl?p={}">Download</a>'.format(urlenc(fp)))
                    stream_page(conn, 'View: ' + htmlesc(fname), parts)

                elif path == '/dl':
                    fp = urldec(query.get('p', ''))
                    if not fp:
                        error_page(conn, 400, 'Missing p param')
                        return
                    try:
                        st    = os.stat(fp)
                        size  = st[6]
                        fname = fp.split('/')[-1]
                        send_headers(conn, 200, 'application/octet-stream', size,
                                     'Content-Disposition: attachment; filename="{}"\r\n'.format(fname))
                        with open(fp, 'rb') as f:
                            while True:
                                chunk = f.read(CHUNK)
                                if not chunk:
                                    break
                                send_all(conn, chunk)
                    except Exception as e:
                        error_page(conn, 404, 'Not found: ' + str(e))

                elif path == '/del':
                    fp = urldec(query.get('p', ''))
                    if not fp:
                        error_page(conn, 400, 'Missing p param')
                        return
                    try:
                        st  = os.stat(fp)       # verify exists first
                        isd = bool(st[0] & 0x4000)
                    except Exception as e:
                        error_page(conn, 404, 'Path not found: ' + str(e))
                        return
                    try:
                        os.rmdir(fp) if isd else os.remove(fp)
                        parent = '/'.join(fp.rstrip('/').split('/')[:-1]) or '/'
                        redirect(conn, '/browse?p=' + urlenc(parent))
                    except Exception as e:
                        error_page(conn, 500, 'Delete error: ' + str(e))

                else:
                    error_page(conn, 404, 'Page not found.')

            # POST
            elif method == 'POST':

                if content_length > MAX_UPLOAD:
                    send_str(conn, 413, 'text/plain',
                             'Body too large. Max {} KB.'.format(MAX_UPLOAD // 1024))
                    return

                # Read remaining body into bytearray (avoids O(n^2) bytes concat)
                stat_bar('Reading {}B...'.format(content_length), YELL)
                remaining = content_length - len(body)
                while remaining > 0:
                    chunk = conn.recv(min(1024, remaining))
                    if not chunk:
                        break
                    body += chunk
                    remaining -= len(chunk)

                ct = hdrs.get('content-type', '')

                if path == '/upload':
                    parts  = parse_multipart(body, ct)
                    dest   = '/'
                    saved  = []
                    errors = []

                    # Pass 1: find destination field
                    for (ph, pc) in parts:
                        if 'name="dest"' in ph.get('content-disposition', ''):
                            dest = pc.decode('utf-8', 'ignore').strip()
                            break

                    # Pass 2: save files
                    for (ph, pc) in parts:
                        cd = ph.get('content-disposition', '')
                        if 'filename="' in cd:
                            try:
                                raw_fname = cd.split('filename="')[1].split('"')[0].strip()
                                fname = (raw_fname or 'upload.bin').replace('/', '_').replace('\\', '_').replace('..', '_')
                                fp = dest.rstrip('/') + '/' + fname
                                with open(fp, 'wb') as f:
                                    f.write(pc)
                                saved.append((fname, len(pc)))
                            except Exception as e:
                                errors.append(str(e))
                            gc.collect()

                    del body    # free upload body before building response
                    del parts
                    gc.collect()
                    update_stats(req_count)

                    if saved:
                        stat_bar('Saved: ' + ', '.join(s[0] for s in saved), GREEN)
                        rows = ''.join('<tr><td class="ok">{}</td><td>{:,} B</td></tr>'.format(
                            htmlesc(n), sz) for n, sz in saved)
                        errs = ''.join('<p class="er">{}</p>'.format(htmlesc(e)) for e in errors)
                        stream_page(conn, 'Upload OK', [
                            '<table><tr><th>File</th><th>Size</th></tr>{}</table>{}'.format(rows, errs),
                            '<p><a class="b" href="/browse?p={}">Back to Files</a></p>'.format(urlenc(dest))
                        ])
                    else:
                        err_msg = '; '.join(errors) if errors else 'No file data found in request.'
                        stream_page(conn, 'Upload Failed', [
                            '<p class="er">{}</p>'.format(htmlesc(err_msg)),
                            '<a class="b" href="/upload">Try again</a>'
                        ])

                elif path == '/mkdir':
                    params  = parse_qs(body.decode('utf-8', 'ignore'))
                    dest    = params.get('dest', '/')
                    dirname = params.get('name', '').strip().replace('/', '').replace('\\', '').replace('..', '')
                    del body
                    gc.collect()
                    if not dirname:
                        error_page(conn, 400, 'No directory name given')
                    else:
                        try:
                            os.mkdir(dest.rstrip('/') + '/' + dirname)
                            redirect(conn, '/browse?p=' + urlenc(dest))
                        except Exception as e:
                            error_page(conn, 500, 'mkdir error: ' + str(e))

                else:
                    error_page(conn, 404, 'Not found')

            else:
                error_page(conn, 400, 'Method not supported')

        except OSError as e:
            # Log to display but don't try to send — connection may be broken.
            stat_bar('OSError {}: {}'.format(e.args[0], str(e)[:15]), RED)
        except Exception as e:
            stat_bar('Err: ' + str(e)[:28], RED)
            try:
                error_page(conn, 500, 'Server error: ' + str(e))
            except:
                pass
        finally:
            try:
                conn.close()
            except:
                pass
            gc.collect()

    # Event loop
    poll = uselect.poll()
    poll.register(srv, uselect.POLLIN)

    while True:
        if btn_stop is not None and btn_stop.value() == 0:
            stat_bar('Stopping server...', RED)
            time.sleep_ms(300)
            break

        events = poll.poll(150)
        for sock, ev in events:
            if ev & uselect.POLLIN:
                try:
                    conn, addr = srv.accept()
                    stat_bar('From: ' + addr[0], CYAN)
                    handle(conn)
                    update_stats(req_count)
                except Exception as e:
                    stat_bar('Accept err: ' + str(e)[:22], RED)

        gc.collect()

    # Cleanup
    try:
        poll.unregister(srv)
    except:
        pass
    try:
        srv.close()
    except:
        pass
    cls()
    txt('Server stopped.', 10, 110, RED)
    time.sleep(1)
