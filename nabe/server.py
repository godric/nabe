import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

from nabe import store, system

LOGGER = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json",
}
# Everything in static/ by its name, the page at /
STATIC = {f"/{f.name}": (TYPES[f.suffix], f.read_bytes()) for f in STATIC_DIR.iterdir() if f.suffix in TYPES}
STATIC["/"] = STATIC.pop("/index.html")
JSON = "application/json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path  # without any ?query
        if path == "/api/devices":
            self.reply(JSON, json.dumps(store.snapshot()).encode())
        elif path in STATIC:
            self.reply(*STATIC[path])
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/probe":
            store.probe_requested.set()
        elif self.path == "/api/wake":
            try:
                mac = self.body()["mac"]
                system.wake(mac)
            except ValueError, KeyError, TypeError:
                self.send_error(400)
                return
            except OSError:
                LOGGER.exception("Couldn't send the magic packet")
                self.send_error(500)
                return
            LOGGER.info("Sent a magic packet to %s", mac)
        else:
            self.send_error(404)
            return
        self.reply(JSON, b"{}")

    def do_PUT(self):
        if self.path != "/api/layout":
            self.send_error(404)
            return
        try:
            store.save_layout(self.body())
        except ValueError, KeyError, TypeError, AttributeError:
            self.send_error(400)
            return
        self.reply(JSON, b"{}")

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))

    def reply(self, ctype, body):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        LOGGER.debug(fmt, *args)
