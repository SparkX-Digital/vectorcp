"""Bounded ZIP creation and extraction with private staging and safe paths."""
import contextlib
import os
import re
import secrets
import stat
import struct
import zipfile

from .core import Fault
from .filetools import CHUNK, MAX_FILE, rename_new, revision


class Archives:
    def __init__(self, engine):
        self.e = engine

    @contextlib.contextmanager
    def child(self, root, path='', create=False):
        fd = os.dup(root)
        try:
            for part in path.split('/') if path else []:
                if create:
                    with contextlib.suppress(FileExistsError):
                        os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def manifest(self, archive, destination):
        infos = archive.infolist()
        if not infos or len(infos) > 1000:
            raise Fault('Choose a ZIP with between 1 and 1,000 entries.')
        declared, paths, size = set(), {}, 0
        for info in infos:
            if info.orig_filename != info.filename or '\x00' in info.orig_filename or '\\' in info.filename:
                raise Fault('The archive contains an unsafe filename.')
            path = info.filename[:-1] if info.is_dir() else info.filename
            self.e.file_parts(path, True)
            if len(destination + '/' + path) > 512 or len(path.split('/')) > 32:
                raise Fault('An archive path exceeds the supported depth or length.')
            if path in declared:
                raise Fault('The archive contains duplicate paths.')
            declared.add(path)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind != 0 and (kind == stat.S_IFDIR) != info.is_dir()):
                raise Fault('Archive links, special files and inconsistent file types are refused.')
            if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise Fault('Only unencrypted stored or deflated ZIP entries are supported.')
            if info.is_dir() and info.file_size:
                raise Fault('Archive directory entries cannot contain file data.')
            size += info.file_size
            if size > MAX_FILE:
                raise Fault('The archive exceeds the 32 MB extraction limit.')
            existing = paths.get(path)
            if existing is not None and existing != info.is_dir():
                raise Fault('The archive uses a file as a parent folder.')
            paths[path] = info.is_dir()
            parts = path.split('/')
            for end in range(1, len(parts)):
                parent = '/'.join(parts[:end])
                if paths.get(parent) is False:
                    raise Fault('The archive uses a file as a parent folder.')
                paths[parent] = True
            if len(paths) > 1000:
                raise Fault('The archive exceeds the 1,000 file and folder limit.')
        return infos, paths, size

    @staticmethod
    def preflight(stream, length):
        # Bound central-directory parsing before ZipFile allocates ZipInfo objects.
        # ZIP64 and multi-disk containers are unnecessary for this bounded profile.
        stream.seek(max(0, length - 65557))
        tail = stream.read(65557)
        offset = tail.rfind(b'PK\x05\x06')
        if offset < 0 or len(tail) - offset < 22:
            raise Fault('The ZIP end record is missing.')
        signature, disk, start_disk, local_count, count, size, start, comment = struct.unpack('<4s4H2IH', tail[offset:offset+22])
        if offset+22+comment != len(tail) or disk or start_disk or count != local_count or not 1 <= count <= 1000 or size > 600000 or start+size > length:
            raise Fault('The ZIP metadata exceeds this profile’s limits or is inconsistent.')
        absolute = max(0, length - 65557) + offset
        if absolute >= 20:
            stream.seek(absolute - 20)
            if stream.read(4) == b'PK\x06\x07':
                raise Fault('ZIP64 containers are not supported by this bounded profile.')
        stream.seek(0)

    def normalize_directories(self, db, site, stage, paths):
        for path in sorted((p for p, is_dir in paths.items() if is_dir), key=lambda p: p.count('/'), reverse=True):
            folder, _, name = path.rpartition('/')
            with self.child(stage, folder) as parent:
                os.chmod(name, 0o755, dir_fd=parent, follow_symlinks=False)
                self.e.file_owner(db, site, parent, name, directory=True)

    def dispatch(self, db, actor, site, method, data):
        try:
            return self.operation(db, actor, site, method, data)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError):
            raise Fault('The ZIP is damaged, encrypted or unsupported. No extracted destination was published.')

    def operation(self, db, actor, site, method, data):
        root, hidden = self.e.site_root(site), data.get('show_hidden', False)
        source_folder, source_name = self.e.file_parts(data.get('path'), hidden)
        target_folder, target_name = self.e.file_parts(data.get('destination'), hidden)
        temporary = '.vectorcp-archive-' + secrets.token_hex(16)
        with self.e.directory(root, source_folder, hidden) as source, self.e.directory(root, target_folder, hidden) as destination, self.e.directory(root.parent) as private:
            for name in os.listdir(private):
                if re.fullmatch(r'\.vectorcp-archive-[0-9a-f]{32}', name):
                    if stat.S_ISDIR(os.stat(name, dir_fd=private, follow_symlinks=False).st_mode):
                        self.e.filetools.remove_tree(private, name)
                    else:
                        os.unlink(name, dir_fd=private)
            st = os.stat(source_name, dir_fd=source, follow_symlinks=False)
            if data.get('revision') != revision(st):
                raise Fault('The source changed. Refresh and try again.', 409)
            try:
                os.stat(target_name, dir_fd=destination, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Fault('The destination already exists. Choose another name.', 409)
            if method == 'files.archive.create':
                if not target_name.lower().endswith('.zip'):
                    raise Fault('Use a destination filename ending in .zip.')
                return self.create(db, actor, site, data, st, source, source_name, destination, target_name, private, temporary)
            if method != 'files.archive.extract':
                raise Fault('Unknown archive operation.', 404)
            with self.e.filetools.regular(source, source_name) as (stream, current):
                if revision(current) != data['revision']:
                    raise Fault('The source ZIP changed. Refresh and try again.', 409)
                self.preflight(stream, current.st_size)
                with zipfile.ZipFile(stream) as archive:
                    infos, paths, size = self.manifest(archive, data['destination'])
                    self.e.filetools.quota(db, site, size)
                    self.e.filetools.entry_room(root, len(paths) + 1)
                    os.mkdir(temporary, 0o700, dir_fd=private)
                    stage = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=private)
                    try:
                        for info in infos:
                            path = info.filename.rstrip('/')
                            if info.is_dir():
                                with self.child(stage, path, create=True):
                                    pass
                                continue
                            folder, _, name = path.rpartition('/')
                            with self.child(stage, folder, create=True) as parent:
                                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                                copied = 0
                                with os.fdopen(fd, 'wb') as output, archive.open(info) as input_stream:
                                    while True:
                                        block = input_stream.read(min(CHUNK, info.file_size - copied + 1))
                                        if not block:
                                            break
                                        copied += len(block)
                                        if copied > info.file_size:
                                            raise Fault('An archive entry exceeds its declared size.')
                                        output.write(block)
                                    if copied != info.file_size:
                                        raise Fault('An archive entry is incomplete.')
                                    output.flush()
                                    os.fsync(output.fileno())
                                os.chmod(name, 0o644, dir_fd=parent, follow_symlinks=False)
                                self.e.file_owner(db, site, parent, name)
                        if revision(os.fstat(stream.fileno())) != data['revision']:
                            raise Fault('The source ZIP changed during extraction.', 409)
                        self.normalize_directories(db, site, stage, paths)
                        os.fchmod(stage, 0o755)
                        self.e.file_owner(db, site, private, temporary, directory=True)
                        self.e.filetools.quota(db, site, size)
                        self.e.filetools.entry_room(root, len(paths) + 1)
                        os.fsync(stage)
                        rename_new(private, temporary, destination, target_name)
                        os.fsync(destination)
                    finally:
                        os.close(stage)
                        with contextlib.suppress(FileNotFoundError):
                            self.e.filetools.remove_tree(private, temporary)
            self.e.log(db, actor, 'archive.extracted', site['domain'] + '/' + data['destination'])
            return {'ok': True, 'bytes': size, 'entries': len(paths) + 1}

    def create(self, db, actor, site, data, st, source, source_name, destination, target_name, private, temporary):
        root = self.e.site_root(site)
        if stat.S_ISDIR(st.st_mode):
            snapshot = self.e.filetools.tree(root, data['path'])
            entries, _, initial = snapshot
            if initial != data['revision']:
                raise Fault('The source folder changed.', 409)
            members = [('', True, initial, 0)] + entries
        elif stat.S_ISREG(st.st_mode) and st.st_size <= MAX_FILE:
            entries, members = None, [('', False, data['revision'], st.st_size)]
        else:
            raise Fault('Archive creation supports regular files or folders with up to 32 MB of content.')
        if len(members) > 1000 or any(len((source_name + ('/' + path if path else '')).split('/')) > 32 for path, _, _, _ in members):
            raise Fault('The ZIP would exceed 1,000 entries or 32 path levels, including its source folder.')
        fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=private)
        try:
            with os.fdopen(fd, 'w+b') as output:
                with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
                    for path, directory, expected, size in members:
                        member = source_name + ('/' + path if path else '')
                        info = zipfile.ZipInfo(member + ('/' if directory else ''))
                        info.create_system = 3
                        info.external_attr = ((stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o644)) << 16
                        info.compress_type = zipfile.ZIP_STORED if directory else zipfile.ZIP_DEFLATED
                        if directory:
                            archive.writestr(info, b'')
                            continue
                        parent_path, _, name = path.rpartition('/')
                        folder = data['path'] + ('/' + parent_path if parent_path else '') if path else data['path'].rpartition('/')[0]
                        with self.e.directory(root, folder, True) as parent, self.e.filetools.regular(parent, name if path else source_name) as (input_stream, current):
                            if revision(current) != expected:
                                raise Fault('An archive source file changed.', 409)
                            copied = 0
                            with archive.open(info, 'w') as writer:
                                while True:
                                    block = input_stream.read(min(CHUNK, size - copied + 1))
                                    if not block:
                                        break
                                    copied += len(block)
                                    if copied > size:
                                        raise Fault('An archive source file changed.', 409)
                                    writer.write(block)
                                    if output.tell() > MAX_FILE:
                                        raise Fault('The ZIP output exceeds 32 MB.')
                            if copied != size or revision(os.fstat(input_stream.fileno())) != expected:
                                raise Fault('An archive source file changed.', 409)
                if entries is not None and self.e.filetools.tree(root, data['path']) != snapshot:
                    raise Fault('The source folder changed during archive creation.', 409)
                length = output.tell()
                if length > MAX_FILE:
                    raise Fault('The ZIP output exceeds 32 MB.')
                output.flush()
                os.fsync(output.fileno())
                output.seek(0)
                self.e.filetools.publish(db, site, destination, target_name, output, length)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=private)
        self.e.log(db, actor, 'archive.created', site['domain'] + '/' + data['destination'])
        return {'ok': True}
