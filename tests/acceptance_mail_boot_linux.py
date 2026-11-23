"""Prepare/verify mail's reboot fence on the marked disposable guest only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from vectorcp.agent import rpc

ROOT = Path('/var/lib/vectorcp/mail-acceptance')
BASE = Path('/var/lib/vectorcp-mail')
STATE = ROOT / 'boot-checkpoint.json'
PENDING = BASE / 'pending.json'
FILES = [Path('/usr/libexec/vectorcp-mail-start-check')] + [
    Path('/etc/systemd/system/' + u + '.service.d/vectorcp.conf') for u in ('postfix', 'dovecot')]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records():
    with sqlite3.connect('/var/lib/vectorcp/control.sqlite3') as db:
        return {table: hashlib.sha256(json.dumps(db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()).encode()).hexdigest()
                for table in ('mail_domains', 'mailboxes')}


def messages():
    return {str(p.relative_to(BASE / 'store')): digest(p) for p in (BASE / 'store').rglob('*')
            if p.is_file() and not p.is_symlink() and p.parent.name in ('cur', 'new')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    context = Path('/var/lib/vectorcp/acceptance-context.json')
    if not args.apply or os.geteuid() != 0 or not context.exists():
        raise SystemExit('Requires --apply as root on the disposable acceptance guest.')
    profile = json.loads(Path('/etc/vectorcp/mail/installed.json').read_text())
    assert profile['hostname'] == 'mail.example.test' and profile['listen'] == ['127.0.0.1']
    os.umask(0o077)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if args.prepare:
        assert not STATE.exists(), 'Preserve the previous boot-check evidence.'
        for p in FILES:
            assert p.stat().st_size > 100, 'Install the complete durable startup gate first.'
        if not PENDING.exists():
            with PENDING.open('x') as stream:
                stream.write(json.dumps({'version': 1, 'acceptance_boot_checkpoint': True}))
                stream.flush(); os.fsync(stream.fileno())
            fd = os.open(str(BASE), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        subprocess.run(['systemctl', 'stop', 'postfix', 'dovecot'], check=True)
        retained = messages()
        assert retained, 'Complete the delivery acceptance first; reboot evidence must include real messages.'
        data = {'boot_id': boot, 'files': {str(p): digest(p) for p in FILES}, 'records': records(), 'messages': retained}
        with STATE.open('x') as stream:
            json.dump(data, stream); stream.flush(); os.fsync(stream.fileno())
        fd = os.open(str(ROOT), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        print('Pending mail checkpoint retained. Reboot this disposable guest, then run --verify.', flush=True)
        return
    previous = json.loads(STATE.read_text())
    assert previous['boot_id'] != boot, 'A guest reboot is required between prepare and verify.'
    assert PENDING.exists(), 'The durable checkpoint was lost.'
    assert previous['files'] == {str(p): digest(p) for p in FILES}, 'A startup gate changed across reboot.'
    for unit in ('postfix', 'dovecot'):
        assert subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode != 0
        assert subprocess.run(['systemctl', 'start', unit], capture_output=True).returncode != 0
    assert records() == previous['records'] and messages() == previous['messages']
    login = json.loads(context.read_text())['owner_login']
    session = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': login})
    def call(method, data=None):
        return rpc('/run/vectorcp/agent.sock', {'method': method, 'data': data or {}, 'token': session['token'], 'csrf': session['csrf']})
    assert call('mail.list')['recovery_required']
    call('mail.recover', {'confirm': 'RECOVER MAIL'})
    assert not call('mail.list')['recovery_required']
    assert records() == previous['records'] and messages() == previous['messages']
    assert subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing'
    result = {'at': int(time.time()), 'checks': ['startup gate hashes survive reboot', 'pending marker prevents automatic and explicit native service startup',
              'committed mail records and messages survive reboot', 'owner recovery resumes native services with SELinux enforcing']}
    (ROOT / 'boot-result.json').write_text(json.dumps(result, indent=2) + '\n')
    for name in result['checks']:
        print('PASS ' + name, flush=True)


if __name__ == '__main__':
    main()
