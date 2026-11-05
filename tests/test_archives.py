import errno
import io
from pathlib import Path
import secrets
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from vectorcp.core import Engine, Fault
from vectorcp.filetools import MAX_FILE, revision


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='vectorcp-archives-')
        cls.root = Path(cls.tmp.name)
        cls.e = Engine(cls.root/'state', cls.root/'sites', development=True)
        password = secrets.token_urlsafe(24)
        cls.owner = cls.e.bootstrap({'setup_token': cls.e.setup_token(), 'username': 'owner', 'name': 'Owner', 'password': password})
        cls.e.dispatch({'method': 'accounts.create', 'token': cls.owner['token'], 'csrf': cls.owner['csrf'],
            'data': {'username': 'other', 'name': 'Other', 'password': password}})
        cls.other = cls.e.login({'username': 'other', 'password': password})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.site = self.call('sites.create', {'domain': secrets.token_hex(6)+'.example.com'})['id']
        self.public = self.root/'sites'/str(self.site)/'public'

    def call(self, method, data=None, who=None, csrf=None):
        who = who or self.owner
        data = dict(data or {})
        if method.startswith('files.'):
            data.setdefault('site_id', self.site)
        return self.e.dispatch({'method': method, 'data': data, 'token': who['token'], 'csrf': who['csrf'] if csrf is None else csrf})

    def denied(self, status, action):
        with self.assertRaises(Fault) as error:
            action()
        self.assertEqual(error.exception.status, status, str(error.exception))

    def operation(self, method, source, destination):
        folder, _, name = source.rpartition('/')
        entry = next(x for x in self.call('files.list', {'path': folder, 'show_hidden': True})['files'] if x['name']==name)
        return self.call(method, {'path': source, 'revision': entry['revision'], 'destination': destination, 'show_hidden': True})

    @staticmethod
    def archive(entries):
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in entries:
                    archive.writestr(name, content)
        return stream.getvalue()

    def test_folder_and_regular_file_round_trip_include_hidden_files(self):
        (self.public/'assets').mkdir()
        (self.public/'assets/sub').mkdir()
        (self.public/'assets/sub/data.bin').write_bytes(bytes(range(256))*100)
        (self.public/'assets/.settings').write_text('enabled=true')
        self.operation('files.archive.create', 'assets', 'assets.zip')
        with zipfile.ZipFile(self.public/'assets.zip') as archive:
            self.assertEqual(set(archive.namelist()), {'assets/', 'assets/.settings', 'assets/sub/', 'assets/sub/data.bin'})
        self.operation('files.archive.extract', 'assets.zip', 'unpacked')
        self.assertEqual((self.public/'unpacked/assets/sub/data.bin').read_bytes(), (self.public/'assets/sub/data.bin').read_bytes())
        self.assertEqual((self.public/'unpacked/assets/.settings').read_text(), 'enabled=true')
        self.operation('files.archive.create', 'index.html', 'page.zip')
        self.operation('files.archive.extract', 'page.zip', 'page')
        self.assertEqual((self.public/'page/index.html').read_bytes(), (self.public/'index.html').read_bytes())
        self.assertFalse(list(self.public.parent.glob('.vectorcp-archive-*')))

    def test_traversal_absolute_paths_backslashes_reserved_names_and_duplicates_are_refused(self):
        for entries in [[('../escape', b'bad')], [('/absolute', b'bad')], [('a\\b', b'bad')],
                        [('.vectorcp-private', b'bad')], [('file ', b'bad')], [('a/../b', b'bad')],
                        [('same', b'one'), ('same', b'two')], [('parent/file', b'x'), ('parent', b'not a folder')]]:
            with self.subTest(entries=entries):
                (self.public/'bad.zip').write_bytes(self.archive(entries))
                self.denied(400, lambda: self.operation('files.archive.extract', 'bad.zip', 'unsafe'))
                self.assertFalse((self.public/'unsafe').exists())
        self.assertFalse((self.root/'escape').exists())

    def test_links_devices_and_inconsistent_types_are_refused(self):
        for mode in (stat.S_IFLNK|0o777, stat.S_IFIFO|0o600, stat.S_IFCHR|0o600, stat.S_IFDIR|0o755):
            info = zipfile.ZipInfo('entry')
            info.create_system = 3
            info.external_attr = mode << 16
            (self.public/'unsafe.zip').write_bytes(self.archive([(info, b'/etc/passwd')]))
            self.denied(400, lambda: self.operation('files.archive.extract', 'unsafe.zip', 'unsafe'))
            self.assertFalse((self.public/'unsafe').exists())

    def test_extraction_limits_bound_content_and_metadata_before_parsing(self):
        (self.public/'large.zip').write_bytes(self.archive([('large.bin', b'x'*(MAX_FILE+1))]))
        self.denied(400, lambda: self.operation('files.archive.extract', 'large.zip', 'large'))
        (self.public/'many.zip').write_bytes(self.archive([('file-%d'%i, b'') for i in range(1001)]))
        with patch('vectorcp.archives.zipfile.ZipFile') as parser:
            self.denied(400, lambda: self.operation('files.archive.extract', 'many.zip', 'many'))
            parser.assert_not_called()
        # A forged small entry count cannot force unbounded central-directory reads.
        value = bytearray(self.archive([('file', b'value')]))
        offset = value.rfind(b'PK\x05\x06')
        struct.pack_into('<I', value, offset+12, 600001)
        (self.public/'metadata.zip').write_bytes(value)
        self.denied(400, lambda: self.operation('files.archive.extract', 'metadata.zip', 'metadata'))

    def test_nul_names_encryption_and_zip64_locator_are_refused(self):
        raw = self.archive([('nullXname', b'value')])
        (self.public/'nul.zip').write_bytes(raw.replace(b'nullXname', b'null\x00name'))
        self.denied(400, lambda: self.operation('files.archive.extract', 'nul.zip', 'nul'))
        value = bytearray(self.archive([('file', b'value')]))
        local, central = value.find(b'PK\x03\x04'), value.find(b'PK\x01\x02')
        struct.pack_into('<H', value, local+6, 1)
        struct.pack_into('<H', value, central+8, 1)
        (self.public/'encrypted.zip').write_bytes(value)
        self.denied(400, lambda: self.operation('files.archive.extract', 'encrypted.zip', 'encrypted'))
        # A maximum-length comment puts the locator just before the tail buffer.
        stream = io.BytesIO(self.archive([('file', b'value')]))
        with zipfile.ZipFile(stream, 'a') as archive:
            archive.comment = b'x'*65535
        value = stream.getvalue()
        end = value.rfind(b'PK\x05\x06')
        value = value[:end] + b'PK\x06\x07' + b'\x00'*16 + value[end:]
        (self.public/'zip64.zip').write_bytes(value)
        self.denied(400, lambda: self.operation('files.archive.extract', 'zip64.zip', 'zip64'))

    def test_crc_failure_and_full_storage_remove_partial_staging(self):
        value = bytearray(self.archive([('first.txt', b'first content'), ('second.txt', b'second content')]))
        header = value.find(b'PK\x01\x02')
        struct.pack_into('<I', value, header+16, 0)  # Wrong CRC, detected after a read.
        (self.public/'corrupt.zip').write_bytes(value)
        self.denied(400, lambda: self.operation('files.archive.extract', 'corrupt.zip', 'corrupt'))
        self.assertFalse((self.public/'corrupt').exists())
        self.assertFalse(list(self.public.parent.glob('.vectorcp-archive-*')))
        with patch('vectorcp.archives.os.fsync', side_effect=OSError(errno.ENOSPC, 'Full')):
            self.denied(409, lambda: self.operation('files.archive.create', 'index.html', 'full.zip'))
        self.assertFalse((self.public/'full.zip').exists())
        self.assertFalse(list(self.public.parent.glob('.vectorcp-archive-*')))

    def test_destination_conflicts_and_customer_scope_are_preserved(self):
        self.operation('files.archive.create', 'index.html', 'page.zip')
        original = (self.public/'page.zip').read_bytes()
        self.denied(409, lambda: self.operation('files.archive.create', 'index.html', 'page.zip'))
        self.assertEqual((self.public/'page.zip').read_bytes(), original)
        (self.public/'destination').mkdir()
        self.denied(409, lambda: self.operation('files.archive.extract', 'page.zip', 'destination'))
        for method in ('files.archive.create', 'files.archive.extract'):
            self.denied(404, lambda: self.call(method, {'path': 'page.zip'}, who=self.other))
            self.denied(403, lambda: self.call(method, {'path': 'page.zip'}, csrf='forged'))

    def test_link_sources_and_stale_revisions_are_refused(self):
        (self.public/'link').symlink_to(self.root/'state/control.sqlite3')
        self.denied(400, lambda: self.call('files.archive.create', {'path': 'link', 'revision': revision((self.public/'link').lstat()), 'destination': 'leak.zip'}))
        self.denied(409, lambda: self.call('files.archive.create', {'path': 'index.html', 'revision': 'forged', 'destination': 'stale.zip'}))
        (self.public/'folder').mkdir()
        (self.public/'folder/link').symlink_to(self.root/'state/control.sqlite3')
        self.denied(400, lambda: self.operation('files.archive.create', 'folder', 'unsafe.zip'))
        self.assertFalse((self.public/'unsafe.zip').exists())

    def test_extraction_quota_includes_existing_files_and_trash(self):
        (self.public/'data.zip').write_bytes(self.archive([('large.bin', b'x'*(1024*1024))]))
        with self.e.db() as db:
            db.execute('UPDATE users SET storage_mb=1 WHERE id=?', (self.owner['user']['id'],))
        try:
            self.denied(409, lambda: self.operation('files.archive.extract', 'data.zip', 'over'))
            self.assertFalse((self.public/'over').exists())
        finally:
            with self.e.db() as db:
                db.execute('UPDATE users SET storage_mb=1024 WHERE id=?', (self.owner['user']['id'],))

    def test_created_archive_obeys_the_same_depth_limit_as_extraction(self):
        folder = self.public/'deep'
        folder.mkdir()
        for _ in range(31):
            folder = folder/'sub'
            folder.mkdir()
        (folder/'file.txt').write_text('Deep fixture')
        self.denied(400, lambda: self.operation('files.archive.create', 'deep', 'deep.zip'))
        self.assertFalse((self.public/'deep.zip').exists())


if __name__ == '__main__':
    unittest.main()
