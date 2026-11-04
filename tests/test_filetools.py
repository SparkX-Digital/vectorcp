import base64
import errno
import hashlib
import os
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault
from vectorcp.filetools import CHUNK, MAX_FILE


class FileOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='vectorcp-files-')
        cls.root = Path(cls.tmp.name)
        cls.engine = Engine(cls.root / 'state', cls.root / 'sites', development=True)
        password = secrets.token_urlsafe(24)
        cls.admin = cls.engine.bootstrap({'setup_token': cls.engine.setup_token(),
            'username': 'administrator', 'name': 'Owner', 'password': password})
        for username in ('alice', 'bob'):
            cls.engine.dispatch({'method': 'accounts.create', 'token': cls.admin['token'],
                'csrf': cls.admin['csrf'], 'data': {'username': username,
                'name': username, 'password': password, 'storage_mb': 10, 'site_limit': 100}})
            setattr(cls, username, cls.engine.login({'username': username, 'password': password}))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.site = self.call('sites.create', {'domain': secrets.token_hex(6) + '.example.com'})['id']
        self.public = self.root / 'sites' / str(self.site) / 'public'

    def tearDown(self):
        with self.engine.db() as db:
            for row in db.execute('SELECT id FROM file_uploads').fetchall():
                self.engine.filetools.discard(db, row['id'])
        # Keep other tests independent of data and quota used here.
        import shutil
        for item in self.public.iterdir():
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()

    def call(self, method, data=None, session=None, **overrides):
        session = session or self.alice
        request = {'method': method, 'data': dict(data or {}),
                   'token': session['token'], 'csrf': session['csrf']}
        if method.startswith('files.'):
            request['data'].setdefault('site_id', self.site)
        request.update(overrides)
        return self.engine.dispatch(request)

    def refused(self, status, method, data, **kw):
        with self.assertRaises(Fault) as caught:
            self.call(method, data, **kw)
        self.assertEqual(caught.exception.status, status, str(caught.exception))

    def start(self, content, path='upload.bin', **kw):
        return self.call('files.upload.start', {'path': path, 'bytes': len(content),
            'sha256': hashlib.sha256(content).hexdigest()}, **kw)['id']

    def test_hidden_preference_applies_to_list_editor_transfer_search_and_actions(self):
        self.call('files.mkdir', {'path': '.config', 'show_hidden': True})
        self.call('files.write', {'path': '.config/.settings', 'content': 'private settings', 'revision': 'new', 'show_hidden': True})
        self.assertNotIn('.config', [x['name'] for x in self.call('files.list')['files']])
        self.assertIn('.config', [x['name'] for x in self.call('files.list', {'show_hidden': True})['files']])
        self.refused(400, 'files.read', {'path': '.config/.settings'})
        self.assertEqual(self.call('files.read', {'path': '.config/.settings', 'show_hidden': True})['content'], 'private settings')
        self.assertEqual(self.call('files.search', {'query': 'settings'})['files'], [])
        matches = self.call('files.search', {'query': 'settings', 'show_hidden': True})['files']
        self.assertEqual(matches[0]['path'], '.config/.settings')
        before = self.call('files.describe', {'path': '.config/.settings', 'show_hidden': True})
        self.call('files.copy', {'path': '.config/.settings', 'revision': before['revision'], 'destination': '.copy', 'show_hidden': True})
        self.assertEqual((self.public/'.copy').read_text(), 'private settings')
        for path in ('.', '..', '.config/../index.html', '.vectorcp-reserved', ' name.txt', 'index.html ', 'folder /file.txt'):
            self.refused(400, 'files.read', {'path': path, 'show_hidden': True})

    def test_external_whitespace_names_cannot_alias_a_normal_file(self):
        (self.public/'index.html ').write_text('keep separate')
        before = (self.public/'index.html').read_bytes()
        listed = self.call('files.list')['files']
        self.assertNotIn('index.html ', [x['name'] for x in listed])
        self.refused(400, 'files.remove', {'path': 'index.html ', 'revision': next(x['revision'] for x in listed if x['name']=='index.html')})
        self.assertEqual((self.public/'index.html').read_bytes(), before)
        self.assertEqual((self.public/'index.html ').read_text(), 'keep separate')

    def test_permission_changes_use_revision_and_refuse_links_special_bits_and_other_accounts(self):
        info = self.call('files.permissions', {'path': 'index.html'})
        self.assertEqual(info['owner'], 'alice')
        self.assertEqual(self.call('files.chmod', {'path': 'index.html', 'mode': '600', 'revision': info['revision']})['mode'], '600')
        self.assertEqual((self.public/'index.html').stat().st_mode & 0o7777, 0o600)
        current = self.call('files.read', {'path': 'index.html'})
        self.call('files.write', {'path': 'index.html', 'content': 'Permission stays private after saving', 'revision': current['revision']})
        self.assertEqual((self.public/'index.html').stat().st_mode & 0o7777, 0o600)
        self.refused(409, 'files.chmod', {'path': 'index.html', 'mode': '644', 'revision': info['revision']})
        for mode in ('777', '666', '4755', '0644', 644):
            self.refused(400, 'files.chmod', {'path': 'index.html', 'mode': mode, 'revision': info['revision']})
        (self.public/'link').symlink_to(self.root/'state/control.sqlite3')
        self.refused(409, 'files.permissions', {'path': 'link'})
        self.refused(404, 'files.permissions', {'path': 'index.html'}, session=self.bob)
        self.refused(403, 'files.chmod', {'path': 'index.html'}, csrf='invalid')

    def test_new_text_file_preserves_a_destination_created_while_saving(self):
        destination = self.public/'arriving.txt'
        original = os.fsync
        def race(fd):
            if not destination.exists():
                destination.write_text('Created by the website during save')
            return original(fd)
        with patch('vectorcp.core.os.fsync', side_effect=race):
            self.refused(409, 'files.write', {'path': 'arriving.txt', 'content': 'Editor content', 'revision': 'new'})
        self.assertEqual(destination.read_text(), 'Created by the website during save')
        self.assertFalse(list(self.public.glob('.vectorcp-*')))

    def test_recursive_copy_preserves_hidden_content_and_refuses_escapes_or_replacement(self):
        self.call('files.mkdir', {'path': 'assets'})
        (self.public/'assets/sub').mkdir()
        (self.public/'assets/sub/data.bin').write_bytes(bytes(range(256))*100)
        (self.public/'assets/.settings').write_text('hidden but included')
        entry = next(x for x in self.call('files.list')['files'] if x['name']=='assets')
        data = {'path': 'assets', 'destination': 'copied', 'revision': entry['revision']}
        self.call('files.copy', data)
        self.assertEqual((self.public/'copied/sub/data.bin').read_bytes(), (self.public/'assets/sub/data.bin').read_bytes())
        self.assertEqual((self.public/'copied/.settings').read_text(), 'hidden but included')
        self.refused(409, 'files.copy', data)
        self.refused(400, 'files.copy', dict(data, destination='assets/inside'))
        (self.public/'assets/link').symlink_to(self.root/'state/control.sqlite3')
        entry = next(x for x in self.call('files.list')['files'] if x['name']=='assets')
        self.refused(400, 'files.copy', dict(data, destination='unsafe', revision=entry['revision']))
        self.assertFalse((self.public/'unsafe').exists())
        self.assertFalse(list(self.public.parent.glob('.vectorcp-*')))

    def test_folder_copy_failure_cleans_stage_and_never_publishes_partial_contents(self):
        self.call('files.mkdir', {'path': 'source'})
        (self.public/'source/one.txt').write_text('one')
        (self.public/'source/two.txt').write_text('two')
        item = next(x for x in self.call('files.list')['files'] if x['name']=='source')
        data = {'path': 'source', 'destination': 'destination', 'revision': item['revision']}
        original = self.engine.filetools.publish
        calls = []
        def failure(*args, **kwargs):
            calls.append(True)
            if len(calls)==2:
                raise OSError(errno.ENOSPC, 'Storage full')
            return original(*args, **kwargs)
        with patch.object(self.engine.filetools, 'publish', side_effect=failure):
            self.refused(409, 'files.copy', data)
        self.assertFalse((self.public/'destination').exists())
        self.assertFalse(list(self.public.parent.glob('.vectorcp-*')))
        self.assertEqual((self.public/'source/two.txt').read_text(), 'two')

    def test_batch_reports_individual_conflicts_without_losing_completed_items(self):
        self.call('files.mkdir', {'path': 'destination'})
        (self.public/'one.txt').write_text('one')
        (self.public/'two.txt').write_text('two')
        (self.public/'destination/two.txt').write_text('keep existing')
        entries = {x['name']: x for x in self.call('files.list')['files']}
        items = [{'path': name, 'revision': entries[name]['revision']} for name in ('one.txt','two.txt')]
        result = self.call('files.batch', {'items': items, 'operation': 'copy', 'destination': 'destination'})
        self.assertFalse(result['ok'])
        self.assertEqual([r['ok'] for r in result['results']], [True, False])
        self.assertEqual((self.public/'destination/one.txt').read_text(), 'one')
        self.assertEqual((self.public/'destination/two.txt').read_text(), 'keep existing')
        self.refused(400, 'files.batch', {'items': [items[0], items[0]], 'operation': 'copy', 'destination': 'destination'})
        self.refused(403, 'files.batch', {'items': items, 'operation': 'copy', 'destination': 'destination'}, csrf='wrong')

    def chunk(self, ident, content, offset=0):
        return self.call('files.upload.chunk', {'id': ident, 'offset': offset,
            'base64': base64.b64encode(content).decode()})

    def item(self, name):
        return next(f for f in self.call('files.list')['files'] if f['name'] == name)

    def test_binary_upload_is_private_until_verified_and_download_matches(self):
        content = bytes(range(256)) * 2100
        ident = self.start(content)
        self.assertFalse((self.public / 'upload.bin').exists())
        for offset in range(0, len(content), CHUNK):
            self.chunk(ident, content[offset:offset + CHUNK], offset)
        self.call('files.upload.finish', {'id': ident})
        self.assertTrue(self.call('files.upload.status', {'id': ident})['completed'])
        self.assertTrue(self.call('files.upload.finish', {'id': ident})['ok'])
        self.assertEqual((self.public / 'upload.bin').read_bytes(), content)
        info = self.call('files.describe', {'path': 'upload.bin'})
        parts = []
        offset = 0
        while offset < info['bytes']:
            part = self.call('files.chunk', {'path': 'upload.bin',
                'revision': info['revision'], 'offset': offset})
            parts.append(base64.b64decode(part['base64']))
            offset = part['next']
        self.assertEqual(b''.join(parts), content)
        self.assertEqual(info['sha256'], hashlib.sha256(content).hexdigest())
        self.assertFalse(list(self.engine.filetools.staging.iterdir()))

    def test_retry_recovery_and_agent_restart_keep_upload_offset(self):
        content = b'firstsecond'
        ident = self.start(content)
        self.chunk(ident, b'first')
        self.assertEqual(self.chunk(ident, b'first')['received'], 5)
        self.refused(409, 'files.upload.chunk', {'id': ident, 'offset': 0, 'base64': 'ZmFsc2U='})
        # A crash after write/fsync but before SQLite commit leaves extra bytes.
        with (self.engine.filetools.staging / ident).open('ab') as stream:
            stream.write(b'uncommitted')
        restarted = Engine(self.root / 'state', self.root / 'sites', development=True)
        result = restarted.dispatch({'method': 'files.upload.status',
            'data': {'site_id': self.site, 'id': ident}, 'token': self.alice['token']})
        self.assertEqual(result['received'], 5)
        self.chunk(ident, b'second', 5)
        self.call('files.upload.finish', {'id': ident})
        self.assertEqual((self.public / 'upload.bin').read_bytes(), content)

    def test_checksum_incomplete_and_destination_conflict_never_publish(self):
        ident = self.start(b'good')
        self.refused(409, 'files.upload.finish', {'id': ident})
        self.chunk(ident, b'evil')
        self.refused(409, 'files.upload.finish', {'id': ident})
        self.assertFalse((self.public / 'upload.bin').exists())
        self.call('files.upload.cancel', {'id': ident})
        ident = self.start(b'good')
        self.chunk(ident, b'good')
        (self.public / 'upload.bin').write_bytes(b'website process created this')
        self.refused(409, 'files.upload.finish', {'id': ident})
        self.assertEqual((self.public / 'upload.bin').read_bytes(), b'website process created this')
        self.assertFalse(list(self.public.glob('.vectorcp-*')))

    def test_upload_authentication_csrf_and_actor_ownership(self):
        ident = self.start(b'private')
        self.refused(404, 'files.upload.status', {'id': ident}, session=self.bob)
        self.refused(404, 'files.upload.status', {'id': ident}, session=self.admin)
        for method in ('files.upload.chunk', 'files.upload.finish', 'files.upload.cancel'):
            self.refused(403, method, {'id': ident}, csrf='forged')
        self.refused(400, 'files.upload.chunk', {'id': ident, 'offset': 0, 'base64': '!invalid'})
        self.refused(409, 'files.upload.chunk', {'id': ident, 'offset': 1, 'base64': 'YQ=='})
        self.call('files.upload.cancel', {'id': ident})
        self.refused(404, 'files.upload.status', {'id': ident})

    def test_staging_limits_quota_reservation_and_expiry(self):
        self.refused(400, 'files.upload.start', {'path': 'too-big', 'bytes': MAX_FILE + 1, 'sha256': '0' * 64})
        ident = self.start(b'x' * (6 * 1024 * 1024))
        self.refused(409, 'files.upload.start', {'path': 'more', 'bytes': 6 * 1024 * 1024, 'sha256': '0' * 64})
        with self.engine.db() as db:
            db.execute('UPDATE file_uploads SET created=? WHERE id=?', (int(time.time()) - 3601, ident))
        another = self.start(b'ok', 'fresh.bin')
        self.assertFalse((self.engine.filetools.staging / ident).exists())
        self.assertTrue((self.engine.filetools.staging / another).exists())

    def test_finish_rechecks_quota_and_disk_failure_leaves_no_visible_file(self):
        ident = self.start(b'good')
        self.chunk(ident, b'good')
        with patch.object(self.engine.filetools, 'quota', side_effect=Fault('Full', 409)):
            self.refused(409, 'files.upload.finish', {'id': ident})
        with patch('vectorcp.filetools.rename_new', side_effect=OSError(errno.ENOSPC, 'full')):
            self.refused(409, 'files.upload.finish', {'id': ident})
        self.assertFalse((self.public / 'upload.bin').exists())
        self.assertFalse(list(self.public.glob('.vectorcp-*')))

    def test_copy_move_rename_and_empty_folder_removal(self):
        original = self.call('files.describe', {'path': 'index.html'})
        self.call('files.copy', {'path': 'index.html', 'destination': 'copy.html', 'revision': original['revision']})
        self.assertEqual((self.public / 'copy.html').read_bytes(), (self.public / 'index.html').read_bytes())
        self.call('files.mkdir', {'path': 'assets'})
        self.call('files.move', {'path': 'copy.html', 'destination': 'assets/moved.html', 'revision': self.item('copy.html')['revision']})
        self.assertFalse((self.public / 'copy.html').exists())
        self.call('files.move', {'path': 'assets', 'destination': 'renamed', 'revision': self.item('assets')['revision']})
        self.refused(409, 'files.remove', {'path': 'renamed', 'revision': self.item('renamed')['revision']})
        info = self.call('files.describe', {'path': 'renamed/moved.html'})
        self.call('files.remove', {'path': 'renamed/moved.html', 'revision': info['revision']})
        self.call('files.remove', {'path': 'renamed', 'revision': self.item('renamed')['revision']})
        self.assertTrue((self.public / 'index.html').exists())

    def test_conflicts_stale_revisions_and_missing_csrf_preserve_files(self):
        original = self.call('files.describe', {'path': 'index.html'})
        for method in ('files.copy', 'files.move'):
            self.refused(409 if method == 'files.copy' else 400, method,
                {'path': 'index.html', 'destination': 'index.html', 'revision': original['revision']})
            self.refused(403, method, {'path': 'index.html', 'destination': 'new.html', 'revision': original['revision']}, csrf='')
        (self.public / 'index.html').write_text('newer')
        for method in ('files.chunk', 'files.copy', 'files.move', 'files.remove'):
            self.refused(409, method, {'path': 'index.html', 'destination': 'other.html', 'revision': original['revision'], 'offset': 0})
        self.assertEqual((self.public / 'index.html').read_text(), 'newer')

    def test_paths_symlinks_special_files_and_cross_customer_access(self):
        (self.public / 'escape').symlink_to(self.root, target_is_directory=True)
        (self.public / 'link.txt').symlink_to(self.root / 'state/control.sqlite3')
        info = self.call('files.describe', {'path': 'index.html'})
        for target in ('../outside', '/etc/outside', '.secret', 'escape/control.sqlite3'):
            for method in ('files.copy', 'files.move'):
                with self.assertRaises(Fault):
                    self.call(method, {'path': 'index.html', 'destination': target, 'revision': info['revision']})
        for method in ('files.describe', 'files.chunk', 'files.copy', 'files.move', 'files.remove'):
            with self.assertRaises(Fault):
                self.call(method, {'path': 'link.txt', 'destination': 'new', 'revision': info['revision'], 'offset': 0})
            self.refused(404, method, {'path': 'index.html'}, session=self.bob)
        os.mkfifo(self.public / 'pipe')
        self.refused(400, 'files.describe', {'path': 'pipe'})
        self.assertTrue((self.root / 'state/control.sqlite3').exists())

    def test_search_is_scoped_bounded_and_does_not_follow_links(self):
        (self.public / 'assets').mkdir()
        (self.public / 'assets/Match.txt').write_text('found')
        (self.public / '.match').write_text('hidden')
        (self.public / 'match-link').symlink_to(self.root, target_is_directory=True)
        result = self.call('files.search', {'query': 'match'})
        self.assertEqual([f['path'] for f in result['files']], ['assets/Match.txt'])
        for i in range(205):
            (self.public / ('match-%03d' % i)).touch()
        result = self.call('files.search', {'query': 'match'})
        self.assertEqual(len(result['files']), 200)
        self.assertTrue(result['limited'])
        self.refused(404, 'files.search', {'query': 'match'}, session=self.bob)

    def test_empty_file_upload_and_entry_limit_are_supported(self):
        ident = self.start(b'')
        self.call('files.upload.finish', {'id': ident})
        info = self.call('files.describe', {'path': 'upload.bin'})
        self.assertEqual(info['bytes'], 0)
        self.assertEqual(self.call('files.chunk', {'path': 'upload.bin', 'revision': info['revision'], 'offset': 0})['base64'], '')
        with patch.object(self.engine, 'check_entry_limit', side_effect=Fault('Entries full', 409)):
            self.refused(409, 'files.copy', {'path': 'upload.bin', 'revision': info['revision'], 'destination': 'second'})
            self.refused(409, 'files.upload.start', {'path': 'new', 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()})
