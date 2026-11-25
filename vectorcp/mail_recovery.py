"""Root-only, check-first Maildir snapshots and additive message recovery.

No Engine is constructed: read-only checks must not recover hosting jobs. Native
mail is quiesced for apply, and the existing startup checkpoint fails closed.
Snapshots are private local directories, not untrusted uploaded archives.
"""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import sqlite3
import stat
import time
from types import SimpleNamespace

from .core import Fault
from .distribution import Distribution
from .mail import Mail
from . import mail_profile as profile

MAX_MESSAGES = 10000
MAX_FOLDERS = 256
MAX_BYTES = 256 * 1048576
MAX_SNAPSHOTS = 64
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1048576
HEADROOM = 256 * 1048576
IDENT = re.compile(r'[a-f0-9]{24}\Z')
OPERATION = 'message-recovery'


def present(path):
    return path.exists() or path.is_symlink()


def safe_directory(path, private=False):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (private and (info.st_uid != os.geteuid() or info.st_mode & 0o077)):
        raise Fault('A recovery directory has an unsafe owner, type or permissions.')


@contextmanager
def regular(path, private=False, maximum=MAX_BYTES):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > maximum
                or (private and (info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1))):
            raise Fault('A recovery file has an unsafe owner, type, size or permissions.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            yield stream, info
    finally:
        os.close(fd)


def measure(stream, output=None):
    sha, size, extra, previous = hashlib.sha256(), 0, 0, b''
    while True:
        chunk = stream.read(1048576)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BYTES:
            raise Fault('A message exceeds the recovery size limit.')
        sha.update(chunk)
        # Dovecot quota_vsizes counts CRLF-normalized message bytes.
        extra += chunk.count(b'\n') - (previous + chunk).count(b'\r\n')
        previous = chunk[-1:]
        if output:
            output.write(chunk)
    return sha.hexdigest(), size, size + extra


def folder_name(value):
    return (isinstance(value, str) and len(value.encode()) <= 160
            and '/' not in value and '\\' not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and (value == '' or (value.startswith('.') and all(value[1:].split('.')))))


def message_name(value):
    return (isinstance(value, str) and 1 <= len(value.encode()) <= 255
            and value not in ('.', '..') and '/' not in value and '\\' not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def keywords(path):
    if not present(path):
        return ''
    with regular(path, maximum=16384) as (stream, _):
        value = stream.read().decode('utf-8')
    validate_keywords(value)
    return value


def validate_keywords(value):
    ids, names = set(), set()
    for line in value.splitlines():
        match = re.fullmatch(r'([0-9]|1[0-9]|2[0-5]) ([^\s\x00-\x1f\x7f]{1,64})', line)
        if not match or int(match[1]) in ids or match[2] in names:
            raise Fault('The mailbox keyword map is unsupported; it was preserved.')
        ids.add(int(match[1])); names.add(match[2])


class Recovery:
    def __init__(self, state=profile.STATE, development=False):
        self.state = Path(state)
        self.development = development
        engine = SimpleNamespace(state=self.state, development=development, db_path=self.state / 'control.sqlite3')
        engine.distribution = Distribution(engine)
        self.mail = Mail(engine)
        self.root = self.state / 'mail-snapshots'
        self.maintenance = self.state / 'profile-maintenance' if development else Path('/run/vectorcp-profile-maintenance')
        if development:
            self.uid, self.gid = os.geteuid(), os.getegid()
        else:
            try:
                user = pwd.getpwnam('vectorcp-vmail')
            except KeyError:
                raise Fault('Install the optional managed native mail profile first.')
            self.uid, self.gid = user.pw_uid, user.pw_gid

    @contextmanager
    def db(self):
        with closing(sqlite3.connect('file:' + str(self.state / 'control.sqlite3') + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            yield db

    def mailbox(self, db, address):
        row = db.execute('SELECT b.id,b.site_id,b.local,b.quota_mb,s.domain,s.user_id FROM mailboxes b JOIN sites s ON s.id=b.site_id WHERE b.local || \'@\' || s.domain=?', (address,)).fetchone()
        if not row or not re.fullmatch(r'[a-f0-9]{32}', row['id']):
            raise Fault('Choose an existing mailbox by its exact lowercase email address.')
        return {'mailbox_id': row['id'], 'site_id': row['site_id'], 'user_id': row['user_id'], 'address': address, 'quota_mb': row['quota_mb']}

    def healthy(self, db, recovering=False):
        installed = self.mail.profile
        if not installed:
            raise Fault('Install the optional managed native mail profile first.')
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise Fault('Wait for hosting jobs before mail recovery maintenance.')
        if not self.development:
            for path, expected in ((Path('/etc/dovecot/dovecot.conf'), profile.dovecot_config(installed['listen'], self.uid, self.gid)),
                                   (Path('/etc/postfix/main.cf'), profile.postfix_config(installed['hostname'], installed['listen'], installed.get('aliases') is True))):
                with regular(path, maximum=65536) as (stream, _):
                    if stream.read().decode() != expected:
                        raise Fault('Native mail configuration was customized; recovery was refused without changing it.')
            if not os.path.ismount(self.mail.store) or not os.path.ismount('/var/spool/postfix'):
                raise Fault('Both bounded mail volumes must be mounted.')
        if self.mail.current_digest() != self.mail.digest(self.mail.snapshot(db)):
            raise Fault('Recover committed mail configuration before message maintenance.')
        if not recovering and (present(self.mail.pending) or present(self.maintenance)
                               or any(v != 'active' for v in self.mail.services().values())):
            raise Fault('Inspect and recover existing mail or profile maintenance first.')
        return installed

    def home(self, box):
        safe_directory(self.mail.store)
        home = self.mail.store / box['mailbox_id']
        if present(home):
            safe_directory(home)
        return home / 'Maildir'

    def inventory(self, box, target=None):
        root = self.home(box)
        folders, messages, total, virtual = {'': ''}, [], 0, 0
        if not present(root):
            return folders, messages, total, virtual
        safe_directory(root)
        for path in sorted(root.iterdir()):
            if path.is_symlink():
                raise Fault('A mailbox contains a link. No message recovery was published.')
            if path.name.startswith('.') and path.is_dir():
                if not folder_name(path.name):
                    raise Fault('A mailbox folder exceeds the recovery path limits.')
                folders[path.name] = ''
        if len(folders) > MAX_FOLDERS:
            raise Fault('A mailbox exceeds the 256-folder recovery limit.')
        for folder in folders:
            source = root / folder if folder else root
            safe_directory(source)
            folders[folder] = keywords(source / 'dovecot-keywords')
            for bucket in ('cur', 'new'):
                directory = source / bucket
                if not present(directory):
                    continue
                safe_directory(directory)
                for path in sorted(directory.iterdir()):
                    if not message_name(path.name) or len(messages) >= MAX_MESSAGES:
                        raise Fault('A mailbox exceeds the recovery name or 10,000-message limits.')
                    with regular(path) as (stream, info):
                        item = {'folder': folder, 'bucket': bucket, 'name': path.name, 'mtime_ns': info.st_mtime_ns}
                        if target:
                            output_path = target / ('%05d' % len(messages))
                            fd = os.open(str(output_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                            with os.fdopen(fd, 'wb') as output:
                                sha, size, vsize = measure(stream, output)
                                output.flush(); os.fsync(output.fileno())
                        else:
                            sha, size, vsize = measure(stream)
                        after = os.fstat(stream.fileno())
                        if (after.st_mtime_ns, after.st_size, after.st_ino) != (info.st_mtime_ns, info.st_size, info.st_ino) or size != info.st_size:
                            raise Fault('A mailbox changed during inspection. Retry after stopping other mail writers.')
                    total += size; virtual += vsize
                    if total > MAX_BYTES:
                        raise Fault('A mailbox exceeds the 256 MB message recovery limit.')
                    item.update(sha256=sha, bytes=size, virtual_bytes=vsize)
                    messages.append(item)
        return folders, messages, total, virtual

    def read_snapshot(self, ident):
        if not isinstance(ident, str) or not IDENT.fullmatch(ident):
            raise Fault('Use an existing 24-character snapshot identifier.')
        safe_directory(self.root, private=True)
        path = self.root / ident
        safe_directory(path, private=True)
        with regular(path / 'manifest.json', private=True, maximum=4 * 1048576) as (stream, _):
            d = json.load(stream)
        if (not isinstance(d, dict) or d.get('version') != 1 or d.get('id') != ident
                or not isinstance(d.get('folders'), dict) or not 1 <= len(d['folders']) <= MAX_FOLDERS
                or '' not in d['folders'] or not all(folder_name(f) and isinstance(k, str) and len(k.encode()) <= 16384 for f, k in d['folders'].items())
                or not isinstance(d.get('messages'), list) or len(d['messages']) > MAX_MESSAGES):
            raise Fault('The private snapshot manifest is invalid.')
        data = path / 'messages'
        safe_directory(data, private=True)
        seen, total, virtual = set(), 0, 0
        for index, item in enumerate(d['messages']):
            if (not isinstance(item, dict) or item.get('folder') not in d['folders'] or item.get('bucket') not in ('new', 'cur')
                    or not message_name(item.get('name')) or type(item.get('mtime_ns')) is not int or not 0 <= item['mtime_ns'] < 2**63):
                raise Fault('The snapshot message manifest is invalid.')
            key = item['folder'], item['bucket'], item['name']
            if key in seen:
                raise Fault('The snapshot contains duplicate message paths.')
            seen.add(key)
            with regular(data / ('%05d' % index), private=True) as (stream, _):
                sha, size, vsize = measure(stream)
            if (sha, size, vsize) != (item.get('sha256'), item.get('bytes'), item.get('virtual_bytes')):
                raise Fault('Snapshot verification failed. Original mailbox data was preserved.')
            total += size; virtual += vsize
            if total > MAX_BYTES:
                raise Fault('The snapshot exceeds the 256 MB recovery limit.')
        if total != d.get('bytes') or virtual != d.get('virtual_bytes') or set(p.name for p in data.iterdir()) != {'%05d' % i for i in range(len(d['messages']))}:
            raise Fault('The snapshot content inventory is inconsistent.')
        for value in d['folders'].values():
            validate_keywords(value)
        return d

    def identity(self, snapshot, box):
        if any(snapshot.get(key) != box[key] for key in ('mailbox_id', 'site_id', 'user_id', 'address')):
            raise Fault('The snapshot belongs to a different mailbox or account. Cross-account restore is not supported.')

    def room(self, destination, size, headroom=HEADROOM):
        if shutil.disk_usage(destination).free < size + headroom:
            raise Fault('Insufficient free storage for recovery and its reserved headroom.')

    def snapshot_room(self, size, adding=True):
        if not present(self.root):
            self.room(self.state, size)
            return
        safe_directory(self.root, private=True)
        count, total = 0, 0
        for path in self.root.iterdir():
            if IDENT.fullmatch(path.name) or path.name.startswith('.partial-'):
                safe_directory(path, private=True)
                count += 1
                for parent, dirs, files in os.walk(path, followlinks=False):
                    for name in dirs:
                        safe_directory(Path(parent) / name, private=True)
                    for name in files:
                        with regular(Path(parent) / name, private=True) as (_, info):
                            total += info.st_size
        if count + int(adding) > MAX_SNAPSHOTS or total + size > MAX_SNAPSHOT_BYTES:
            raise Fault('Local snapshots reached the 64-snapshot or 2 GB limit. Retain verified offsite copies and manage them as root before retrying.')
        self.room(self.root, size)

    def frontends(self):
        return ['vectorcp-web'] + (['vectorcp-web-public'] if Path('/etc/systemd/system/vectorcp-web-public.service').exists() else [])

    def service(self, action, units):
        if not self.development:
            self.mail.run(['/usr/bin/systemctl', action] + units)

    def start_panel(self):
        self.service('start', ['vectorcp-agent'] + self.frontends())
        if not self.development:
            self.mail.run(['/usr/bin/curl', '--fail', '--silent', '--retry', '10', '--retry-connrefused',
                           '--retry-delay', '1', '--max-time', '2', 'http://127.0.0.1:8765/healthz'])

    def write(self, path, value):
        # The profile writer owns native files as root; tests use their own UID.
        if self.development:
            temporary = path.with_name(path.name + '.new-' + secrets.token_hex(4))
            fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(value.encode() if isinstance(value, str) else value); f.flush(); os.fsync(f.fileno())
            os.replace(temporary, path); self.mail.fsync(path.parent)
        else:
            profile.write(path, value, 0o600)

    def journal(self, data):
        self.write(self.mail.pending, json.dumps(data, sort_keys=True) + '\n')

    def begin(self, data):
        self.write(self.maintenance, OPERATION + '\n')
        self.service('stop', self.frontends())
        with self.db() as db:
            self.healthy(db, recovering=True)  # Recheck jobs before stopping the agent.
        self.service('stop', ['vectorcp-agent'])
        with self.db() as db:
            self.healthy(db, recovering=True)
        if present(self.mail.pending):
            raise Fault('Mail acquired another checkpoint during preflight; inspect it before retrying.')
        self.journal(data)
        self.mail.stop()

    def finish(self, data):
        data['phase'] = 'committed'
        self.journal(data)
        self.mail.pending.unlink(); self.mail.fsync(self.mail.base)
        self.service('start', ['dovecot', 'postfix'])
        if not self.development:
            for unit in ('dovecot', 'postfix'):
                self.mail.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit])
        self.maintenance.unlink(); self.mail.fsync(self.maintenance.parent)
        self.start_panel()

    def fail_closed(self, data):
        # Never clear another operator's checkpoint on error.
        if not present(self.mail.pending):
            self.journal(data)
        self.mail.stop()
        self.start_panel()

    def backup(self, address, apply=False):
        with self.db() as db:
            self.healthy(db); box = self.mailbox(db, address)
        inventory = self.inventory(box)
        self.snapshot_room(inventory[2] + 4 * 1048576)
        if not apply:
            return {'check_only': True, 'address': address, 'messages': len(inventory[1]), 'bytes': inventory[2]}
        ident = secrets.token_hex(12)
        data = {'operation': OPERATION, 'action': 'backup', 'phase': 'staging', 'snapshot': ident, 'address': address, 'mailbox_id': box['mailbox_id']}
        try:
            self.begin(data)
            with self.db() as db:
                self.healthy(db, recovering=True); self.identity(box, self.mailbox(db, address))
            frozen = self.inventory(box)
            self.snapshot_room(frozen[2] + 4 * 1048576)
            self.root.mkdir(mode=0o700, exist_ok=True); safe_directory(self.root, private=True)
            self.mail.fsync(self.state)
            stage = self.root / ('.partial-' + ident)
            stage.mkdir(mode=0o700); (stage / 'messages').mkdir(mode=0o700)
            folders, entries, size, vsize = self.inventory(box, stage / 'messages')
            self.snapshot_room(0, adding=False)
            snapshot = dict(box, version=1, id=ident, created=int(time.time()), folders=folders, messages=entries, bytes=size, virtual_bytes=vsize)
            self.write(stage / 'manifest.json', json.dumps(snapshot, ensure_ascii=True, sort_keys=True) + '\n')
            self.mail.fsync(stage / 'messages'); self.mail.fsync(stage)
            os.rename(stage, self.root / ident); self.mail.fsync(self.root)
            self.read_snapshot(ident)
            self.finish(data)
            return {'id': ident, 'address': address, 'messages': len(entries), 'bytes': size}
        except BaseException:
            self.fail_closed(data)
            raise

    def targets(self, snapshot):
        prefix = '.Recovered-' + snapshot['id']
        result = {folder: prefix + folder for folder in snapshot['folders']}
        if not all(folder_name(name) for name in result.values()):
            raise Fault('The recovered folder names would exceed this profile\'s path limit. Inspect nested recovery trees first.')
        return result

    def restore_preflight(self, ident, address):
        with self.db() as db:
            self.healthy(db); box = self.mailbox(db, address)
        snapshot = self.read_snapshot(ident); self.identity(snapshot, box)
        current = self.inventory(box)
        self.restore_limits(box, snapshot, current)
        root = self.home(box)
        if any(present(root / name) for name in self.targets(snapshot).values()):
            raise Fault('This recovery folder tree already exists. Existing recovered messages were preserved.')
        self.room(self.mail.store, snapshot['bytes'] + 16 * 1048576, headroom=0)
        return box, snapshot

    def restore_limits(self, box, snapshot, current):
        if current[3] + snapshot['virtual_bytes'] > box['quota_mb'] * 1048576:
            raise Fault('Current and recovered messages would exceed this mailbox quota. Increase its reservation before restoring.')
        if (current[2] + snapshot['bytes'] > MAX_BYTES
                or len(current[1]) + len(snapshot['messages']) > MAX_MESSAGES
                or len(current[0]) + len(snapshot['folders']) > MAX_FOLDERS):
            raise Fault('The recovered mailbox would exceed this message recovery profile\'s size, message or folder limits.')

    def restore(self, ident, address, apply=False):
        box, snapshot = self.restore_preflight(ident, address)
        if not apply:
            return {'check_only': True, 'id': ident, 'address': address, 'messages': len(snapshot['messages']), 'folder': 'Recovered-' + ident}
        data = {'operation': OPERATION, 'action': 'restore', 'phase': 'staging', 'snapshot': ident, 'address': address, 'mailbox_id': box['mailbox_id'], 'staging_id': secrets.token_hex(12)}
        try:
            self.begin(data)
            # Services are stopped; repeat identity, current quota and collision checks.
            with self.db() as db:
                self.healthy(db, recovering=True); current_box = self.mailbox(db, address)
            self.identity(snapshot, current_box)
            current = self.inventory(current_box)
            self.restore_limits(current_box, snapshot, current)
            self.room(self.mail.store, snapshot['bytes'] + 16 * 1048576, headroom=0)
            stage = self.mail.store / ('.vectorcp-recovery-' + data['staging_id'])
            stage.mkdir(mode=0o700)
            self.mail.fsync(self.mail.store)
            self.prepare_folders(snapshot, stage)
            data['phase'] = 'prepared'; self.journal(data)
            root = self.home(box)
            for directory in (root.parent, root):
                if not present(directory):
                    directory.mkdir(mode=0o700); os.chown(directory, self.uid, self.gid)
                    self.mail.fsync(directory.parent)
                safe_directory(directory)
            for name in self.targets(snapshot).values():
                if present(root / name):
                    raise Fault('A recovery destination appeared during maintenance; it was preserved.')
                os.rename(stage / name, root / name)
                self.mail.fsync(root); self.mail.fsync(stage)
            if not self.development:
                self.mail.run(['/usr/sbin/restorecon', '-RF', str(root)])
            self.finish(data)
            return {'id': ident, 'address': address, 'messages': len(snapshot['messages']), 'folder': 'Recovered-' + ident}
        except BaseException:
            self.fail_closed(data)
            raise

    def prepare_folders(self, snapshot, stage):
        targets = self.targets(snapshot)
        for folder, name in targets.items():
            path = stage / name
            path.mkdir(mode=0o700)
            for bucket in ('cur', 'new', 'tmp'):
                (path / bucket).mkdir(mode=0o700)
            for label, value in (('maildirfolder', ''), ('dovecot-keywords', snapshot['folders'][folder])):
                self.write(path / label, value)
            for child in path.iterdir():
                os.chown(child, self.uid, self.gid)
            os.chown(path, self.uid, self.gid)
        for index, item in enumerate(snapshot['messages']):
            path = stage / targets[item['folder']] / item['bucket'] / item['name']
            with regular(self.root / snapshot['id'] / 'messages' / ('%05d' % index), private=True) as (source, _):
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as output:
                    sha, size, vsize = measure(source, output)
                    if (sha, size, vsize) != (item['sha256'], item['bytes'], item['virtual_bytes']):
                        raise Fault('Snapshot changed during recovery staging.')
                    os.fchown(output.fileno(), self.uid, self.gid)
                    output.flush()
                    os.utime(output.fileno(), ns=(item['mtime_ns'], item['mtime_ns']))
                    os.fsync(output.fileno())
        for parent, dirs, _ in os.walk(stage, topdown=False):
            for name in dirs:
                self.mail.fsync(Path(parent) / name)
        self.mail.fsync(stage)

    def verify_folder(self, snapshot, name, path):
        safe_directory(path)
        if set(p.name for p in path.iterdir()) != {'cur', 'new', 'tmp', 'maildirfolder', 'dovecot-keywords'}:
            raise Fault('A published recovery folder changed. Inspect its retained messages manually.')
        folder = next(f for f, target in self.targets(snapshot).items() if target == name)
        if keywords(path / 'dovecot-keywords') != snapshot['folders'][folder]:
            raise Fault('A recovery keyword map changed. Inspect it before proceeding.')
        with regular(path / 'maildirfolder', maximum=0):
            pass
        for bucket in ('cur', 'new', 'tmp'):
            directory = path / bucket
            safe_directory(directory)
            expected = {item['name']: item for item in snapshot['messages'] if item['folder'] == folder and item['bucket'] == bucket}
            if set(p.name for p in directory.iterdir()) != set(expected):
                raise Fault('Recovery messages changed during maintenance; no unexpected messages were withdrawn.')
            for filename, item in expected.items():
                with regular(directory / filename) as (stream, info):
                    sha, size, vsize = measure(stream)
                if (sha, size, vsize, info.st_mtime_ns) != (item['sha256'], item['bytes'], item['virtual_bytes'], item['mtime_ns']):
                    raise Fault('A recovery message changed. Inspect it before proceeding.')

    def recover(self, apply=False):
        with regular(self.mail.pending, private=True, maximum=4096) as (stream, _):
            data = json.load(stream)
        if (data.get('operation') != OPERATION or data.get('action') not in ('backup', 'restore')
                or data.get('phase') not in ('staging', 'prepared', 'committed')
                or not isinstance(data.get('snapshot'), str) or not IDENT.fullmatch(data['snapshot'])
                or (data.get('action') == 'restore' and (not isinstance(data.get('staging_id'), str) or not IDENT.fullmatch(data['staging_id'])))):
            raise Fault('This checkpoint is not a supported message-recovery operation.')
        if present(self.maintenance):
            with regular(self.maintenance, private=True, maximum=100) as (stream, _):
                if stream.read() != (OPERATION + '\n').encode():
                    raise Fault('Another profile maintenance marker must be inspected first.')
        with self.db() as db:
            self.healthy(db, recovering=True); box = self.mailbox(db, data['address'])
        if box['mailbox_id'] != data.get('mailbox_id'):
            raise Fault('The mailbox identity changed; inspect recovery staging manually.')
        if not apply:
            return {'check_only': True, 'action': data['action'], 'phase': data['phase'], 'address': data['address']}
        committed = data['phase'] == 'committed'
        try:
            if not present(self.maintenance):
                self.write(self.maintenance, OPERATION + '\n')  # /run is lost on reboot.
            self.service('stop', self.frontends())
            with self.db() as db:
                self.healthy(db, recovering=True)
            self.service('stop', ['vectorcp-agent']); self.mail.stop()
            if data['action'] == 'restore' and data['phase'] != 'committed':
                snapshot = self.read_snapshot(data['snapshot']); self.identity(snapshot, box)
                stage = self.mail.store / ('.vectorcp-recovery-' + data['staging_id'])
                if present(stage):
                    safe_directory(stage, private=True)
                elif data['phase'] == 'prepared':
                    raise Fault('Recovery staging is missing. Inspect the retained mailbox before recovery.')
                root = self.home(box)
                # Move only this operation's newly published folders back to its
                # private staging. Existing INBOX, folders and newer mail stay put.
                if data['phase'] == 'prepared':
                    for name in self.targets(snapshot).values():
                        source, target = root / name, stage / name
                        if present(source) and present(target):
                            raise Fault('Both recovery paths exist. Inspect them without deleting either.')
                        if present(source):
                            self.verify_folder(snapshot, name, source)
                            os.rename(source, target); self.mail.fsync(root); self.mail.fsync(stage)
                        elif not present(target):
                            raise Fault('A recovery folder is missing. Inspect retained data before proceeding.')
            self.finish(data)
            return {'ok': True, 'result': 'committed operation finalized' if committed else 'interrupted operation withdrawn; staged data retained privately'}
        except BaseException:
            self.fail_closed(data)
            raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('backup', 'restore', 'recover', 'list'))
    p.add_argument('--mailbox', help='Exact existing lowercase email address')
    p.add_argument('--snapshot', help='Private local snapshot identifier')
    p.add_argument('--apply', action='store_true', help='Pause mail and apply; otherwise check only')
    args = p.parse_args()
    if os.geteuid() != 0 or not Path('/etc/almalinux-release').is_file() or 'release 9.' not in Path('/etc/almalinux-release').read_text():
        raise SystemExit('Run as root on the supported AlmaLinux 9 VectorCP installation.')
    if args.action in ('backup', 'restore') and not args.mailbox:
        p.error('--mailbox is required')
    if args.action == 'restore' and not args.snapshot:
        p.error('--snapshot is required')
    if args.action == 'list' and args.apply:
        p.error('list is read-only')
    try:
        recovery = Recovery()
        def run():
            if args.action == 'backup':
                return recovery.backup(args.mailbox, args.apply)
            if args.action == 'restore':
                return recovery.restore(args.snapshot, args.mailbox, args.apply)
            if args.action == 'recover':
                return recovery.recover(args.apply)
            rows = []
            if present(recovery.root):
                safe_directory(recovery.root, private=True)
                for path in sorted(recovery.root.iterdir()):
                    if IDENT.fullmatch(path.name):
                        d = recovery.read_snapshot(path.name)
                        rows.append({key: d[key] for key in ('id', 'address', 'created', 'bytes')})
            return {'snapshots': rows}
        if args.apply:
            with (profile.STATE / 'profile-maintenance.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = run()
        else:
            result = run()
        print(json.dumps(result, indent=2))
    except (Fault, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        raise SystemExit(str(error))


if __name__ == '__main__':
    main()
