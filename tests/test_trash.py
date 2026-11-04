import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault


class TrashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='vectorcp-trash-')
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
        self.assertEqual(error.exception.status, status)

    def trash(self, path):
        folder, _, name = path.rpartition('/')
        item = next(x for x in self.call('files.list', {'path': folder, 'show_hidden': True})['files'] if x['name']==name)
        return self.call('files.trash', {'path': path, 'revision': item['revision'], 'show_hidden': True})['id']

    def test_trash_keeps_private_durable_content_and_restore_refuses_collision(self):
        original = (self.public/'index.html').read_bytes()
        ident = self.trash('index.html')
        self.assertFalse((self.public/'index.html').exists())
        private = self.public.parent/'.vectorcp-trash'/ident
        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual((private/'payload').read_bytes(), original)
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.assertEqual(self.call('files.trash.list')['entries'][0]['id'], ident)
        (self.public/'index.html').write_text('new live page')
        self.denied(409, lambda: self.call('files.trash.restore', {'id': ident}))
        self.assertEqual((self.public/'index.html').read_text(), 'new live page')
        self.call('files.trash.restore', {'id': ident, 'destination': 'restored.html'})
        self.assertEqual((self.public/'restored.html').read_bytes(), original)
        self.assertEqual(self.call('files.trash.list')['entries'], [])

    def test_trash_usage_and_inode_accounting_cannot_bypass_quota(self):
        with self.e.db() as db:
            db.execute('UPDATE users SET storage_mb=1 WHERE id=?', (self.owner['user']['id'],))
        try:
            (self.public/'large.bin').write_bytes(b'x'*(1024*1024))
            ident = self.trash('large.bin')
            self.denied(409, lambda: self.call('files.write', {'path': 'over.txt', 'content': 'over', 'revision': 'new'}))
            self.call('files.trash.purge', {'id': ident})
            self.call('files.write', {'path': 'fits.txt', 'content': 'fits', 'revision': 'new'})
        finally:
            with self.e.db() as db:
                db.execute('UPDATE users SET storage_mb=1024 WHERE id=?', (self.owner['user']['id'],))

    def test_folder_trash_restore_and_permanent_purge_include_hidden_contents(self):
        self.call('files.mkdir', {'path': 'folder'})
        (self.public/'folder/.hidden').write_text('retained')
        ident = self.trash('folder')
        self.call('files.trash.restore', {'id': ident})
        self.assertEqual((self.public/'folder/.hidden').read_text(), 'retained')
        ident = self.trash('folder')
        self.call('files.trash.purge', {'id': ident})
        self.assertFalse((self.public.parent/'.vectorcp-trash'/ident).exists())
        self.denied(404, lambda: self.call('files.trash.restore', {'id': ident}))

    def test_site_scope_csrf_and_traversal_cover_all_trash_operations(self):
        ident = self.trash('index.html')
        for method in ('files.trash.list', 'files.trash.restore', 'files.trash.purge'):
            self.denied(404, lambda: self.call(method, {'id': ident}, who=self.other))
        for method in ('files.trash.restore', 'files.trash.purge'):
            self.denied(403, lambda: self.call(method, {'id': ident}, csrf='forged'))
            self.denied(404, lambda: self.call(method, {'id': '../../outside'}))
        self.denied(400, lambda: self.call('files.trash.restore', {'id': ident, 'destination': '../outside'}))
        self.assertEqual(len(self.call('files.trash.list')['entries']), 1)

    def test_failed_move_and_interrupted_receipts_preserve_live_files(self):
        with patch('vectorcp.trash.rename_new', side_effect=Fault('Destination changed', 409)):
            self.denied(409, lambda: self.trash('index.html'))
        self.assertTrue((self.public/'index.html').exists())
        trash = self.public.parent/'.vectorcp-trash'
        self.assertEqual(list(trash.iterdir()), [])
        interrupted = trash/secrets.token_hex(16)
        interrupted.mkdir(mode=0o700)
        (interrupted/'metadata.json').write_text(json.dumps({'path': 'index.html', 'created': 1}))
        self.assertEqual(self.call('files.trash.list')['entries'], [])
        self.assertTrue((self.public/'index.html').exists())
        self.assertFalse(interrupted.exists())

    def test_receipt_and_its_parent_directories_are_synced_before_removing_live_data(self):
        from vectorcp.filetools import rename_new
        events = []
        real_sync = os.fsync
        def sync(fd):
            events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            return real_sync(fd)
        def move(*args):
            # The new trash root and entry must be durable, as well as the
            # metadata receipt and its containing directory, before the move.
            self.assertEqual(events, ['directory', 'directory', 'file', 'directory'])
            return rename_new(*args)
        with patch('vectorcp.trash.os.fsync', side_effect=sync), patch('vectorcp.trash.rename_new', side_effect=move):
            ident = self.trash('index.html')
        self.assertEqual(self.call('files.trash.list')['entries'][0]['id'], ident)


if __name__ == '__main__':
    unittest.main()
