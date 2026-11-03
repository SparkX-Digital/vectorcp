"""Run an isolated, loopback-only local validation instance. No Linux changes."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Local runtime directory outside the deliverable source")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    data = Path(args.data).absolute()
    data.mkdir(parents=True, exist_ok=True)
    sock = Path("/private/tmp" if sys.platform == "darwin" else "/tmp") / ("vectorcp-preview-%d-%d.sock" % (os.getuid(), os.getpid()))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    project = str(Path(__file__).parent.absolute())
    agent = subprocess.Popen([sys.executable, "-m", "vectorcp.agent", "--development", "--state", str(data / "state"), "--sites", str(data / "sites"), "--socket", str(sock)], cwd=project)
    web = None

    def cleanup(*_):
        if web is not None:
            web.terminate()
        agent.terminate()
        for child in (web, agent):
            if child is not None:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
        sock.unlink(missing_ok=True)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        for _ in range(100):
            if sock.exists():
                break
            if agent.poll() is not None:
                raise RuntimeError("The development agent did not start.")
            time.sleep(0.05)
        else:
            raise RuntimeError("The agent readiness check timed out.")
        web = subprocess.Popen([sys.executable, "-m", "vectorcp.web", "--development", "--socket", str(sock), "--port", str(args.port), "--origin", "http://127.0.0.1:%d" % args.port], cwd=project)
        print("Local preview: http://127.0.0.1:%d" % args.port, flush=True)
        print("State: " + str(data), flush=True)
        while agent.poll() is None and web.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
