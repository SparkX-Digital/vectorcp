"""Create disposable preview records; generated passwords stay off disk.

Capture stdout in a calling process's memory. Never use these records in the VPS
installation. This refuses to alter an existing instance.
"""
import argparse
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veyra.core import Engine

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True)
args = parser.parse_args()
data = Path(args.data).absolute()
engine = Engine(data / "state", data / "sites", development=True)
password = secrets.token_urlsafe(28)
admin = engine.bootstrap({"setup_token": engine.setup_token(), "username": "previewadmin", "name": "Local preview", "password": password})


def call(method, values):
    return engine.dispatch({"method": method, "data": values, "token": admin["token"], "csrf": admin["csrf"]})


call("accounts.create", {"username": "studio", "name": "Example Studio", "password": secrets.token_urlsafe(28)})
owner = next(a["id"] for a in call("accounts.list", {})["accounts"] if a["username"] == "studio")
call("sites.create", {"domain": "studio.example.com", "user_id": owner})
site_id = call("sites.create", {"domain": "journal.example.com"})["id"]
call("backups.create", {"site_id": site_id})
print(json.dumps({"username": "previewadmin", "password": password}))
