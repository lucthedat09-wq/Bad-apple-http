#!/usr/bin/env python3
"""
Bad Apple 16x16 → 8-bit stream
Mỗi lần GET /read trả về {"value":"xxxxxxxx"} (8 bit)
"""

import http.server
import socketserver
import threading
import json
import os
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8080))
DATA_FILE = os.path.join(os.path.dirname(__file__), "badapple_16x16.txt")
TOTAL_FRAMES = 3205

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.playing = False
        self.current_frame = 0      # 0-based
        self.bit_pos = 0            # vị trí bit trong frame (0 → 255)
        self.frames = []            # mỗi frame là chuỗi 256 ký tự 0/1

    def load_frames(self):
        print("Loading frames...")
        with open(DATA_FILE, "r") as f:
            lines = [line.rstrip("\n") for line in f]

        self.frames = []
        for i in range(TOTAL_FRAMES):
            frame_lines = lines[i*16 : (i+1)*16]
            flat = "".join(frame_lines)          # 256 ký tự
            self.frames.append(flat)

        print(f"Loaded {len(self.frames)} frames")

    def get_next_8bit(self):
        """Trả về 8 bit tiếp theo + tự tăng vị trí"""
        with self.lock:
            frame = self.frames[self.current_frame]
            # Lấy 8 bit
            chunk = frame[self.bit_pos : self.bit_pos + 8]
            # Nếu thiếu (hiếm) thì pad 0
            chunk = chunk.ljust(8, "0")

            if self.playing:
                self.bit_pos += 8
                if self.bit_pos >= 256:
                    self.bit_pos = 0
                    self.current_frame = (self.current_frame + 1) % TOTAL_FRAMES

            return chunk

    def get_status(self):
        with self.lock:
            return {
                "frame": self.current_frame + 1,
                "total": TOTAL_FRAMES,
                "bit": self.bit_pos,
                "playing": self.playing
            }

    def start(self):
        with self.lock:
            self.playing = True

    def stop(self):
        with self.lock:
            self.playing = False

    def reset(self):
        with self.lock:
            self.current_frame = 0
            self.bit_pos = 0
            self.playing = False

    def set_frame(self, n):
        with self.lock:
            if 0 <= n < TOTAL_FRAMES:
                self.current_frame = n
                self.bit_pos = 0

state = State()

CONTROL_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bad Apple 8-bit Stream</title>
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e;
    --green: #3fb950; --red: #f85149; --blue: #58a6ff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; padding: 24px 16px;
  }
  h1 { font-size: 1.5rem; margin-bottom: 6px; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px; width: 100%; max-width: 400px;
  }
  .info { text-align: center; margin-bottom: 20px; }
  .frame-num { font-size: 2rem; font-weight: 700; }
  .frame-num span { color: var(--muted); font-size: 1rem; font-weight: 400; }
  .status { margin-top: 6px; font-size: 0.95rem; }
  .status.playing { color: var(--green); }
  .status.stopped { color: var(--red); }
  .btns { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
  button {
    border: none; border-radius: 8px; padding: 11px 24px;
    font-size: 1rem; font-weight: 600; cursor: pointer;
  }
  #btn-start { background: var(--green); color: #000; }
  #btn-stop  { background: var(--red); color: #fff; }
  #btn-reset { background: var(--border); color: var(--text); }
  .links { margin-top: 18px; font-size: 0.85rem; color: var(--muted); text-align: center; }
  .links code { background: #21262d; padding: 2px 6px; border-radius: 4px; color: var(--blue); }
  .note { margin-top: 12px; font-size: 0.8rem; color: var(--muted); text-align: center; }
</style>
</head>
<body>
  <h1>Bad Apple → 8-bit</h1>
  <p class="sub">Mỗi GET /read = 8 bit</p>

  <div class="card">
    <div class="info">
      <div class="frame-num">
        <span id="cur">1</span>
        <span>/ <span id="total">3205</span></span>
      </div>
      <div id="status" class="status stopped">● STOPPED</div>
      <div style="margin-top:4px;font-size:0.85rem;color:var(--muted)">
        Bit: <span id="bit">0</span>/256
      </div>
    </div>

    <div class="btns">
      <button id="btn-start" onclick="doStart()">▶ Start</button>
      <button id="btn-stop"  onclick="doStop()">■ Stop</button>
      <button id="btn-reset" onclick="doReset()">↺ Reset</button>
    </div>

    <p class="note">GET /read → {"value":"xxxxxxxx"} (8 bit)</p>
  </div>

  <div class="links">
    Transmitter: <code id="read-url"></code>
  </div>

<script>
async function fetchStatus() {
  try {
    const r = await fetch('/status');
    const j = await r.json();
    document.getElementById('cur').textContent = j.frame;
    document.getElementById('total').textContent = j.total;
    document.getElementById('bit').textContent = j.bit;
    const st = document.getElementById('status');
    if (j.playing) {
      st.textContent = '● PLAYING';
      st.className = 'status playing';
    } else {
      st.textContent = '● STOPPED';
      st.className = 'status stopped';
    }
  } catch(e) {}
}

async function doStart()  { await fetch('/start',  {method:'POST'}); fetchStatus(); }
async function doStop()   { await fetch('/stop',   {method:'POST'}); fetchStatus(); }
async function doReset()  { await fetch('/reset',  {method:'POST'}); fetchStatus(); }

document.getElementById('read-url').textContent = location.origin + '/read';
setInterval(fetchStatus, 400);
fetchStatus();
</script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/control":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(CONTROL_HTML.encode("utf-8"))

        elif path == "/read":
            bits = state.get_next_8bit()
            payload = json.dumps({"value": bits}, separators=(",", ":"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))

        elif path == "/status":
            data = json.dumps(state.get_status())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/start":
            state.start()
            self._ok()
        elif path == "/stop":
            state.stop()
            self._ok()
        elif path == "/reset":
            state.reset()
            self._ok()
        elif path == "/seek":
            qs = parse_qs(urlparse(self.path).query)
            try:
                f = int(qs.get("f", ["1"])[0]) - 1
                state.set_frame(f)
            except:
                pass
            self._ok()
        else:
            self.send_error(404)

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

def main():
    state.load_frames()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Bad Apple 8-bit stream running on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
