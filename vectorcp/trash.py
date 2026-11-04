"""Recoverable removal on the customer's own filesystem, outside public files.

Each root-only entry contains a durable metadata file and a payload. The payload
rename is the commit point, so interruption does not depend on a second database
transaction. No automatic expiry or background purge is performed.
"""
import contextlib
import json
import os
import re
import secrets
import stat
import time

from .core import Fault
from .filetools import MAX_FILE, rename_new, revision

OPERATIONS = {'files.trash', 'files.trash.list', 'files.trash.restore', 'files.trash.purge'}
READ_ONLY = {'files.trash.list'}


class Trash:
    def __init__(self, engine):
        self.e = engine

    @contextlib.contextmanager
    def directory(self, site):
        with self.e.directory(self.e.site_root(site).parent) as parent:
            try:
                os.mkdir('.vectorcp-trash', 0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
            fd = os.open('.vectorcp-trash', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if os.fstat(fd).st_uid != os.geteuid() or stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
                    raise Fault('Trash storage permissions need administrator repair.', 503)
                yield fd
            finally:
                os.close(fd)

    @staticmethod
    def metadata(entry):
        fd = os.open('metadata.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=entry)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise Fault('Trash metadata needs administrator repair.', 503)
            value = json.loads(stream.read(4097))
        if not isinstance(value, dict) or not isinstance(value.get('path'), str):
            raise Fault('Trash metadata needs administrator repair.', 503)
        return value

    def dispatch(self, db, actor, site, method, data):
        root = self.e.site_root(site)
        with self.directory(site) as trash:
            if method == 'files.trash.list':
                entries = []
                for ident in sorted(os.listdir(trash)):
                    if not re.fullmatch(r'[0-9a-f]{32}', ident):
                        continue
                    fd = os.open(ident, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=trash)
                    try:
                        metadata = self.metadata(fd)
                        try:
                            os.stat('payload', dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            # Crash before removal or after a successful restore/purge.
                            os.unlink('metadata.json', dir_fd=fd)
                            os.rmdir(ident, dir_fd=trash)
                            continue
                        entries.append(dict(metadata, id=ident))
                    finally:
                        os.close(fd)
                return {'entries': sorted(entries, key=lambda x: x['created'], reverse=True), 'limit': 100}
            if method == 'files.trash':
                if len(os.listdir(trash)) >= 100:
                    raise Fault('This website has 100 trash entries. Restore or permanently remove some first.', 409)
                folder, name = self.e.file_parts(data.get('path'), data.get('show_hidden', False))
                with self.e.directory(root, folder, data.get('show_hidden', False)) as parent:
                    st = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                        raise Fault('Only regular files and folders can be moved to trash.')
                    if revision(st) != data.get('revision'):
                        raise Fault('The selected item changed. Refresh and try again.', 409)
                    size, count = st.st_size, 1
                    if stat.S_ISDIR(st.st_mode):
                        contents, size, current = self.e.filetools.tree(root, data['path'])
                        count += len(contents)
                        if current != revision(st):
                            raise Fault('The selected folder changed. Refresh and try again.', 409)
                    if size > MAX_FILE:
                        raise Fault('Trash supports items containing up to 32 MB of files.')
                    ident = secrets.token_hex(16)
                    os.mkdir(ident, 0o700, dir_fd=trash)
                    os.fsync(trash)
                    entry = os.open(ident, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=trash)
                    try:
                        metadata = {'path': data['path'], 'created': int(time.time()), 'bytes': size,
                                    'entries': count, 'directory': stat.S_ISDIR(st.st_mode)}
                        fd = os.open('metadata.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=entry)
                        with os.fdopen(fd, 'w') as stream:
                            json.dump(metadata, stream)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.fsync(entry)
                        rename_new(parent, name, entry, 'payload')
                        os.fsync(parent)
                        os.fsync(entry)
                        os.fsync(trash)
                    finally:
                        # Ordinary failures before the rename leave no empty receipt.
                        try:
                            try:
                                os.stat('payload', dir_fd=entry, follow_symlinks=False)
                            except FileNotFoundError:
                                with contextlib.suppress(FileNotFoundError):
                                    os.unlink('metadata.json', dir_fd=entry)
                                os.rmdir(ident, dir_fd=trash)
                        finally:
                            os.close(entry)
                self.e.log(db, actor, 'file.trashed', site['domain'] + '/' + data['path'])
                return {'ok': True, 'id': ident}
            ident = data.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[0-9a-f]{32}', ident):
                raise Fault('Trash entry not found.', 404)
            try:
                entry = os.open(ident, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=trash)
            except FileNotFoundError:
                raise Fault('Trash entry not found.', 404)
            try:
                metadata = self.metadata(entry)
                if method == 'files.trash.restore':
                    target = data.get('destination') or metadata['path']
                    folder, name = self.e.file_parts(target, True)
                    with self.e.directory(root, folder, True) as parent:
                        rename_new(entry, 'payload', parent, name)
                        os.fsync(parent)
                    action = 'file.restored'
                elif method == 'files.trash.purge':
                    st = os.stat('payload', dir_fd=entry, follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        self.e.filetools.remove_tree(entry, 'payload')
                    else:
                        os.unlink('payload', dir_fd=entry)
                    action = 'file.trash_purged'
                else:
                    raise Fault('Unknown trash operation.', 404)
                os.fsync(entry)
                os.unlink('metadata.json', dir_fd=entry)
                os.rmdir(ident, dir_fd=trash)
                os.fsync(trash)
                self.e.log(db, actor, action, site['domain'] + '/' + metadata['path'])
                return {'ok': True}
            finally:
                os.close(entry)
