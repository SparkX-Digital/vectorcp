"""Owner-configured SFTP destinations with pinned host keys and verified copies.

No hostname, credential, key path or remote path is accepted from an HTTP client.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import tempfile
import time

from .core import Fault, integer, text
from .distribution import manages, scope

READ_ONLY = {'backups.destinations', 'backups.offsite.list'}
OPERATIONS = READ_ONLY | {'backups.offsite.send', 'backups.offsite.fetch'}
MAX_COPY = 280 * 1024 ** 2


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS offsite_copies (
      id TEXT PRIMARY KEY, backup_id TEXT NOT NULL, site_id INTEGER NOT NULL REFERENCES sites(id),
      user_id INTEGER NOT NULL REFERENCES users(id), domain TEXT NOT NULL,
      bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, destination TEXT NOT NULL,
      created INTEGER NOT NULL, UNIQUE(backup_id,destination))''')
    db.execute('CREATE INDEX IF NOT EXISTS offsite_owner_history ON offsite_copies(user_id,created)')


def checksum(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(262144), b''):
            sha.update(block)
    return sha.hexdigest()


def quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


class Offsite:
    def __init__(self, engine):
        self.e = engine

    def private_file(self, path, secret=False):
        path = Path(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & (0o077 if secret else 0o022):
            raise Fault('An offsite configuration or key file has unsafe ownership or permissions.', 409)
        return path

    def destinations(self):
        path = self.e.state / 'offsite/destinations.json'
        if not path.exists():
            return []
        try:
            values = json.loads(self.private_file(path, secret=True).read_text())
            if not isinstance(values, list) or len(values)>8:
                raise ValueError()
            seen = set()
            for d in values:
                if (not isinstance(d, dict) or not re.fullmatch(r'[a-z][a-z0-9_-]{2,30}', d['id']) or d['id'] in seen or
                    not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', d['host']) or
                    not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', d['user']) or
                    isinstance(d['port'], bool) or not isinstance(d['port'], int) or not 1<=d['port']<=65535 or
                    not re.fullmatch(r'/[A-Za-z0-9/_-]{1,240}', d['path']) or '..' in PurePosixPath(d['path']).parts or
                    not isinstance(d['label'], str) or not 1<=len(d['label'])<=80):
                    raise ValueError()
                seen.add(d['id'])
                self.private_file(d['key'], secret=True)
                self.private_file(d['known_hosts'])
            return values
        except (OSError, ValueError, TypeError, KeyError):
            raise Fault('The owner’s offsite destination configuration needs review.', 409)

    def destination(self, name):
        value = next((d for d in self.destinations() if d['id']==name), None)
        if not value:
            raise Fault('Choose an available offsite destination.', 409)
        return value

    def transfer(self, destination, lines, folder):
        batch = Path(folder) / 'sftp-batch'
        batch.write_text('\n'.join(lines)+'\n')
        batch.chmod(0o600)
        args = ['/usr/bin/prlimit', '--fsize=%d' % MAX_COPY, '--', '/usr/bin/sftp',
                '-F', '/dev/null',
                '-oBatchMode=yes', '-oIdentitiesOnly=yes', '-oIdentityAgent=none',
                '-oPasswordAuthentication=no', '-oStrictHostKeyChecking=yes',
                '-oGlobalKnownHostsFile=/dev/null', '-oUserKnownHostsFile='+destination['known_hosts'],
                '-oConnectTimeout=10', '-oServerAliveInterval=10', '-oServerAliveCountMax=2',
                '-P', str(destination['port']), '-i', destination['key'], '-b', str(batch),
                destination['user']+'@'+destination['host']]
        try:
            result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        except subprocess.TimeoutExpired:
            raise Fault('Offsite transfer timed out. The local recovery point was preserved.', 409)
        if result.returncode:
            raise Fault('SFTP transfer failed. Check the pinned host key, connection, remote folder and free space.', 409)

    def dispatch(self, db, actor, method, data):
        if method == 'backups.destinations':
            return {'destinations': [{'id': d['id'], 'label': d['label']} for d in self.destinations()]}
        if method == 'backups.offsite.list':
            clause, args = scope(actor)
            offset = integer(data.get('offset', 0), 'offsite history offset', 0, 1000000)
            rows = [dict(r) for r in db.execute('SELECT * FROM offsite_copies' + (' WHERE '+clause if clause else '') + ' ORDER BY created DESC,id LIMIT 101 OFFSET ?', args+(offset,))]
            return {'copies': rows[:100], 'more': len(rows)>100, 'offset': offset}
        copy_id = text(data.get('id'), 'saved copy', 32)
        table = 'backups' if method == 'backups.offsite.send' else 'offsite_copies'
        row = db.execute('SELECT * FROM '+table+' WHERE id=?', (copy_id,)).fetchone()
        if not row or not manages(db, actor, row['user_id']):
            raise Fault('Saved copy not found.', 404)
        if method == 'backups.offsite.send' and row['kind'] != 'full':
            raise Fault('Offsite transfer requires a full website backup.', 409)
        destination = data.get('destination') if method == 'backups.offsite.send' else row['destination']
        self.destination(destination)
        return self.e.hosting_job(db, actor, method, {'site_id': row['site_id'], 'id': copy_id, 'destination': destination})

    def send(self, backup_id, destination_name):
        import shutil
        d = self.destination(destination_name)
        with self.e.db() as db:
            row = db.execute("SELECT * FROM backups WHERE id=? AND kind='full'", (backup_id,)).fetchone()
        if not row:
            raise Fault('Full recovery point not found.', 404)
        path = self.e.backups / (row['id']+'.tar.gz')
        size = path.stat().st_size
        if size>MAX_COPY or shutil.disk_usage(self.e.backups).free < size+64*1024**2:
            raise Fault('Offsite verification needs space for a temporary second copy.', 409)
        sha = checksum(path)
        path.chmod(0o600)
        remote = d['path'].rstrip('/') + '/' + row['id'] + '-' + sha + '.tar.gz'
        with tempfile.TemporaryDirectory(dir=str(self.e.backups)) as folder:
            verified = Path(folder) / 'verified.tar.gz'
            staging = remote + '.upload-' + secrets.token_hex(8)
            self.transfer(d, ['put -p '+quoted(path)+' '+quoted(staging), 'chmod 600 '+quoted(staging), 'rename '+quoted(staging)+' '+quoted(remote), 'get '+quoted(remote)+' '+quoted(verified)], folder)
            if verified.stat().st_size!=size or checksum(verified)!=sha:
                raise Fault('Offsite round-trip verification failed. The local recovery point was preserved.', 409)
        with self.e.db() as db:
            db.execute('''INSERT INTO offsite_copies VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(backup_id,destination) DO UPDATE SET bytes=excluded.bytes,sha256=excluded.sha256,created=excluded.created''',
                       (secrets.token_hex(12), row['id'], row['site_id'], row['user_id'], row['domain'], size, sha, d['id'], int(time.time())))
        return {}

    def fetch(self, copy_id, site, owner):
        import shutil
        with self.e.db() as db:
            row = db.execute('SELECT * FROM offsite_copies WHERE id=? AND site_id=? AND user_id=?', (copy_id, site['id'], owner['id'])).fetchone()
            existing = db.execute('SELECT * FROM backups WHERE id=?', (row['backup_id'],)).fetchone() if row else None
            count, used = db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM backups WHERE user_id=?', (owner['id'],)).fetchone()
            global_used = db.execute('SELECT COALESCE(SUM(bytes),0) FROM backups').fetchone()[0]
        if not row:
            raise Fault('Offsite copy not found.', 404)
        if (not existing and (count>=5 or used+row['bytes']>512*1024**2 or global_used+row['bytes']>2*1024**3)) or shutil.disk_usage(self.e.backups).free<row['bytes']+64*1024**2:
            raise Fault('Make space within local backup allowances before fetching this copy.', 409)
        d = self.destination(row['destination'])
        remote = d['path'].rstrip('/')+'/'+row['backup_id']+'-'+row['sha256']+'.tar.gz'
        with tempfile.TemporaryDirectory(dir=str(self.e.backups)) as folder:
            stage = Path(folder) / 'incoming.tar.gz'
            self.transfer(d, ['get '+quoted(remote)+' '+quoted(stage)], folder)
            if stage.stat().st_size!=row['bytes'] or checksum(stage)!=row['sha256']:
                raise Fault('Offsite copy integrity verification failed. Existing local copies were preserved.', 409)
            target = self.e.backups/(row['backup_id']+'.tar.gz')
            os.replace(stage, target)
            with self.e.db() as db:
                db.execute("INSERT OR IGNORE INTO backups(id,user_id,site_id,domain,bytes,created,kind) VALUES(?,?,?,?,?,?,'full')", (row['backup_id'], row['user_id'], row['site_id'], row['domain'], row['bytes'], row['created']))
        return {}
