"""Small local web app: browse reels, download, copy captions, share, and auto-make reels every day."""
import contextlib
import datetime as dt
import io
import json
import mimetypes
import socket
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config

PAGE = Path(__file__).with_name("index.html")
state = {"running": False, "log": "", "last_auto": None}
lock = threading.Lock()


class _Tee(io.StringIO):
    def write(self, s):
        state["log"] = (state["log"] + s)[-6000:]
        return len(s)


def start_job(topics=None):
    with lock:
        if state["running"]:
            return False
        state["running"], state["log"] = True, ""

    def run():
        from .make import make_daily
        try:
            with contextlib.redirect_stdout(_Tee()):
                made = make_daily(topics=topics)
                print(f"\nDone: {len(made)} reel(s) made.")
        except BaseException as e:  # SystemExit from "no trends" included
            state["log"] += f"\nStopped: {e}"
        finally:
            state["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return True


def scheduler():
    """Makes the day's reels at DAILY_TIME while the app is open."""
    if not config.DAILY_TIME:
        return
    hh, mm = (int(x) for x in config.DAILY_TIME.split(":"))
    while True:
        now = dt.datetime.now()
        today = now.date().isoformat()
        already = any((config.OUTPUT_DIR / today).glob("[0-9][0-9]-*")) or state["last_auto"] == today
        if (now.hour, now.minute) >= (hh, mm) and not already:
            state["last_auto"] = today
            start_job()
        time.sleep(60)


def list_reels():
    reels = []
    for meta in sorted(config.OUTPUT_DIR.glob("*/*/meta.json"), reverse=True):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rel = meta.parent.relative_to(config.OUTPUT_DIR).as_posix()
        m["video_url"] = f"/files/{rel}/{m.get('video', 'reel.mp4')}"
        m["cover_url"] = f"/files/{rel}/{m.get('cover', 'cover.jpg')}"
        m["post_url"] = f"/files/{rel}/post.txt"
        m["id"] = rel
        reels.append(m)
    reels.sort(key=lambda m: (m.get("date", ""), -m.get("rank", 0)), reverse=True)
    return reels


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/reels":
            self._json({"reels": list_reels()})
        elif url.path == "/api/status":
            self._json({"running": state["running"], "log": state["log"], "settings": {
                "pexels": bool(config.PEXELS_API_KEY), "pixabay": bool(config.PIXABAY_API_KEY),
                "ai": bool(config.ANTHROPIC_API_KEY), "geo": config.GEO, "count": config.REELS_PER_DAY,
                "daily_time": config.DAILY_TIME, "handle": config.HANDLE}})
        elif url.path in ("/manifest.webmanifest", "/icon-192.png", "/icon-512.png"):
            from .site import write_app_files
            app_dir = config.CACHE_DIR / "app"
            write_app_files(app_dir)
            body = (app_dir / url.path[1:]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json" if url.path.endswith("manifest") else "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path.startswith("/files/"):
            self._file(urllib.parse.unquote(url.path[len("/files/"):]), "download=1" in url.query)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/make":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        topic = (data.get("topic") or "").strip()
        ok = start_job([topic] if topic else None)
        self._json({"started": ok})

    def _file(self, rel, download):
        base = config.OUTPUT_DIR.resolve()
        path = (base / rel).resolve()
        if base not in path.parents or not path.is_file():
            return self.send_error(404)
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if a and b else size - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if download:
            name = f"{path.parent.parent.name}-{path.parent.name}{path.suffix}"
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)


def serve(port=8765, lan=False):
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    host = "0.0.0.0" if lan else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=scheduler, daemon=True).start()
    print(f"Reel Maker is running at http://localhost:{port}")
    if lan:
        with contextlib.suppress(OSError):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            print(f"On your phone (same Wi-Fi): http://{s.getsockname()[0]}:{port}")
    if config.DAILY_TIME:
        print(f"New reels are made automatically every day at {config.DAILY_TIME} while this window stays open.")
    print("Press Ctrl+C to stop.")
    with contextlib.suppress(Exception):
        webbrowser.open(f"http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
