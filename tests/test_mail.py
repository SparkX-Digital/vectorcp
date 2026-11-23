import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault


class MailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.e = Engine(self.root / 'state', self.root / 'sites', development=True)
        self.secret = 'a-private-testing-password'
        self.owner = self.e.bootstrap({'username': 'owner', 'name': 'Owner', 'password': self.secret, 'setup_token': self.e.setup_token()})
        self.uid = self.call(self.owner, 'accounts.create', {'username': 'alice', 'name': 'Alice', 'password': self.secret})['id']
        self.other_uid = self.call(self.owner, 'accounts.create', {'username': 'bob', 'name': 'Bob', 'password': self.secret})['id']
        self.alice = self.e.login({'username': 'alice', 'password': self.secret})
        self.bob = self.e.login({'username': 'bob', 'password': self.secret})
        self.site = self.call(self.alice, 'sites.create', {'domain': 'alice.example.test'})['id']
        self.other = self.call(self.bob, 'sites.create', {'domain': 'bob.example.test'})['id']
        with self.e.db() as db:
            db.execute('UPDATE users SET hosting_slot=1,storage_mb=512 WHERE id=?', (self.uid,))
            db.execute('UPDATE users SET hosting_slot=2,storage_mb=512 WHERE id=?', (self.other_uid,))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, who, method, data=None, **extra):
        return self.e.dispatch(dict({'method': method, 'data': data or {}, 'token': who['token'], 'csrf': who['csrf']}, **extra))

    def install(self):
        self.e.mail.config.mkdir()
        (self.e.mail.config / 'installed.json').write_text(json.dumps({'version': 1, 'hostname': 'mail.example.test', 'storage_mb': 512, 'control_db': str(self.e.db_path)}))
        with self.e.db() as db:
            self.e.mail.checkpoint()
            self.e.mail.complete(self.e.mail.snapshot(db))

    def enable(self, site=None):
        domain = 'bob.example.test' if site == self.other else 'alice.example.test'
        return self.call(self.owner, 'mail.domain', {'site_id': site or self.site, 'enabled': True, 'confirm_domain': domain})

    def create(self, who=None, site=None, local='hello', quota=16):
        self.call(who or self.alice, 'mail.create', {'site_id': site or self.site, 'local': local, 'quota_mb': quota, 'password': self.secret})
        boxes = self.call(who or self.alice, 'mail.list')['domains'][0]['mailboxes']
        return next(b['id'] for b in boxes if b['local'] == local)

    def projection(self):
        with sqlite3.connect(self.e.mail.projection) as db:
            return db.execute('SELECT address,password,home,quota_mb,active FROM boxes ORDER BY address').fetchall()

    def test_optional_profile_and_explicit_owner_activation(self):
        self.assertFalse(self.call(self.alice, 'mail.list')['installed'])
        with self.assertRaises(Fault):
            self.create()
        self.install()
        with self.assertRaises(Fault):
            self.create()
        with self.assertRaises(Fault) as caught:
            self.call(self.alice, 'mail.domain', {'site_id': self.site, 'enabled': True, 'confirm_domain': 'alice.example.test'})
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(Fault):
            self.call(self.owner, 'mail.domain', {'site_id': self.site, 'enabled': True, 'confirm_domain': 'wrong.example.test'})
        self.enable()
        self.create()
        self.assertTrue(self.projection()[0][4])

    def test_cross_customer_ids_and_listings_are_scoped(self):
        self.install(); self.enable(); self.enable(self.other)
        ident = self.create(self.bob, self.other)
        self.assertEqual([d['domain'] for d in self.call(self.alice, 'mail.list')['domains']], ['alice.example.test'])
        for method, data in [('mail.create', {'site_id': self.other, 'local': 'new', 'quota_mb': 1, 'password': self.secret}),
                             ('mail.active', {'id': ident, 'active': False}), ('mail.password', {'id': ident, 'password': self.secret}),
                             ('mail.quota', {'id': ident, 'quota_mb': 1})]:
            with self.subTest(method=method), self.assertRaises(Fault) as caught:
                self.call(self.alice, method, data)
            self.assertEqual(caught.exception.status, 404)

    def test_password_never_returned_audited_or_stored_plaintext(self):
        self.install(); self.enable(); ident = self.create()
        changed = 'a-new-private-mail-password'
        self.call(self.alice, 'mail.password', {'id': ident, 'password': changed})
        public = json.dumps(self.call(self.owner, 'mail.list')) + json.dumps(self.call(self.owner, 'audit'))
        for value in (self.secret, changed, self.projection()[0][1]):
            self.assertNotIn(value, public)
        self.assertNotIn(changed.encode(), self.e.mail.projection.read_bytes())
        self.assertNotIn(changed.encode(), self.e.db_path.read_bytes())

    def test_input_injection_duplicates_and_no_catchall(self):
        self.install(); self.enable(); self.create()
        for local in ('hello', '../bad', 'bad..name', '@', '*', 'a+b', 'UPPER', 'a\nquery', 'a' * 65, 'hello@example.test'):
            with self.subTest(local=local), self.assertRaises(Fault):
                self.create(local=local)
        for password in ('short', 'x' * 129, 'sixteen-chars\nmore'):
            with self.assertRaises(Fault):
                self.call(self.alice, 'mail.create', {'site_id': self.site, 'local': 'valid', 'quota_mb': 16, 'password': password})

    def test_reservations_count_suspended_mailboxes(self):
        self.install(); self.enable(); ident = self.create(quota=300)
        self.call(self.alice, 'mail.active', {'id': ident, 'active': False})
        with self.assertRaises(Fault):
            self.create(local='second', quota=110)  # 80% of 512 = 409
        self.call(self.alice, 'mail.quota', {'id': ident, 'quota_mb': 10})
        self.create(local='second', quota=300)
        self.assertEqual(self.projection()[0][3], 10)

    def test_account_site_and_mailbox_suspensions_revoke_projection(self):
        self.install(); self.enable(); ident = self.create()
        self.call(self.alice, 'mail.active', {'id': ident, 'active': False})
        self.assertEqual(self.projection()[0][4], 0)
        self.call(self.alice, 'mail.active', {'id': ident, 'active': True})
        self.call(self.owner, 'accounts.active', {'id': self.uid, 'active': False})
        self.assertEqual(self.projection()[0][4], 0)
        self.call(self.owner, 'accounts.active', {'id': self.uid, 'active': True})
        self.call(self.owner, 'sites.active', {'site_id': self.site, 'active': False})
        self.assertEqual(self.projection()[0][4], 0)
        self.call(self.owner, 'sites.active', {'site_id': self.site, 'active': True})
        self.assertEqual(self.projection()[0][4], 1)

    def test_csrf_required_and_read_does_not_publish(self):
        self.install(); self.enable(); ident = self.create()
        for method in ('mail.active', 'mail.password', 'mail.quota', 'mail.domain', 'mail.create', 'mail.recover'):
            with self.subTest(method=method), self.assertRaises(Fault) as caught:
                self.call(self.owner, method, {}, csrf='forged')
            self.assertEqual(caught.exception.status, 403)
        with patch.object(self.e.mail, 'stop') as stop:
            self.call(self.alice, 'mail.list')
            self.call(self.owner, 'audit')
            stop.assert_not_called()

    def test_stop_failure_does_not_commit_and_requires_explicit_recovery(self):
        self.install(); self.enable(); ident = self.create()
        with patch.object(self.e.mail, 'stop', side_effect=Fault('simulated stop failure', 503)):
            with self.assertRaises(Fault):
                self.call(self.alice, 'mail.active', {'id': ident, 'active': False})
        self.assertTrue(self.e.mail.pending.exists())
        with self.e.db() as db:
            self.assertEqual(db.execute('SELECT active FROM mailboxes WHERE id=?', (ident,)).fetchone()[0], 1)
        with self.assertRaises(Fault):
            self.call(self.alice, 'mail.recover', {'confirm': 'RECOVER MAIL'})
        self.call(self.owner, 'mail.recover', {'confirm': 'RECOVER MAIL'})
        self.assertFalse(self.e.mail.pending.exists())
        self.assertTrue(self.projection()[0][4])

    def test_publication_failure_retains_committed_change_stopped_for_recovery(self):
        self.install(); self.enable(); ident = self.create()
        original = self.e.mail.complete
        with patch.object(self.e.mail, 'complete', side_effect=Fault('simulated publication failure', 503)):
            with self.assertRaises(Fault):
                self.call(self.alice, 'mail.active', {'id': ident, 'active': False})
        with self.e.db() as db:
            self.assertEqual(db.execute('SELECT active FROM mailboxes WHERE id=?', (ident,)).fetchone()[0], 0)
        # Recreate the engine to simulate a process restart. Never auto-resume.
        self.e = Engine(self.root / 'state', self.root / 'sites', development=True)
        self.assertTrue(self.call(self.owner, 'mail.list')['recovery_required'])
        self.call(self.owner, 'mail.recover', {'confirm': 'RECOVER MAIL'})
        self.assertFalse(self.projection()[0][4])

    def test_profile_cannot_publish_another_control_database(self):
        self.install()
        p = self.e.mail.config / 'installed.json'
        data = json.loads(p.read_text()); data['control_db'] = '/some/other/control.sqlite3'
        p.write_text(json.dumps(data))
        self.assertFalse(self.call(self.owner, 'mail.list')['installed'])

    def test_domain_disable_preserves_passwords_and_messages(self):
        self.install(); self.enable(); self.create()
        original = self.projection()[0]
        home = Path(original[2]); home.mkdir(parents=True); (home / 'retained').write_text('private mail')
        self.call(self.owner, 'mail.domain', {'site_id': self.site, 'enabled': False, 'confirm_domain': 'alice.example.test'})
        self.assertEqual(self.projection()[0][:4], original[:4])
        self.assertEqual((home / 'retained').read_text(), 'private mail')
        self.assertFalse(self.projection()[0][4])

    def test_missing_or_damaged_projection_pauses_ui_and_requires_recovery(self):
        self.install(); self.enable(); self.create()
        self.e.mail.projection.write_bytes(b'corrupt lookup')
        status = self.call(self.owner, 'mail.list')
        self.assertTrue(status['recovery_required'])
        self.assertFalse(status['domains'][0]['mailboxes'][0]['effective'])
        with self.assertRaises(Fault):
            self.create(local='blocked')
        self.call(self.owner, 'mail.recover', {'confirm': 'RECOVER MAIL'})
        self.assertTrue(self.call(self.owner, 'mail.list')['domains'][0]['effective'])

    def test_customer_cannot_start_mail_services_stopped_by_owner(self):
        self.install(); self.enable(); ident = self.create()
        with patch.object(self.e.mail, 'services', return_value={'postfix': 'inactive', 'dovecot': 'inactive'}), patch.object(self.e.mail, 'stop') as stop:
            self.assertTrue(self.call(self.alice, 'mail.list')['recovery_required'])
            with self.assertRaises(Fault):
                self.call(self.alice, 'mail.quota', {'id': ident, 'quota_mb': 20})
            stop.assert_not_called()

    def test_projection_is_private_before_any_hashes_are_written(self):
        self.install(); self.enable()
        connect = sqlite3.connect
        observed = []
        def checked(path, *args, **kwargs):
            if str(path).startswith(str(self.e.mail.base / 'lookup-')):
                observed.append(Path(path).stat().st_mode & 0o777)
            return connect(path, *args, **kwargs)
        previous = os.umask(0)
        try:
            with patch('vectorcp.mail.sqlite3.connect', side_effect=checked):
                self.create()
        finally:
            os.umask(previous)
        self.assertEqual(observed, [0o600])
        self.assertEqual(self.e.mail.projection.stat().st_mode & 0o777, 0o640)


if __name__ == '__main__':
    unittest.main()
