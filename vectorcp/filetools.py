"""Bounded website file transfers and operations; all paths are site relative.

Uploads are private, sequential and resumable for one hour. Publication is an
atomic no-replace rename, including when a website process creates the target
while an upload is in progress. No operation follows a symbolic link.
"""
import base64
import binascii
import contextlib
import ctypes
import errno
import hashlib
import os
import re
import secrets
import stat
import sys
import time

from .core import Fault, integer, text

CHUNK = 256 * 1024
MAX_FILE = 32 * 1024 * 1024
STAGING_LIMIT = 64 * 1024 * 1024
UPLOAD_TTL = 3600
READ_ONLY = {'files.describe', 'files.chunk', 'files.upload.status', 'files.search', 'files.permissions'}
READ_ONLY |= {'files.trash.list'}
OPERATIONS = READ_ONLY | {'files.upload.start', 'files.upload.chunk',
                         'files.upload.finish', 'files.upload.cancel',
                         'files.copy', 'files.move', 'files.remove', 'files.chmod', 'files.batch',
                         'files.trash', 'files.trash.restore', 'files.trash.purge',
                         'files.archive.create', 'files.archive.extract'}


def revision(st):
    return hashlib.sha256(('%s:%s:%s:%s:%s:%s' % (
        st.st_dev, st.st_ino, st.st_mode, st.st_size,
        st.st_mtime_ns, st.st_ctime_ns)).encode()).hexdigest()


