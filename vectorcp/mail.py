"""Optional, scoped virtual mailboxes. Native services never read the control DB.

A durable stop-before-commit checkpoint revokes existing IMAP/SMTP sessions on
security changes. Interrupted publication remains stopped until owner recovery.
"""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import time

from .core import Fault, integer, password_hash
from .distribution import available, manages, scope

OPERATIONS = {'mail.list', 'mail.domain', 'mail.create', 'mail.password',
              'mail.quota', 'mail.active', 'mail.recover', 'mail.alias-create',
              'mail.alias-active'}
READ_ONLY = {'mail.list'}
LOCAL = re.compile(r'[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z')


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS mail_domains (
      site_id INTEGER PRIMARY KEY REFERENCES sites(id), enabled INTEGER NOT NULL DEFAULT 0,
      created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS mailboxes (
      id TEXT PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES mail_domains(site_id),
      local TEXT NOT NULL, password TEXT NOT NULL, quota_mb INTEGER NOT NULL,
      active INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
      UNIQUE(site_id,local));
    CREATE TABLE IF NOT EXISTS mail_aliases (
      id TEXT PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES mail_domains(site_id),
      local TEXT NOT NULL, mailbox_id TEXT NOT NULL REFERENCES mailboxes(id),
      active INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
      UNIQUE(site_id,local));
    ''')


class Mail:
    def __init__(self, engine):
        self.e = engine
        self.config = engine.state / 'mail-profile' if engine.development else Path('/etc/vectorcp/mail')
        self.base = engine.state / 'mail-runtime' if engine.development else Path('/var/lib/vectorcp-mail')
        self.store = self.base / 'store'
        self.pending = self.base / 'pending.json'
        self.projection = self.base / 'lookup.sqlite3'

    @property
    def profile(self):
        path = self.config / 'installed.json'
        if not path.exists():
            return None
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_size > 4096:
                raise ValueError()
            if not self.e.development and (st.st_uid != 0 or st.st_mode & 0o077):
                raise ValueError()
            p = json.loads(path.read_text())
            if p['version'] != 1 or p['control_db'] != str(self.e.db_path):
                # A second control plane must never publish into this mail profile.
                return None
            from .core import DOMAIN
            if not DOMAIN.fullmatch(p['hostname']) or not isinstance(p['storage_mb'], int) or not 128 <= p['storage_mb'] <= 8192:
                raise ValueError()
            return p
        except (ValueError, KeyError, TypeError, OSError):
            raise Fault('The mail profile is invalid. Contact the server administrator.', 503)

    def run(self, args, input=None):
        try:
            r = subprocess.run(args, input=input, text=True, capture_output=True, timeout=40)
        except (OSError, subprocess.TimeoutExpired):
            raise Fault('The mail service command did not finish. Inspect the server before recovery.', 503)
        if r.returncode:
            raise Fault('The mail service command failed. Inspect its journal before recovery.', 503)
        return r.stdout

    def snapshot(self, db):
        domains, boxes, aliases = [], [], []
        for site in db.execute('SELECT s.*,m.enabled AS mail_enabled FROM sites s JOIN mail_domains m ON m.site_id=s.id ORDER BY s.id'):
            owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
            enabled = bool(site['mail_enabled'] and site['status'] == 'active' and available(db, owner)
                           and self.e.distribution.features(db, owner)['mail'])
            domains.append((site['domain'], int(enabled)))
            for box in db.execute('SELECT * FROM mailboxes WHERE site_id=? ORDER BY local', (site['id'],)):
                boxes.append((box['local'] + '@' + site['domain'], box['password'],
                              str(self.store / box['id']), box['quota_mb'], int(enabled and box['active'])))
            for alias in db.execute('SELECT a.*,b.local AS destination,b.active AS mailbox_active FROM mail_aliases a JOIN mailboxes b ON b.id=a.mailbox_id AND b.site_id=a.site_id WHERE a.site_id=? ORDER BY a.local', (site['id'],)):
                aliases.append((alias['local'] + '@' + site['domain'],
                                alias['destination'] + '@' + site['domain'],
                                int(enabled and alias['active'] and alias['mailbox_active'])))
        result = {'domains': domains, 'boxes': boxes}
        # Preserve old profile digests until aliases actually exist.
        if aliases:
            result['aliases'] = aliases
        return result

    @staticmethod
    def digest(snapshot):
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()

    def current_digest(self):
        try:
            st = self.projection.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o027:
                return None
            with closing(sqlite3.connect('file:' + str(self.projection) + '?mode=ro', uri=True)) as db:
                row = db.execute('SELECT digest FROM metadata').fetchone()
                return row[0] if row else None
        except (OSError, sqlite3.Error):
            return None

    def services(self):
        services = {}
        if not self.e.development:
            for unit in ('postfix', 'dovecot'):
                try:
                    result = subprocess.run(['/usr/bin/systemctl', 'is-active', unit], capture_output=True, text=True, timeout=5)
                    services[unit] = result.stdout.strip() or 'unknown'
                except (OSError, subprocess.TimeoutExpired):
                    services[unit] = 'unknown'
        return services

    def health(self, db):
        services = self.services()
        interrupted = self.pending.exists() or self.pending.is_symlink()
        drift = self.current_digest() != self.digest(self.snapshot(db))
        storage = self.e.development or (os.path.ismount(self.store) and os.path.ismount('/var/spool/postfix'))
        message_recovery = False
        if interrupted:
            try:
                info = self.pending.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_size <= 4096:
                    checkpoint = json.loads(self.pending.read_text())
                    message_recovery = isinstance(checkpoint, dict) and checkpoint.get('operation') == 'message-recovery'
            except (OSError, ValueError):
                pass
        return {'services': services, 'message_recovery_required': message_recovery,
                'recovery_required': bool(interrupted or drift or not storage or any(v != 'active' for v in services.values()))}

    def checkpoint(self):
        self.base.mkdir(mode=0o750, parents=True, exist_ok=True)
        with self.pending.open('x') as f:
            f.write(json.dumps({'version': 1, 'created': int(time.time())}))
            f.flush()
            os.fsync(f.fileno())
        self.pending.chmod(0o600)
        self.fsync(self.base)

    @staticmethod
    def fsync(path):
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def stop(self):
        if not self.e.development:
            self.run(['/usr/bin/systemctl', 'stop', 'postfix', 'dovecot'])
            # Stop's success is not enough if a unit has a custom restart policy.
            for unit in ('postfix', 'dovecot'):
                if self.run(['/usr/bin/systemctl', 'show', '-p', 'ActiveState', '--value', unit]).strip() not in ('inactive', 'failed'):
                    raise Fault('Mail services did not stop. The change was refused.', 503)

    def prepare(self, db, before):
        """Called before control DB commit, including account/plan/site changes."""
        if not self.profile:
            return None
        snapshot = self.snapshot(db)
        if snapshot == before:
            return None
        if (self.pending.exists() or self.pending.is_symlink()
                or self.current_digest() != self.digest(before)
                or (not self.e.development and Path('/run/vectorcp-profile-maintenance').exists())
                or any(v != 'active' for v in self.services().values())):
            raise Fault('Mail publication needs owner recovery before further mail or access changes.', 409)
        self.checkpoint()
        self.stop()
        return snapshot

    def complete(self, snapshot):
        """Publish only after control commit, while both native services are stopped."""
        temporary = self.base / ('lookup-' + secrets.token_hex(8) + '.sqlite3')
        try:
            fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(str(temporary))) as db, db:
                db.executescript('''
                CREATE TABLE domains (domain TEXT PRIMARY KEY, active INTEGER NOT NULL);
                CREATE TABLE boxes (address TEXT PRIMARY KEY,password TEXT NOT NULL,home TEXT NOT NULL,quota_mb INTEGER NOT NULL,active INTEGER NOT NULL);
                CREATE TABLE metadata (digest TEXT NOT NULL);
                CREATE TABLE aliases (address TEXT PRIMARY KEY,destination TEXT NOT NULL,active INTEGER NOT NULL);
                ''')
                db.executemany('INSERT INTO domains VALUES(?,?)', snapshot['domains'])
                db.executemany('INSERT INTO boxes VALUES(?,?,?,?,?)', snapshot['boxes'])
                db.executemany('INSERT INTO aliases VALUES(?,?,?)', snapshot.get('aliases', []))
                db.execute('INSERT INTO metadata VALUES(?)', (self.digest(snapshot),))
            temporary.chmod(0o640)
            if not self.e.development:
                import grp
                os.chown(temporary, 0, grp.getgrnam('postfix').gr_gid)
            self.fsync(temporary)
            os.replace(temporary, self.projection)
            if not self.e.development:
                self.run(['/usr/sbin/restorecon', str(self.projection)])
            self.fsync(self.base)
            self.pending.unlink()
            self.fsync(self.base)
            if not self.e.development:
                self.run(['/usr/bin/systemctl', 'start', 'dovecot', 'postfix'])
                for unit in ('dovecot', 'postfix'):
                    self.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit])
        except Exception:
            if not self.pending.exists():
                self.checkpoint()
            self.stop()
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def site(self, db, actor, ident, mutation=False):
        site = db.execute('SELECT * FROM sites WHERE id=?', (integer(ident, 'website', 1, 2147483647),)).fetchone()
        if not site or not manages(db, actor, site['user_id']):
            raise Fault('Website not found.', 404)
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if mutation:
            if owner['role'] != 'customer' or owner['is_reseller'] or not owner['hosting_slot']:
                raise Fault('Mail requires an isolated ordinary customer account.', 409)
            if mutation != 'restrict' and (not available(db, owner) or site['status'] != 'active'):
                raise Fault('Restore access to this account and website first.', 409)
            if mutation != 'restrict':
                self.e.distribution.require_feature(db, owner, 'mail')
            self.e.transfers.idle(db, owner['id'])
        return site, owner

    def password(self, value):
        if not isinstance(value, str) or not 15 <= len(value) <= 72 or len(value.encode()) > 72 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise Fault('Use 15 to 72 characters, at most 72 UTF-8 bytes, without control characters.')
        if self.e.development:
            return '{DEVELOPMENT}' + password_hash(value)
        result = self.run(['/usr/bin/doveadm', 'pw', '-s', 'BLF-CRYPT', '-r', '12'], input=value + '\n' + value + '\n').strip()
        if not re.fullmatch(r'\{BLF-CRYPT\}\$2[aby]\$12\$[./A-Za-z0-9]{53}', result):
            raise Fault('The installed mail password scheme is unavailable.', 503)
        return result

    def reservation(self, db, owner, quota, exclude=''):
        account = db.execute('SELECT COALESCE(SUM(b.quota_mb),0) FROM mailboxes b JOIN sites s ON s.id=b.site_id WHERE s.user_id=? AND b.id<>?', (owner['id'], exclude)).fetchone()[0]
        total = db.execute('SELECT COALESCE(SUM(quota_mb),0) FROM mailboxes WHERE id<>?', (exclude,)).fetchone()[0]
        if account + quota > owner['storage_mb'] or total + quota > self.profile['storage_mb'] * 4 // 5:
            raise Fault('The customer or server mail storage reservation would be exceeded.', 409)

    def dispatch(self, db, actor, method, data):
        p = self.profile
        if method == 'mail.list':
            health = self.health(db) if p else {'services': {}, 'recovery_required': False}
            clause, args = scope(actor, 's.user_id')
            sites = db.execute('SELECT s.id,s.domain,s.user_id,m.enabled FROM sites s LEFT JOIN mail_domains m ON m.site_id=s.id ' + ('WHERE ' + clause if clause else '') + ' ORDER BY s.domain', args).fetchall()
            domains = []
            for s in sites:
                site, owner = self.site(db, actor, s['id'])
                effective = bool(p and s['enabled'] and available(db, owner) and site['status'] == 'active' and self.e.distribution.features(db, owner)['mail'] and not health['recovery_required'])
                boxes = [dict(r) for r in db.execute('SELECT id,local,quota_mb,active,created FROM mailboxes WHERE site_id=? ORDER BY local', (s['id'],))]
                for b in boxes:
                    b['address'] = b['local'] + '@' + s['domain']
                    b['effective'] = effective and bool(b['active']) and not self.pending.exists()
                aliases = [dict(r) for r in db.execute('SELECT a.id,a.local,a.mailbox_id,a.active,a.created,b.local AS destination,b.active AS mailbox_active FROM mail_aliases a JOIN mailboxes b ON b.id=a.mailbox_id AND b.site_id=a.site_id WHERE a.site_id=? ORDER BY a.local', (s['id'],))]
                for a in aliases:
                    a['address'] = a['local'] + '@' + s['domain']
                    a['destination'] += '@' + s['domain']
                    mailbox_active = a.pop('mailbox_active')
                    a['effective'] = effective and bool(a['active'] and mailbox_active)
                domains.append({'site_id': s['id'], 'domain': s['domain'], 'enabled': bool(s['enabled']), 'effective': effective, 'mailboxes': boxes, 'aliases': aliases})
            return {'installed': bool(p), 'hostname': p['hostname'] if p else None,
                    'aliases_supported': bool(p and p.get('aliases') is True),
                    **health, 'domains': domains,
                    'storage_mb': p['storage_mb'] * 4 // 5 if p and actor['role'] == 'admin' else None,
                    'ports': {'smtp': 25, 'submission': 587, 'imaps': 993}}
        if actor['role'] != 'admin' and method in ('mail.domain', 'mail.recover'):
            raise Fault('Only the server owner can activate mail domains or recover publication.', 403)
        if not p:
            raise Fault('The optional mail profile is not installed. Ask the server administrator.', 409)
        if not self.e.development and Path('/run/vectorcp-profile-maintenance').exists():
            raise Fault('Wait for the server owner to finish service-profile maintenance.', 409)
        if method == 'mail.recover':
            if self.pending.exists() or self.pending.is_symlink():
                try:
                    info = self.pending.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                        raise ValueError()
                    checkpoint = json.loads(self.pending.read_text())
                except (OSError, ValueError):
                    raise Fault('Inspect the unreadable mail checkpoint before recovery.', 409)
                if isinstance(checkpoint, dict) and checkpoint.get('operation') == 'message-recovery':
                    raise Fault('Root must use the mail message recovery command to inspect this checkpoint. Publication recovery cannot complete a message restore.', 409)
            if data.get('confirm') != 'RECOVER MAIL':
                raise Fault('Type RECOVER MAIL after reviewing the service journal.')
            if not self.health(db)['recovery_required']:
                raise Fault('Mail services already match the committed configuration.', 409)
            if not (self.pending.exists() or self.pending.is_symlink()):
                self.checkpoint()
            self.stop()
            self.complete(self.snapshot(db))
            self.e.log(db, actor, method, 'Committed mail configuration')
            return {'ok': True}
        if self.health(db)['recovery_required']:
            raise Fault('Mail publication needs owner recovery.', 409)
        if method == 'mail.domain':
            site, owner = self.site(db, actor, data.get('site_id'), mutation='restrict' if data.get('enabled') is False else True)
            enabled = data.get('enabled')
            if not isinstance(enabled, bool) or data.get('confirm_domain') != site['domain']:
                raise Fault('Confirm the exact mail domain and enabled state.')
            db.execute('INSERT INTO mail_domains VALUES(?,?,?) ON CONFLICT(site_id) DO UPDATE SET enabled=excluded.enabled', (site['id'], int(enabled), int(time.time())))
            target = site['domain']
        elif method in ('mail.create', 'mail.alias-create'):
            site, owner = self.site(db, actor, data.get('site_id'), mutation=True)
            domain = db.execute('SELECT enabled FROM mail_domains WHERE site_id=?', (site['id'],)).fetchone()
            if not domain or not domain['enabled']:
                raise Fault('The server owner must activate this mail domain first.', 409)
            local = data.get('local')
            if not isinstance(local, str) or not LOCAL.fullmatch(local) or '..' in local:
                raise Fault('Use 1–64 lowercase letters, digits, dots, underscores or hyphens, starting and ending with a letter or digit.')
            if (db.execute('SELECT 1 FROM mailboxes WHERE site_id=? AND local=?', (site['id'], local)).fetchone()
                    or db.execute('SELECT 1 FROM mail_aliases WHERE site_id=? AND local=?', (site['id'], local)).fetchone()):
                raise Fault('This email address is already reserved by a mailbox or alias.', 409)
            if method == 'mail.alias-create':
                self.require_aliases(p)
                box = db.execute('SELECT id FROM mailboxes WHERE id=? AND site_id=?', (data.get('mailbox_id') if isinstance(data.get('mailbox_id'), str) else '', site['id'])).fetchone()
                if not box:
                    raise Fault('Choose a mailbox on this same domain.', 404)
                if db.execute('SELECT COUNT(*) FROM mail_aliases').fetchone()[0] >= 512 or db.execute('SELECT COUNT(*) FROM mail_aliases a JOIN sites s ON s.id=a.site_id WHERE s.user_id=?', (owner['id'],)).fetchone()[0] >= 64:
                    raise Fault('This mail profile allows 64 aliases per customer and 512 per server.', 409)
                db.execute('INSERT INTO mail_aliases VALUES(?,?,?,?,?,?)', (secrets.token_hex(16), site['id'], local, box['id'], 1, int(time.time())))
                target = local + '@' + site['domain']
                self.e.log(db, actor, method, target)
                return {'ok': True}
            if db.execute('SELECT COUNT(*) FROM mailboxes').fetchone()[0] >= 128 or db.execute('SELECT COUNT(*) FROM mailboxes b JOIN sites s ON s.id=b.site_id WHERE s.user_id=?', (owner['id'],)).fetchone()[0] >= 32:
                raise Fault('This mail profile allows 32 mailboxes per customer and 128 per server.', 409)
            quota = integer(data.get('quota_mb'), 'mailbox quota', 1, 4096)
            self.reservation(db, owner, quota)
            ident = secrets.token_hex(16)
            db.execute('INSERT INTO mailboxes VALUES(?,?,?,?,?,?,?)', (ident, site['id'], local, self.password(data.get('password')), quota, 1, int(time.time())))
            target = local + '@' + site['domain']
        elif method == 'mail.alias-active':
            self.require_aliases(p)
            ident = data.get('id')
            alias = db.execute('SELECT * FROM mail_aliases WHERE id=?', (ident if isinstance(ident, str) else '',)).fetchone()
            if not alias:
                raise Fault('Alias not found.', 404)
            self.site(db, actor, alias['site_id'], mutation='restrict' if data.get('active') is False else True)
            if not isinstance(data.get('active'), bool):
                raise Fault('Choose an enabled or suspended alias state.')
            db.execute('UPDATE mail_aliases SET active=? WHERE id=?', (int(data['active']), alias['id']))
            target = alias['local']
        else:
            ident = data.get('id')
            if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
                raise Fault('Mailbox not found.', 404)
            box = db.execute('SELECT * FROM mailboxes WHERE id=?', (ident,)).fetchone()
            if not box:
                raise Fault('Mailbox not found.', 404)
            site, owner = self.site(db, actor, box['site_id'], mutation='restrict' if method == 'mail.active' and data.get('active') is False else True)
            target = box['local'] + '@' + site['domain']
            if method == 'mail.password':
                db.execute('UPDATE mailboxes SET password=? WHERE id=?', (self.password(data.get('password')), ident))
            elif method == 'mail.quota':
                quota = integer(data.get('quota_mb'), 'mailbox quota', 1, 4096)
                self.reservation(db, owner, quota, ident)
                db.execute('UPDATE mailboxes SET quota_mb=? WHERE id=?', (quota, ident))
            elif method == 'mail.active':
                if not isinstance(data.get('active'), bool):
                    raise Fault('Choose an enabled or suspended mailbox state.')
                db.execute('UPDATE mailboxes SET active=? WHERE id=?', (int(data['active']), ident))
            else:
                raise Fault('Unknown mail operation.', 404)
        self.e.log(db, actor, method, target)
        return {'ok': True}

    @staticmethod
    def require_aliases(profile):
        if profile.get('aliases') is not True:
            raise Fault('The server owner must upgrade the native mail profile for aliases first. See the mail hosting guide.', 409)
