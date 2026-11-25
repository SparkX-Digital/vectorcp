import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_mail
from vectorcp.core import Fault
from vectorcp.mail_recovery import Recovery
from vectorcp.mail_recovery import main as recovery_main
from vectorcp.mail_start_check import check


class MailRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_mail.MailTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        f.install(); f.enable(); f.enable(f.other)
        self.ident = f.create()
        self.other = f.create(f.bob, f.other)
        self.address = 'hello@alice.example.test'
        self.r = Recovery(f.e.state, development=True)
        self.root = f.e.mail.store / self.ident / 'Maildir'
        self.root.mkdir(parents=True)
        self.add_message('', 'cur', '1700000000.message:2,Sa', b'Subject: retained\r\n\r\nPrivate fixture A\r\n')
        self.add_message('.Projects.Archive', 'new', '1700000001.other', b'Subject: nested\n\nPrivate fixture B\n')
        (self.root / 'dovecot-keywords').write_text('0 starred\n')
        (self.root / 'dovecot-uidlist').write_text('original UID state')
        (self.root / 'dovecot.index').write_text('original index')
        self.original = self.inventory()

    def add_message(self, folder, bucket, name, value):
        root = self.root / folder if folder else self.root
        for directory in ('cur', 'new', 'tmp'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        path = root / bucket / name
        path.write_bytes(value)
        os.utime(path, ns=(1700000000123456789, 1700000000123456789))
        return path

    def inventory(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def backup(self):
        return self.r.backup(self.address, apply=True)['id']

    def manifest(self, ident):
        return self.r.root / ident / 'manifest.json'

    def assert_clear(self):
        self.assertFalse(self.r.mail.pending.exists())
        self.assertFalse(self.r.maintenance.exists())

    def test_preflight_is_read_only_and_preserves_control_and_jobs(self):
        database = self.fixture.e.db_path.read_bytes()
        before = self.inventory()
        result = self.r.backup(self.address)
        self.assertTrue(result['check_only'])
        self.assertEqual(result['messages'], 2)
        self.assertEqual(database, self.fixture.e.db_path.read_bytes())
        self.assertEqual(before, self.inventory())
        self.assertFalse(self.r.root.exists())
        self.assert_clear()
        with closing(sqlite3.connect(self.fixture.e.db_path)) as db, db:
            db.execute("INSERT INTO jobs VALUES('recovery-test',?,NULL,'fixture','running','running',1,1)", (self.fixture.uid,))
        with self.assertRaisesRegex(Fault, 'hosting jobs'):
            self.r.backup(self.address)
        with closing(sqlite3.connect(self.fixture.e.db_path)) as db:
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id='recovery-test'").fetchone()[0], 'running')
        self.assert_clear()

    def test_snapshot_and_additive_restore_keep_newer_messages_flags_dates_and_keywords(self):
        before_db = self.fixture.e.db_path.read_bytes()
        ident = self.backup()
        snapshot = self.r.read_snapshot(ident)
        self.assertEqual(len(snapshot['messages']), 2)
        self.assertNotIn('password', json.dumps(snapshot))
        self.assertEqual(snapshot['virtual_bytes'], sum(i['virtual_bytes'] for i in snapshot['messages']))
        self.assertTrue(all(i['virtual_bytes'] >= i['bytes'] for i in snapshot['messages']))
        self.add_message('', 'new', 'newer-message', b'Subject: arrived later\r\n\r\nKeep this\r\n')
        before = self.inventory()
        preflight = self.r.restore(ident, self.address)
        self.assertTrue(preflight['check_only'])
        self.assertEqual(before, self.inventory())
        result = self.r.restore(ident, self.address, apply=True)
        prefix = '.Recovered-' + ident
        self.assertEqual(result['folder'], prefix[1:])
        for relative, expected in before.items():
            self.assertEqual(self.inventory()[relative], expected)
        for item in snapshot['messages']:
            p = self.root / (prefix + item['folder']) / item['bucket'] / item['name']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), item['sha256'])
            self.assertEqual(p.stat().st_mtime_ns, item['mtime_ns'])
        self.assertEqual((self.root / prefix / 'dovecot-keywords').read_text(), '0 starred\n')
        self.assertFalse((self.root / prefix / 'dovecot-uidlist').exists())
        self.assertFalse((self.root / prefix / 'dovecot.index').exists())
        self.assertEqual(before_db, self.fixture.e.db_path.read_bytes())
        self.assertEqual(self.r.root.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in (self.r.root / ident).rglob('*') if p.is_file()))
        self.assert_clear()

    def test_wrong_mailbox_and_account_identity_are_refused_before_maintenance(self):
        ident = self.backup()
        with self.assertRaisesRegex(Fault, 'different mailbox'):
            self.r.restore(ident, 'hello@bob.example.test', apply=True)
        path = self.manifest(ident); value = json.loads(path.read_text())
        value['user_id'] += 1; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(Fault, 'different mailbox'):
            self.r.restore(ident, self.address, apply=True)
        self.assertEqual(self.original, self.inventory())
        self.assert_clear()

    def test_corruption_traversal_duplicate_paths_and_keywords_are_refused(self):
        ident = self.backup(); path = self.manifest(ident); original = path.read_bytes()
        changes = [lambda d: d['messages'][0].update(folder='../other'),
                   lambda d: d['messages'][0].update(name='../escape'),
                   lambda d: d['messages'].append(d['messages'][0]),
                   lambda d: d['folders'].update({'': '0 okay\n0 duplicate\n'}),
                   lambda d: d.update(bytes=d['bytes'] + 1)]
        for change in changes:
            value = json.loads(original); change(value); path.write_text(json.dumps(value))
            with self.subTest(change=change), self.assertRaises(Fault):
                self.r.restore(ident, self.address, apply=True)
            self.assert_clear()
        path.write_bytes(original)
        blob = self.r.root / ident / 'messages/00000'; blob.write_bytes(b'changed')
        with self.assertRaisesRegex(Fault, 'verification failed'):
            self.r.restore(ident, self.address, apply=True)
        self.assertEqual(self.original, self.inventory())
        self.assert_clear()

    def test_snapshot_symlinks_hardlinks_and_unsafe_permissions_are_refused(self):
        ident = self.backup(); blob = self.r.root / ident / 'messages/00000'
        data = blob.read_bytes(); blob.unlink(); blob.symlink_to(self.root / 'cur/1700000000.message:2,Sa')
        with self.assertRaises((Fault, OSError)):
            self.r.restore(ident, self.address)
        blob.unlink(); blob.write_bytes(data); blob.chmod(0o600)
        alias = blob.with_name('hardlink'); os.link(blob, alias)
        with self.assertRaises(Fault):
            self.r.restore(ident, self.address)
        alias.unlink(); blob.chmod(0o644)
        with self.assertRaises(Fault):
            self.r.restore(ident, self.address)
        self.assert_clear()

    def test_source_links_special_files_and_bad_keyword_maps_fail_before_pause(self):
        p = self.root / 'new/link'; p.symlink_to(self.root / 'dovecot-uidlist')
        with self.assertRaises((Fault, OSError)):
            self.r.backup(self.address, apply=True)
        p.unlink(); os.mkfifo(p)
        with self.assertRaises(Fault):
            self.r.backup(self.address, apply=True)
        p.unlink(); (self.root / 'dovecot-keywords').write_text('26 unsupported\n')
        with self.assertRaises(Fault):
            self.r.backup(self.address, apply=True)
        self.assert_clear()

    def test_limits_quota_and_headroom_are_enforced_without_mutation(self):
        for constant, value in [('MAX_MESSAGES', 1), ('MAX_BYTES', 2), ('MAX_FOLDERS', 1)]:
            with self.subTest(constant=constant), patch('vectorcp.mail_recovery.' + constant, value), self.assertRaises(Fault):
                self.r.backup(self.address, apply=True)
            self.assert_clear()
        ident = self.backup()
        with patch.object(self.r, 'room', side_effect=Fault('no space')), self.assertRaises(Fault):
            self.r.restore(ident, self.address, apply=True)
        with patch.object(self.r, 'inventory', return_value=({}, [], 0, 17 * 1048576)), self.assertRaisesRegex(Fault, 'quota'):
            self.r.restore(ident, self.address, apply=True)
        with patch('vectorcp.mail_recovery.MAX_SNAPSHOTS', 1), self.assertRaisesRegex(Fault, '64-snapshot'):
            self.r.backup(self.address, apply=True)
        with patch('vectorcp.mail_recovery.MAX_SNAPSHOT_BYTES', 1), self.assertRaises(Fault):
            self.r.backup(self.address, apply=True)
        self.assertEqual(self.original, self.inventory())
        self.assert_clear()

    def test_restored_folder_path_limits_keep_future_snapshots_usable(self):
        self.add_message('.' + 'x' * 135, 'new', 'deep', b'bounded folder')
        ident = self.backup()
        with self.assertRaisesRegex(Fault, 'path limit'):
            self.r.restore(ident, self.address, apply=True)
        self.assert_clear()

    def test_duplicate_restore_preserves_existing_recovery_folder(self):
        ident = self.backup(); self.r.restore(ident, self.address, apply=True)
        before = self.inventory()
        with self.assertRaisesRegex(Fault, 'already exists'):
            self.r.restore(ident, self.address, apply=True)
        self.assertEqual(before, self.inventory())
        self.assert_clear()

    def test_interrupted_staging_is_retained_and_ordinary_publication_recovery_refuses(self):
        ident = self.backup(); prepare = self.r.prepare_folders
        def interrupted(*args):
            prepare(*args)
            raise OSError('simulated interrupted staging')
        with patch.object(self.r, 'prepare_folders', side_effect=interrupted), self.assertRaises(OSError):
            self.r.restore(ident, self.address, apply=True)
        self.assertTrue(self.r.mail.pending.exists())
        self.assertTrue(self.fixture.call(self.fixture.owner, 'mail.list')['message_recovery_required'])
        with self.assertRaises(Fault):
            self.fixture.call(self.fixture.owner, 'mail.recover', {'confirm': 'RECOVER MAIL'})
        before = self.r.mail.pending.read_bytes()
        self.assertTrue(self.r.recover()['check_only'])
        self.assertEqual(before, self.r.mail.pending.read_bytes())
        result = self.r.recover(apply=True)
        self.assertIn('withdrawn', result['result'])
        self.assertEqual(self.original, self.inventory())
        self.assertTrue(list(self.r.mail.store.glob('.vectorcp-recovery-*')))
        self.assert_clear()
        # A new attempt can use the same snapshot; retained staging is never reused.
        self.r.restore(ident, self.address, apply=True)
        self.assert_clear()

    def interrupt_publication(self, ident):
        rename = os.rename
        published = []
        def interrupt(source, target):
            if Path(source).parent.name.startswith('.vectorcp-recovery-') and Path(target).parent == self.root:
                if published:
                    raise OSError('simulated second-folder rename interruption')
                published.append(str(target))
            return rename(source, target)
        with patch('vectorcp.mail_recovery.os.rename', side_effect=interrupt), self.assertRaises(OSError):
            self.r.restore(ident, self.address, apply=True)
        self.assertEqual(len(published), 1)
        return Path(published[0])

    def test_mid_publication_recovery_withdraws_only_its_new_folders(self):
        ident = self.backup()
        self.add_message('', 'new', 'newer', b'Newer mail must remain')
        before = self.inventory()
        self.interrupt_publication(ident)
        with patch('vectorcp.mail_start_check.os.path.ismount', return_value=True), self.assertRaises(RuntimeError):
            check(self.r.mail.base, self.r.mail.base / 'queue')
        self.r.recover(apply=True)
        self.assertEqual(before, self.inventory())
        self.assert_clear()

    def test_reboot_lost_runtime_marker_can_be_recovered_from_durable_checkpoint(self):
        ident = self.backup(); self.interrupt_publication(ident)
        self.r.maintenance.unlink()
        self.assertTrue(self.r.recover()['check_only'])
        self.r.recover(apply=True)
        self.assertEqual(self.original, self.inventory())
        self.assert_clear()

    def test_changed_published_recovery_folder_is_retained_for_manual_inspection(self):
        ident = self.backup(); path = self.interrupt_publication(ident)
        (path / 'new/unexpected').write_bytes(b'Unexpected mail must not disappear')
        with self.assertRaisesRegex(Fault, 'unexpected messages'):
            self.r.recover(apply=True)
        self.assertTrue((path / 'new/unexpected').exists())
        self.assertTrue(self.r.mail.pending.exists())

    def test_committed_start_failure_recovery_does_not_undo_restored_messages(self):
        ident = self.backup()
        def service(action, units):
            if action == 'start' and units == ['dovecot', 'postfix']:
                raise Fault('simulated mail start failure')
        with patch.object(self.r, 'service', side_effect=service), self.assertRaises(Fault):
            self.r.restore(ident, self.address, apply=True)
        journal = json.loads(self.r.mail.pending.read_text())
        self.assertEqual(journal['phase'], 'committed')
        before = self.inventory()
        result = self.r.recover(apply=True)
        self.assertIn('committed', result['result'])
        self.assertEqual(before, self.inventory())
        self.assert_clear()

    def test_failure_before_staging_still_recovers_without_inventing_data(self):
        ident = self.backup()
        with patch.object(self.r, 'begin', side_effect=Fault('simulated early interruption')), self.assertRaises(Fault):
            self.r.restore(ident, self.address, apply=True)
        self.r.recover(apply=True)
        self.assertEqual(self.original, self.inventory())
        self.assert_clear()

    def test_unrelated_checkpoint_and_maintenance_are_never_cleared(self):
        self.r.mail.pending.write_text('{"installation_incomplete":true}\n')
        self.r.mail.pending.chmod(0o600)
        with self.assertRaises(Fault):
            self.r.recover(apply=True)
        self.assertTrue(self.r.mail.pending.exists())
        self.r.mail.pending.unlink()
        self.r.maintenance.write_text('another-maintenance\n')
        with self.assertRaises(Fault):
            self.r.backup(self.address, apply=True)
        self.assertEqual(self.r.maintenance.read_text(), 'another-maintenance\n')

    def test_cli_has_no_development_or_nonroot_bypass(self):
        with patch('vectorcp.mail_recovery.os.geteuid', return_value=1000), patch.object(sys, 'argv', ['mail_recovery', 'backup', '--mailbox', self.address]):
            with self.assertRaisesRegex(SystemExit, 'Run as root'):
                recovery_main()
        self.assertNotIn('--development', subprocess.check_output([sys.executable, '-m', 'vectorcp.mail_recovery', '--help'], text=True))
        self.assert_clear()


if __name__ == '__main__':
    unittest.main()