def rename_new(source_fd, source, destination_fd, destination):
    """Fail closed if the OS cannot atomically refuse an existing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith('linux'):
        function, flags = getattr(libc, 'renameat2', None), 1  # RENAME_NOREPLACE
    elif sys.platform == 'darwin':
        function, flags = getattr(libc, 'renameatx_np', None), 4  # RENAME_EXCL
    else:
        function, flags = None, 0
    if function is None:
        raise Fault('Atomic file operations are unavailable on this platform.', 503)
    function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                         ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    if function(source_fd, os.fsencode(source), destination_fd,
                os.fsencode(destination), flags):
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise Fault('The destination already exists. Choose another name.', 409)
        raise OSError(code, os.strerror(code))


class FileTools:
    def __init__(self, engine):
        self.e = engine
        self.staging = engine.state / 'uploads'
        self.staging.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.staging, 0o700)
        with engine.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS file_uploads (
              id TEXT PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
              site_id INTEGER NOT NULL REFERENCES sites(id), path TEXT NOT NULL,
              bytes INTEGER NOT NULL, received INTEGER NOT NULL DEFAULT 0,
              sha256 TEXT NOT NULL, created INTEGER NOT NULL,
              completed INTEGER NOT NULL DEFAULT 0)''')
            self.expire(db)

    def expire(self, db):
        for row in db.execute('SELECT id FROM file_uploads WHERE created<?',
                              (int(time.time()) - UPLOAD_TTL,)).fetchall():
            self.discard(db, row['id'])
        for row in db.execute('SELECT id FROM file_uploads WHERE completed=1 ORDER BY created DESC,id LIMIT -1 OFFSET 2048').fetchall():
            self.discard(db, row['id'])
        # Recover from a crash between staging creation and the SQLite commit.
        known = {r['id'] for r in db.execute('SELECT id FROM file_uploads')}
        for name in os.listdir(self.staging):
            if re.fullmatch(r'[0-9a-f]{32}', name) and name not in known:
                (self.staging / name).unlink(missing_ok=True)

    def discard(self, db, ident):
        (self.staging / ident).unlink(missing_ok=True)
        db.execute('DELETE FROM file_uploads WHERE id=?', (ident,))

    def upload(self, db, actor, site, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[0-9a-f]{32}', ident):
            raise Fault('Upload not found.', 404)
        row = db.execute('SELECT * FROM file_uploads WHERE id=? AND actor_id=? AND site_id=?',
                         (ident, actor['id'], site['id'])).fetchone()
        if not row or row['created'] < int(time.time()) - UPLOAD_TTL:
            raise Fault('Upload not found or expired.', 404)
        return row

    @contextlib.contextmanager
    def regular(self, parent, name, maximum=MAX_FILE):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError:
            raise Fault('File not found or access refused.', 404)
        with os.fdopen(fd, 'rb') as stream:
            st = os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise Fault('Only regular files are supported.')
            if st.st_size > maximum:
                raise Fault('This operation supports files up to 32 MB.')
            yield stream, st

    def quota(self, db, site, additional):
        owner = db.execute('SELECT storage_mb FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if self.e.account_usage(db, site['user_id']) + additional > owner['storage_mb'] * 1024 * 1024:
            raise Fault('This account has reached its file storage limit.', 409)

    def entry_room(self, root, additional):
        count = 0
        for area in (root, root.parent / '.vectorcp-trash'):
            if area.is_symlink():
                continue
            for folder, dirs, files in os.walk(area, followlinks=False):
                count += len(dirs) + len(files)
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(folder, d))]
        if count + additional > (12000 if self.e.hosting.enabled else 1000):
            raise Fault('This operation would exceed the website’s file and folder entry limit (including trash).', 409)

    def publish(self, db, site, parent, name, stream, size, expected_hash=None):
        self.e.check_entry_limit(self.e.site_root(site))
        self.quota(db, site, size)
        temporary = '.vectorcp-' + secrets.token_hex(16)
        checksum, copied = hashlib.sha256(), 0
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            with os.fdopen(fd, 'wb') as output:
                while True:
                    chunk = stream.read(min(CHUNK, size - copied + 1))
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > size:
                        raise Fault('The source file changed. Refresh and try again.', 409)
                    checksum.update(chunk)
                    output.write(chunk)
                if copied != size or (expected_hash and checksum.hexdigest() != expected_hash):
                    raise Fault('The source file changed or its checksum did not match.', 409)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o644, dir_fd=parent, follow_symlinks=False)
            self.e.file_owner(db, site, parent, temporary)
            rename_new(parent, temporary, parent, name)
            os.fsync(parent)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent)
        return checksum.hexdigest()

    def dispatch(self, db, actor, site, method, data):
        try:
            return self.operation(db, actor, site, method, data)
        except OSError as error:
            if error.errno in (errno.ENOSPC, errno.EDQUOT):
                raise Fault('Storage is full. No destination file was replaced.', 409)
            raise Fault('The file operation could not be completed. Refresh the folder.', 409)

    def tree(self, root, source):
        """Snapshot a bounded regular-file tree, never following links or special files."""
        entries, total = [], 0
        def walk(fd, prefix='', depth=0):
            nonlocal total
            if depth > 32:
                raise Fault('Folder operations support at most 32 nested levels.')
            for name in sorted(os.listdir(fd)):
                if not self.e.file_name(name, True):
                    raise Fault('The folder contains an unsupported filename. Rename it before copying.')
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                    raise Fault('The folder contains a link or special file. Remove it from the selection.')
                path = prefix + name
                if len(source + '/' + path) > 512:
                    raise Fault('A nested file path is too long.')
                entries.append((path, stat.S_ISDIR(st.st_mode), revision(st), st.st_size))
                if len(entries) > 1000:
                    raise Fault('Folder operations support at most 1,000 entries.')
                if stat.S_ISREG(st.st_mode):
                    total += st.st_size
                    if total > MAX_FILE:
                        raise Fault('Folder operations support at most 32 MB of file content.')
                else:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, path + '/', depth + 1)
                    finally:
                        os.close(child)
        with self.e.directory(root, source, True) as fd:
            initial = revision(os.fstat(fd))
            walk(fd)
            if revision(os.fstat(fd)) != initial:
                raise Fault('The source folder changed. Refresh and try again.', 409)
        return entries, total, initial

    def remove_tree(self, parent, name):
        """Remove only our private temporary tree, using descriptors throughout."""
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            for child in os.listdir(fd):
                st = os.stat(child, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(st.st_mode):
                    self.remove_tree(fd, child)
                else:
                    os.unlink(child, dir_fd=fd)
        finally:
            os.close(fd)
        os.rmdir(name, dir_fd=parent)

    def copy_tree(self, db, site, data):
        root, source = self.e.site_root(site), data['path']
        target = data.get('destination')
        target_folder, target_name = self.e.file_parts(target, data.get('show_hidden', False))
        if target == source or target.startswith(source + '/'):
            raise Fault('Choose a destination outside the selected folder.')
        entries, size, initial = self.tree(root, source)
        if initial != data.get('revision'):
            raise Fault('The source folder changed. Refresh and try again.', 409)
        self.quota(db, site, size)
        self.entry_room(root, len(entries) + 1)
        with self.e.directory(root, target_folder, True) as destination, self.e.directory(root.parent) as staging_parent:
            for name in os.listdir(staging_parent):
                if re.fullmatch(r'\.vectorcp-copy-[0-9a-f]{32}', name):
                    self.remove_tree(staging_parent, name)
            temporary = '.vectorcp-copy-' + secrets.token_hex(16)
            os.mkdir(temporary, 0o700, dir_fd=staging_parent)
            stage = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=staging_parent)
            try:
                # Stage under a root-only directory on the destination filesystem.
                # The destination remains absent until every file has been checked.
                for path, is_dir, expected, length in entries:
                    folder, _, name = path.rpartition('/')
                    target_parent = os.dup(stage)
                    try:
                        for part in folder.split('/') if folder else []:
                            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=target_parent)
                            os.close(target_parent)
                            target_parent = child
                        if is_dir:
                            os.mkdir(name, 0o700, dir_fd=target_parent)
                        else:
                            with self.e.directory(root, source + ('/' + folder if folder else ''), True) as parent:
                                with self.regular(parent, name) as (stream, st):
                                    if revision(st) != expected:
                                        raise Fault('A source file changed. Refresh and try again.', 409)
                                    self.publish(db, site, target_parent, name, stream, length)
                                    if revision(os.fstat(stream.fileno())) != expected:
                                        raise Fault('A source file changed during the copy.', 409)
                    finally:
                        os.close(target_parent)
                if self.tree(root, source) != (entries, size, initial):
                    raise Fault('The source folder changed during the copy.', 409)
                # Normalize directory ownership only after all source checks pass.
                for path, is_dir, _, _ in reversed(entries):
                    if is_dir:
                        folder, _, name = path.rpartition('/')
                        parent = os.dup(stage)
                        try:
                            for part in folder.split('/') if folder else []:
                                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                                os.close(parent)
                                parent = child
                            os.chmod(name, 0o755, dir_fd=parent, follow_symlinks=False)
                            self.e.file_owner(db, site, parent, name, directory=True)
                        finally:
                            os.close(parent)
                os.fchmod(stage, 0o755)
                self.e.file_owner(db, site, staging_parent, temporary, directory=True)
                self.quota(db, site, size)
                self.entry_room(root, len(entries) + 1)
                os.fsync(stage)
                rename_new(staging_parent, temporary, destination, target_name)
                os.fsync(destination)
            finally:
                os.close(stage)
                with contextlib.suppress(FileNotFoundError):
                    self.remove_tree(staging_parent, temporary)
        return {'ok': True, 'entries': len(entries) + 1, 'bytes': size}

    def operation(self, db, actor, site, method, data):
        root = self.e.site_root(site)
        hidden = data.get('show_hidden', False)
        if not isinstance(hidden, bool):
            raise Fault('Invalid hidden-file preference.')
        parts = lambda value: self.e.file_parts(value, hidden)
        directory = lambda path, relative='': self.e.directory(path, relative, hidden)
        if method in {'files.trash', 'files.trash.list', 'files.trash.restore', 'files.trash.purge'}:
            return self.e.trash.dispatch(db, actor, site, method, data)
        if method in {'files.archive.create', 'files.archive.extract'}:
            return self.e.archives.dispatch(db, actor, site, method, data)
        if method == 'files.batch':
            items = data.get('items')
            operation = data.get('operation')
            if operation not in ('copy', 'move', 'remove') or not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise Fault('Choose an operation and between 1 and 20 items.')
            paths = []
            for item in items:
                if not isinstance(item, dict):
                    raise Fault('Invalid selected item.')
                parts(item.get('path'))
                if item['path'] in paths or any(item['path'].startswith(p + '/') or p.startswith(item['path'] + '/') for p in paths):
                    raise Fault('Select different items without also selecting a parent folder.')
                paths.append(item['path'])
            destination = data.get('destination', '')
            if operation != 'remove':
                with directory(root, destination):
                    pass
            results = []
            for item in items:
                values = dict(item, show_hidden=hidden)
                if operation != 'remove':
                    values['destination'] = '/'.join(filter(None, [destination, item['path'].rsplit('/', 1)[-1]]))
                try:
                    with db:  # Keep completed results even if a later item fails.
                        self.dispatch(db, actor, site, 'files.' + operation, values)
                    results.append({'path': item['path'], 'ok': True})
                except Fault as error:
                    results.append({'path': item['path'], 'ok': False, 'error': str(error), 'status': error.status})
            return {'results': results, 'ok': all(r['ok'] for r in results)}
        if method == 'files.upload.start':
            self.expire(db)
            size = integer(data.get('bytes'), 'file size', 0, MAX_FILE)
            checksum = data.get('sha256')
            if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
                raise Fault('A SHA-256 checksum is required.')
            path = data.get('path')
            folder, name = parts(path)
            with directory(root, folder) as parent:
                try:
                    os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise Fault('The destination already exists. Choose another name.', 409)
            self.e.check_entry_limit(root)
            reserved = db.execute('SELECT COALESCE(SUM(f.bytes),0) FROM file_uploads f JOIN sites s ON s.id=f.site_id WHERE s.user_id=? AND f.completed=0', (site['user_id'],)).fetchone()[0]
            self.quota(db, site, reserved + size)
            total, count = db.execute('SELECT COALESCE(SUM(bytes),0),COUNT(*) FROM file_uploads WHERE completed=0').fetchone()
            if total + size > STAGING_LIMIT or count >= 8:
                raise Fault('The upload staging area is busy. Finish or cancel another upload.', 409)
            ident = secrets.token_hex(16)
            fd = os.open(self.staging / ident, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            db.execute('INSERT INTO file_uploads(id,actor_id,site_id,path,bytes,sha256,created) VALUES(?,?,?,?,?,?,?)',
                       (ident, actor['id'], site['id'], path, size, checksum, int(time.time())))
            return {'id': ident, 'received': 0, 'chunk_bytes': CHUNK}
        if method.startswith('files.upload.'):
            row = self.upload(db, actor, site, data.get('id'))
            if method == 'files.upload.status':
                return {'id': row['id'], 'path': row['path'], 'bytes': row['bytes'],
                        'received': row['received'], 'chunk_bytes': CHUNK, 'completed': bool(row['completed'])}
            if method == 'files.upload.cancel':
                self.discard(db, row['id'])
                return {'ok': True}
            if row['completed']:
                if method == 'files.upload.finish':
                    return {'ok': True, 'sha256': row['sha256']}
                raise Fault('This upload is already complete.', 409)
            if method == 'files.upload.chunk':
                offset = integer(data.get('offset'), 'upload offset', 0, row['bytes'])
                encoded = data.get('base64')
                if not isinstance(encoded, str) or len(encoded) > ((CHUNK + 2) // 3) * 4:
                    raise Fault('Upload chunks must be at most 256 KB.')
                try:
                    chunk = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    raise Fault('Invalid upload data.')
                if not chunk or len(chunk) > CHUNK or offset + len(chunk) > row['bytes']:
                    raise Fault('Invalid upload chunk size.')
                fd = os.open(self.staging / row['id'], os.O_RDWR | os.O_NOFOLLOW)
                with os.fdopen(fd, 'r+b') as stream:
                    if os.fstat(fd).st_size < row['received']:
                        raise Fault('Upload staging data is incomplete. Cancel and retry.', 409)
                    if offset < row['received']:
                        stream.seek(offset)
                        if offset + len(chunk) > row['received'] or stream.read(len(chunk)) != chunk:
                            raise Fault('Upload offset does not match. Resume from its received size.', 409)
                        return {'received': row['received']}
                    if offset != row['received']:
                        raise Fault('Upload offset does not match. Resume from its received size.', 409)
                    stream.truncate(offset)
                    stream.seek(offset)
                    stream.write(chunk)
                    stream.flush()
                    os.fsync(fd)
                received = offset + len(chunk)
                db.execute('UPDATE file_uploads SET received=? WHERE id=?', (received, row['id']))
                return {'received': received}
            if row['received'] != row['bytes']:
                raise Fault('The upload is incomplete.', 409)
            folder, name = parts(row['path'])
            with directory(root, folder) as parent, self.regular(None, self.staging / row['id']) as (stream, st):
                checksum = self.publish(db, site, parent, name, stream, row['bytes'], row['sha256'])
            # Retain a short-lived completion receipt for a lost HTTP response.
            (self.staging / row['id']).unlink(missing_ok=True)
            db.execute('UPDATE file_uploads SET completed=1 WHERE id=?', (row['id'],))
            self.e.log(db, actor, 'file.uploaded', site['domain'] + '/' + row['path'])
            return {'ok': True, 'sha256': checksum}
        if method == 'files.search':
            query = text(data.get('query'), 'search', 100).casefold()
            matches, scanned = [], 0
            def walk(parent, prefix=''):
                nonlocal scanned
                for name in sorted(os.listdir(parent)):
                    if not self.e.file_name(name, hidden):
                        continue
                    scanned += 1
                    if scanned > 12000 or len(matches) >= 200:
                        return
                    try:
                        st = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                            continue
                        path = prefix + name
                        if query in name.casefold():
                            matches.append({'path': path, 'directory': stat.S_ISDIR(st.st_mode),
                                            'bytes': st.st_size, 'revision': revision(st)})
                        if stat.S_ISDIR(st.st_mode) and len(path) < 310:
                            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                            try:
                                walk(child, path + '/')
                            finally:
                                os.close(child)
                    except (FileNotFoundError, NotADirectoryError):
                        continue
            with directory(root) as parent:
                walk(parent)
            return {'files': matches, 'limited': scanned > 12000 or len(matches) >= 200}
        folder, name = parts(data.get('path'))
        with directory(root, folder) as parent:
            if method == 'files.copy' and stat.S_ISDIR(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode):
                result = self.copy_tree(db, site, data)
                self.e.log(db, actor, 'folder.copied', site['domain'] + '/' + data['path'])
                return result
            if method in ('files.permissions', 'files.chmod'):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    st = os.fstat(fd)
                    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                        raise Fault('Only regular files and folders have editable permissions.')
                    owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
                    choices = ['700', '750', '755'] if stat.S_ISDIR(st.st_mode) else ['600', '640', '644', '700', '750', '755']
                    if method == 'files.chmod':
                        mode = data.get('mode')
                        if mode not in choices:
                            raise Fault('Choose an allowed permission mode. Shared write and special bits are refused.')
                        if data.get('revision') != revision(st):
                            raise Fault('The item changed. Refresh and try again.', 409)
                        # Ownership can only be normalized to this site's customer;
                        # the API never accepts a UID/GID or another account.
                        if owner['hosting_slot'] is not None:
                            ident = self.e.hosting.identity(self.e.hosting.slot(owner))
                            os.fchown(fd, ident.pw_uid, ident.pw_gid)
                        os.fchmod(fd, int(mode, 8))
                        os.fsync(fd)
                        self.e.log(db, actor, 'file.permissions_changed', site['domain'] + '/' + data['path'])
                    final = os.fstat(fd)
                    return {'mode': format(stat.S_IMODE(final.st_mode), '03o'), 'revision': revision(final),
                            'choices': choices, 'owner': owner['username'], 'isolated': owner['hosting_slot'] is not None}
                finally:
                    os.close(fd)
            if method in ('files.describe', 'files.chunk', 'files.copy'):
                with self.regular(parent, name) as (stream, st):
                    current = revision(st)
                    if method == 'files.describe':
                        checksum = hashlib.sha256()
                        remaining = MAX_FILE + 1
                        while remaining:
                            chunk = stream.read(min(CHUNK, remaining))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            checksum.update(chunk)
                        if remaining == 0 or revision(os.fstat(stream.fileno())) != current:
                            raise Fault('The file changed. Refresh and try again.', 409)
                        return {'bytes': st.st_size, 'revision': current, 'sha256': checksum.hexdigest(), 'chunk_bytes': CHUNK}
                    if data.get('revision') != current:
                        raise Fault('The file changed. Refresh and try again.', 409)
                    if method == 'files.chunk':
                        offset = integer(data.get('offset'), 'download offset', 0, st.st_size)
                        stream.seek(offset)
                        chunk = stream.read(min(CHUNK, st.st_size - offset))
                        if revision(os.fstat(stream.fileno())) != current:
                            raise Fault('The file changed. Start the download again.', 409)
                        return {'base64': base64.b64encode(chunk).decode(), 'offset': offset,
                                'next': offset + len(chunk), 'bytes': st.st_size}
                    target = data.get('destination')
                    target_folder, target_name = parts(target)
                    with directory(root, target_folder) as destination:
                        # Hash the source first so changes during the copy are rejected.
                        checksum = hashlib.sha256()
                        for chunk in iter(lambda: stream.read(CHUNK), b''):
                            checksum.update(chunk)
                            if stream.tell() > MAX_FILE:
                                raise Fault('The source file changed.', 409)
                        if revision(os.fstat(stream.fileno())) != current:
                            raise Fault('The source file changed.', 409)
                        stream.seek(0)
                        self.publish(db, site, destination, target_name, stream, st.st_size, checksum.hexdigest())
            else:
                st = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                    raise Fault('Symbolic links and special files cannot be changed.')
                if data.get('revision') != revision(st):
                    raise Fault('The item changed. Refresh and try again.', 409)
                if method == 'files.move':
                    target = data.get('destination')
                    target_folder, target_name = parts(target)
                    if target == data['path'] or target.startswith(data['path'] + '/'):
                        raise Fault('Choose a destination outside the selected folder.')
                    with directory(root, target_folder) as destination:
                        rename_new(parent, name, destination, target_name)
                        os.fsync(destination)
                elif method == 'files.remove':
                    if stat.S_ISDIR(st.st_mode):
                        os.rmdir(name, dir_fd=parent)  # Refuse nonempty directories.
                    else:
                        os.unlink(name, dir_fd=parent)
                else:
                    raise Fault('Unknown file operation.', 404)
            os.fsync(parent)
        self.e.log(db, actor, method[6:], site['domain'] + '/' + data['path'])
        return {'ok': True}
