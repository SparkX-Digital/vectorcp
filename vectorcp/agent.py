"""Bounded Unix-socket transport for the privileged control-plane agent."""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import socketserver
import stat
import struct
import threading
import traceback

from .core import Engine, Fault

MAX_REQUEST = 2 * 1024 * 1024
MAX_RESPONSE = 9 * 1024 * 1024


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        try:
            if not self.server.engine.development:
                credentials = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                _, uid, _ = struct.unpack("3i", credentials)
                if uid not in (0, self.server.web_uid):
                    return
            raw = self.rfile.readline(MAX_REQUEST + 1)
            if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
                raise Fault("Request is too large or incomplete.", 413)
            request = json.loads(raw)
            result = {"ok": True, "result": self.server.engine.dispatch(request)}
        except Fault as error:
            result = {"ok": False, "status": error.status, "error": str(error)}
        except (ValueError, UnicodeDecodeError):
            result = {"ok": False, "status": 400, "error": "Malformed request."}
        except Exception:
            traceback.print_exc()
            result = {"ok": False, "status": 500, "error": "The operation failed. Inspect the agent log."}
        encoded = json.dumps(result, ensure_ascii=False).encode() + b"\n"
        if len(encoded) > MAX_RESPONSE:
            encoded = b'{"ok":false,"status":413,"error":"Response exceeds the release limit."}\n'
        self.wfile.write(encoded)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, path, engine, web_uid):
        self.engine, self.web_uid = engine, web_uid
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(str(path), Handler)

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


def rpc(path, request):
    encoded = json.dumps(request, ensure_ascii=False).encode() + b"\n"
    if len(encoded) > MAX_REQUEST:
        raise Fault("Request exceeds the release limit.", 413)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(45)
        client.connect(str(path))
        client.sendall(encoded)
        with client.makefile("rb") as stream:
            response = stream.readline(MAX_RESPONSE + 1)
    if len(response) > MAX_RESPONSE or not response.endswith(b"\n"):
        raise Fault("The agent returned an invalid response.", 503)
    result = json.loads(response)
    if not result.get("ok"):
        raise Fault(result.get("error", "Agent operation failed."), result.get("status", 500))
    return result["result"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="/var/lib/vectorcp")
    parser.add_argument("--sites", default="/srv/vectorcp/sites")
    parser.add_argument("--socket", default="/run/vectorcp/agent.sock")
    parser.add_argument("--nginx", default="/etc/nginx/conf.d")
    parser.add_argument("--web-user", default="vectorcp-web")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--setup-token", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if not args.development and (os.geteuid() != 0 or not hasattr(socket, "SO_PEERCRED")):
        parser.error("Production mode requires root on Linux.")
    engine = Engine(args.state, args.sites, args.nginx, args.development)
    if args.setup_token:
        print(engine.setup_token())
        return
    web_uid = os.getuid() if args.development else pwd.getpwnam(args.web_user).pw_uid
    path = Path(args.socket).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if not stat.S_ISSOCK(path.lstat().st_mode):
            parser.error("The socket path is occupied by a non-socket file.")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                parser.error("An agent is already listening.")
    with Server(path, engine, web_uid) as server:
        if not args.development:
            os.chown(path, 0, pwd.getpwnam(args.web_user).pw_gid)
        os.chmod(path, 0o660 if not args.development else 0o600)
        print("VectorCP agent ready", flush=True)
        try:
            server.serve_forever()
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
