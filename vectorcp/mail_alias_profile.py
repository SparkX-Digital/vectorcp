"""Owner-only, check-first upgrade of an existing managed native mail profile."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
from types import SimpleNamespace

from .core import Engine, Fault
from . import mail_profile as profile
from .mail import Mail


def upgrade(apply=False):
    state, config, base = profile.STATE, profile.CONFIG, profile.BASE
    if os.geteuid() != 0 or not Path('/etc/almalinux-release').exists() or 'release 9.' not in Path('/etc/almalinux-release').read_text():
        raise Fault('Run as root on AlmaLinux 9 after upgrading VectorCP.')
    mail = Mail(SimpleNamespace(state=state, development=False, db_path=state / 'control.sqlite3'))
    installed = mail.profile
    if not installed:
        raise Fault('Install the optional native mail profile first.')
    main = Path('/etc/postfix/main.cf')
    lookup = Path('/etc/postfix/vectorcp-aliases.cf')
    maintenance = Path('/run/vectorcp-profile-maintenance')
    if maintenance.exists() or maintenance.is_symlink():
        raise Fault('Inspect and recover the existing profile maintenance operation first.')
    if main.is_symlink() or main.read_text() != profile.postfix_config(installed['hostname'], installed['listen'], aliases=installed.get('aliases') is True):
        raise Fault('Postfix configuration was customized. It was preserved; inspect it before upgrading.')
    if lookup.exists() or lookup.is_symlink():
        if lookup.is_symlink() or lookup.read_text() != profile.ALIAS_MAP:
            raise Fault('An unmanaged alias map exists. It was preserved.')
    if (mail.pending.exists() or mail.pending.is_symlink() or not mail.current_digest()
            or not os.path.ismount(mail.store) or not os.path.ismount('/var/spool/postfix')
            or any(value != 'active' for value in mail.services().values())):
        raise Fault('Recover mail publication before upgrading the native profile.')
    with sqlite3.connect('file:' + str(state / 'control.sqlite3') + '?mode=ro', uri=True) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise Fault('Wait for hosting jobs before upgrading the native profile.')
    if installed.get('aliases') is True:
        if not lookup.exists():
            raise Fault('The alias profile map is missing. Inspect its private configuration backup.')
        print('The managed alias profile is already installed and healthy.')
        return
    if not apply:
        print('Alias upgrade preflight passed. Check only; no service or configuration changes made.')
        return
    backup = state / 'install-backups' / ('mail-aliases-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    backup.mkdir(mode=0o700, parents=True)
    profile.LOG = backup / 'commands.jsonl'
    profile.write(profile.LOG, '', 0o600)
    profile.write(maintenance, 'mail-alias-upgrade\n', 0o600)
    frontends = ['vectorcp-web'] + (['vectorcp-web-public'] if Path('/etc/systemd/system/vectorcp-web-public.service').exists() else [])
    try:
        profile.run(['/usr/bin/systemctl', 'stop'] + frontends)
        with sqlite3.connect('file:' + str(state / 'control.sqlite3') + '?mode=ro', uri=True) as db:
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                raise Fault('A hosting job started during preflight. Retry after it finishes.')
        profile.run(['/usr/bin/systemctl', 'stop', 'vectorcp-agent'])
        engine = Engine(state, '/srv/vectorcp/sites', '/etc/nginx/conf.d')
        mail = engine.mail
        with engine.db() as db:
            if engine.mail.health(db)['recovery_required']:
                raise Fault('Mail state changed during preflight. Inspect it before retrying.')
            with sqlite3.connect(str(backup / 'control.sqlite3')) as target:
                db.backup(target)
            (backup / 'control.sqlite3').chmod(0o600)
            profile.sync(backup / 'control.sqlite3')
            profile.sync(backup)
            engine.mail.checkpoint()
            engine.mail.stop()
            for source in (main, config / 'installed.json', base / 'lookup.sqlite3'):
                profile.write(backup / source.name, source.read_bytes(), 0o600)
            profile.write(lookup, profile.ALIAS_MAP, 0o644)
            profile.write(main, profile.postfix_config(installed['hostname'], installed['listen']), 0o644)
            profile.run(['/usr/sbin/restorecon', str(lookup), str(main)])
            profile.run(['/usr/sbin/postfix', 'check'])
            installed['aliases'] = True
            installed['alias_upgrade_backup'] = str(backup)
            profile.write(config / 'installed.json', json.dumps(installed) + '\n', 0o600)
            engine.mail.complete(engine.mail.snapshot(db))
        profile.readiness(installed['hostname'], installed['listen'][0], Path('/etc/pki/vectorcp-mail/fullchain.pem'))
        profile.run(['/usr/bin/systemctl', 'start', 'vectorcp-agent'] + frontends)
        profile.run(['/usr/bin/curl', '--fail', '--silent', '--retry', '10', '--retry-connrefused', '--retry-delay', '1', '--max-time', '15', 'http://127.0.0.1:8765/healthz'])
        maintenance.unlink()
        profile.sync(maintenance.parent)
        print('Alias profile upgraded. Existing messages, mailbox credentials, DNS and firewall preserved.')
        print('Private configuration backup: ' + str(backup))
    except Exception:
        subprocess.run(['/usr/bin/systemctl', 'stop', 'postfix', 'dovecot'], capture_output=True)
        if not mail.pending.exists():
            mail.checkpoint()
        subprocess.run(['/usr/bin/systemctl', 'start', 'vectorcp-agent'] + frontends, capture_output=True)
        print('Upgrade interrupted. Mail remains stopped; inspect ' + str(backup) + ' and the maintenance marker. Do not reinstall or format mail storage.')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with (profile.STATE / 'profile-maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            upgrade(args.apply)
        except (Fault, ValueError, OSError, subprocess.TimeoutExpired) as error:
            raise SystemExit(str(error))


if __name__ == '__main__':
    main()
