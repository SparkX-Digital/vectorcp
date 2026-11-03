"""An unprivileged HTTP frontend; state and authorization remain in the agent."""
import argparse
import base64
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from .agent import rpc
from .core import Fault

STATIC = Path(__file__).with_name("static")
ROUTES = {"/admin": ("index.html", "text/html; charset=utf-8"), "/reseller": ("index.html", "text/html; charset=utf-8"), "/customer": ("index.html", "text/html; charset=utf-8"), "/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
OPERATIONS = {"overview", "accounts.list", "accounts.create", "accounts.active", "sites.list", "sites.create", "sites.active",
              "files.list", "files.read", "files.write", "files.mkdir", "backups.list", "backups.create", "backups.download", "audit", "logout", "bootstrap", "login", "hosting.enable", "hosting.php", "hosting.wordpress", "hosting.tls", "databases.create", "databases.list", "databases.credentials", "jobs.list", "backups.full", "backups.restore", "backups.delete", "backups.describe", "backups.chunk", "plans.list", "plans.create", "plans.active", "plans.assign", "dns.list", "dns.create", "dns.save", "dns.delete", "dns.export", "dns.verify"}


class Handler(BaseHTTPRequestHandler):
    server_version = "VectorCP"
    sys_version = ""

    def log_message(self, format_string, *args):
        # Do not log query strings, cookies, request bodies or setup fragments.
        print("HTTP %s %s" % (self.command, getattr(self, "response_code", "-")), flush=True)

    def respond(self, status, payload, kind="application/json; charset=utf-8", cookie=None, filename=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.response_code = status
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(body)

    def origin_valid(self):
        expected = urlsplit(self.server.origin)
        host = self.headers.get("Host", "")
        return host == expected.netloc

    def do_GET(self):
        if not self.origin_valid():
            self.respond(400, {"error": "Unrecognized host."})
            return
        path = urlsplit(self.path).path
        if path == "/healthz":
            try:
                rpc(self.server.agent_socket, {"method": "health"})
                self.respond(200, {"service": "veyra-web", "ok": True, "agent": "ready"})
            except (Fault, OSError, ValueError):
                self.respond(503, {"service": "veyra-web", "ok": False, "agent": "unavailable"})
            return
        if path not in ROUTES:
            self.respond(404, {"error": "Page not found."})
            return
        filename, kind = ROUTES[path]
        self.respond(200, (STATIC / filename).read_bytes(), kind)

    def do_POST(self):
        if not self.origin_valid() or self.headers.get("Origin") != self.server.origin:
            self.respond(403, {"error": "Request origin verification failed."})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.respond(415, {"error": "Use a JSON request."})
            return
        if self.path != "/api":
            self.respond(404, {"error": "Operation not found."})
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if size < 0 or size > 2 * 1024 * 1024:
                raise Fault("Request is too large or incomplete.", 413)
            self.connection.settimeout(15)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or payload.get("method") not in OPERATIONS:
                raise Fault("Unknown operation.", 404)
            if payload["method"] in ("bootstrap", "login"):
                if not self.server.allow_auth_attempt():
                    raise Fault("Too many sign-in requests. Wait a minute and try again.", 429)
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies["veyra_session"].value if "veyra_session" in cookies else ""
            # Ignore role, user ID, token and CSRF claims in the request envelope.
            if payload['method'] == 'backups.download':
                self.download_backup(payload.get('data', {}), token)
                return
            result = rpc(self.server.agent_socket, {"method": payload["method"], "data": payload.get("data", {}),
                         "token": token, "csrf": self.headers.get("X-CSRF-Token", "")})
            set_cookie = None
            flags = "; HttpOnly; SameSite=Strict; Path=/" + ("; Secure" if self.server.origin.startswith("https://") else "")
            if payload["method"] in ("bootstrap", "login"):
                set_cookie = "veyra_session=" + result.pop("token") + "; Max-Age=28800" + flags
            elif payload["method"] == "logout":
                set_cookie = "veyra_session=; Max-Age=0" + flags
            if payload['method'] == 'backups.download':
                self.respond(200, base64.b64decode(result['base64']), 'application/gzip', filename=result['filename'])
            else:
                self.respond(200, result, cookie=set_cookie)
        except Fault as error:
            self.respond(error.status, {"error": str(error)})
        except (ValueError, TypeError):
            self.respond(400, {"error": "Invalid request."})
        except (OSError, TimeoutError):
            self.respond(503, {"error": "The server agent is unavailable. Check its service status."})

    def download_backup(self, data, token):
        envelope = {'token': token, 'csrf': self.headers.get('X-CSRF-Token', '')}
        description = rpc(self.server.agent_socket, dict(envelope, method='backups.describe', data=data))
        self.response_code = 200
        self.send_response(200)
        self.send_header('Content-Type', 'application/gzip')
        self.send_header('Content-Length', str(description['bytes']))
        self.send_header('Content-Disposition', 'attachment; filename="' + description['filename'] + '"')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        offset = 0
        while offset < description['bytes']:
            chunk = rpc(self.server.agent_socket, dict(envelope, method='backups.chunk', data=dict(data, offset=offset)))
            payload = base64.b64decode(chunk['base64'])
            if not payload:
                raise OSError('Backup stream ended early')
            self.wfile.write(payload)
            offset += len(payload)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, agent_socket, origin, development=False):
        self.agent_socket, self.origin, self.development = agent_socket, origin, development
        self.slots = threading.BoundedSemaphore(12)
        self.auth_lock = threading.Lock()
        self.auth_times = []
        super().__init__(address, Handler)

    def allow_auth_attempt(self):
        with self.auth_lock:
            now = time.monotonic()
            self.auth_times = [t for t in self.auth_times if now - t < 60]
            if len(self.auth_times) >= 20:
                return False
            self.auth_times.append(now)
            return True

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/veyrapanel/agent.sock")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--private", action="store_true", help="Allow HTTP only through a loopback SSH tunnel")
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    if origin.path or origin.query or origin.fragment or origin.username or origin.password or not origin.hostname:
        parser.error("Use an origin without a path, credentials, query or fragment.")
    if args.private and origin.hostname not in ("127.0.0.1", "localhost"):
        parser.error("Private HTTP mode requires a loopback origin.")
    if origin.scheme != ("http" if args.development or args.private else "https"):
        parser.error("Production requires an HTTPS origin; development uses HTTP.")
    with Server(("127.0.0.1", args.port), args.socket, args.origin, args.development) as server:
        print("VectorCP web ready at " + args.origin, flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
