#!/usr/bin/env python3
"""Upgrade an existing installation from a locally reviewed source tree.

Default: check only. Does not download code, install dependencies or change SSH.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]
INSTALL = Path('/opt/veyrapanel')
STATE = Path('/var/lib/veyrapanel')


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=45)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    if os.geteuid() != 0 or sys.platform != 'linux' or not (INSTALL/'veyra').is_dir() or not (STATE/'control.sqlite3').is_file():
        raise SystemExit('Run as root on an existing VectorCP Linux installation.')
    if (SOURCE/'veyra').resolve() == (INSTALL/'veyra').resolve():
        raise SystemExit('Extract the reviewed release separately from the active installation.')
    for filename in ('core.py','agent.py','web.py','distribution.py','hosting.py','hosting_task.py','dns.py'):
        path = SOURCE/'veyra'/filename
        compile(path.read_text(),str(path),'exec')
    with sqlite3.connect(str(STATE/'control.sqlite3')) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise SystemExit('A hosting job is running. Retry after it finishes.')
    units = ['veyra-agent','veyra-web']
    if Path('/etc/systemd/system/veyra-web-public.service').is_file():
        units.append('veyra-web-public')
    print('Preflight passed. The upgrade preserves customer sites and the control database.')
    if not args.apply:
        print('Check only: no changes made. Use --apply to back up and upgrade the panel.')
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = STATE/'install-backups'/('upgrade-'+stamp)
    backup.mkdir(mode=0o700)
    incoming = INSTALL/('.incoming-'+stamp)
    previous = INSTALL/('.previous-'+stamp)
    shutil.copytree(SOURCE/'veyra',incoming,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for folder, dirs, files in os.walk(incoming):
        os.chmod(folder,0o755)
        for name in files:
            path=Path(folder)/name
            if path.is_symlink():
                raise SystemExit('Release source must not contain symlinks.')
            os.chmod(path,0o644)
    shutil.copytree(INSTALL/'veyra',backup/'veyra',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    # Stop frontend first, then agent: no requests can race the migration.
    run(['/usr/bin/systemctl','stop']+list(reversed(units[1:])))
    with sqlite3.connect(str(STATE/'control.sqlite3')) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            run(['/usr/bin/systemctl','start']+units)
            raise SystemExit('A job started after preflight. No application change was made.')
        run(['/usr/bin/systemctl','stop','veyra-agent'])
        with sqlite3.connect(str(backup/'control.sqlite3')) as target:
            db.backup(target)
    os.chmod(backup/'control.sqlite3',0o600)
    (INSTALL/'veyra').rename(previous)
    incoming.rename(INSTALL/'veyra')
    try:
        run(['/usr/bin/systemctl','daemon-reload'])
        run(['/usr/bin/systemctl','start','veyra-agent'])
        health = "from veyra.agent import rpc; import json; print(json.dumps(rpc('/run/veyrapanel/agent.sock', {'method':'health'})))"
        ready=False
        for attempt in range(30):
            result=subprocess.run(['/usr/bin/python3','-c',health],cwd=str(INSTALL),capture_output=True,text=True,timeout=5)
            if result.returncode==0 and json.loads(result.stdout).get('ok'):
                ready=True
                break
            time.sleep(0.2)
        if not ready:
            raise RuntimeError('The new agent did not become ready.')
        run(['/usr/bin/systemctl','start']+units[1:])
    except Exception:
        # Migrations are additive. Keep the current DB and its complete backup;
        # never overwrite live changes with an old database automatically.
        run(['/usr/bin/systemctl','stop']+list(reversed(units)))
        (INSTALL/'veyra').rename(INSTALL/('.failed-'+stamp))
        previous.rename(INSTALL/'veyra')
        run(['/usr/bin/systemctl','start']+units)
        raise SystemExit('Upgrade failed. Previous application restored; database backup retained at '+str(backup))
    print('Upgrade complete. Backups retained at '+str(backup))
    print('Customer services and Nginx were not restarted. Verify public sign-in and hosted sites.')


if __name__ == '__main__':
    main()
