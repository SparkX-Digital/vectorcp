import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from vectorcp.mail_profile import write
from vectorcp.mail_start_check import check


class MailProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_profile_failure_preserves_previous_configuration(self):
        path = self.root / 'service.conf'
        path.write_text('previous configuration')
        with patch('vectorcp.mail_profile.os.fchown'), patch('vectorcp.mail_profile.os.replace', side_effect=OSError('simulated replacement failure')):
            with self.assertRaises(OSError):
                write(path, 'new configuration', 0o600)
        self.assertEqual(path.read_text(), 'previous configuration')
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_key_payload_and_permissions_are_synced_before_replacement(self):
        path = self.root / 'key.pem'
        synced = []
        replace = os.replace
        fsync = os.fsync
        def record(fd):
            info = os.fstat(fd)
            synced.append((stat.S_ISREG(info.st_mode), info.st_mode & 0o777))
            return fsync(fd)
        def checked(source, target):
            self.assertIn((True, 0o600), synced)
            self.assertEqual(Path(source).read_bytes(), b'private synthetic key')
            return replace(source, target)
        previous = os.umask(0)
        try:
            with patch('vectorcp.mail_profile.os.fchown'), patch('vectorcp.mail_profile.os.fsync', side_effect=record), patch('vectorcp.mail_profile.os.replace', side_effect=checked):
                write(path, b'private synthetic key', 0o600)
        finally:
            os.umask(previous)
        self.assertTrue(any(not regular for regular, _ in synced))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def safe_stat(self, path):
        if path.name == 'lookup.sqlite3':
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0)
        return self.actual_lstat(path)

    def test_start_gate_requires_real_mounts_and_safe_root_owned_lookup(self):
        self.actual_lstat = Path.lstat
        with patch('vectorcp.mail_start_check.os.path.ismount', return_value=False):
            with self.assertRaises(RuntimeError):
                check(self.root, self.root / 'queue')
        with patch('vectorcp.mail_start_check.os.path.ismount', return_value=True), patch.object(Path, 'lstat', lambda path: self.safe_stat(path)):
            check(self.root, self.root / 'queue')
        for mode, uid in [(stat.S_IFREG | 0o666, 0), (stat.S_IFREG | 0o640, 1), (stat.S_IFLNK | 0o777, 0)]:
            def unsafe(path):
                if path.name == 'lookup.sqlite3':
                    return SimpleNamespace(st_mode=mode, st_uid=uid)
                return self.actual_lstat(path)
            with self.subTest(mode=mode, uid=uid), patch('vectorcp.mail_start_check.os.path.ismount', return_value=True), patch.object(Path, 'lstat', unsafe):
                with self.assertRaises(RuntimeError):
                    check(self.root, self.root / 'queue')

    def test_start_gate_rejects_existing_and_inaccessible_checkpoints(self):
        self.actual_lstat = Path.lstat
        pending = self.root / 'pending.json'
        pending.write_text('{}')
        with patch('vectorcp.mail_start_check.os.path.ismount', return_value=True):
            with self.assertRaises(RuntimeError):
                check(self.root, self.root / 'queue')
        pending.unlink()
        def inaccessible(path):
            if path == pending:
                raise PermissionError('simulated denied checkpoint lookup')
            return self.safe_stat(path)
        with patch('vectorcp.mail_start_check.os.path.ismount', return_value=True), patch.object(Path, 'lstat', inaccessible):
            with self.assertRaises(PermissionError):
                check(self.root, self.root / 'queue')
