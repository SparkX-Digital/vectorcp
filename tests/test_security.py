import base64
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault, digest, password_hash
from vectorcp.security import MAX_SESSIONS, totp


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vectorcp-security-')
        self.root = Path(self.tmp.name)
        self.password = secrets.token_urlsafe(24)
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.owner = self.e.bootstrap({'username': 'owner', 'name': 'Owner',
            'password': self.password, 'setup_token': self.e.setup_token()})
        self.uid = self.call(self.owner, 'accounts.create', {'username': 'alice',
            'name': 'Alice', 'password': self.password})['id']
        self.alice = self.e.login({'username': 'alice', 'password': self.password}, 'Alice browser')

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, who, method, data=None, **extra):
        return self.e.dispatch(dict(method=method, data=data or {}, token=who['token'], csrf=who['csrf'], **extra))

    def denied(self, status, action):
        with self.assertRaises(Fault) as error:
            action()
        self.assertEqual(error.exception.status, status)

    def enroll(self):
        secret = self.call(self.alice, 'security.enroll', {'password': self.password})['secret']
        step = int(time.time())//30
        # Pin one time window throughout each flow to avoid timing-sensitive tests.
        self.clock = patch('time.time', return_value=step*30+3)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        result = self.call(self.alice, 'security.confirm', {'password': self.password,
            'verification_code': totp(secret, step)})
        return secret, step, result['recovery_codes']

    def test_rfc6238_sha1_sha256_sha512_vectors(self):
        vectors = [
            (59, '94287082', '46119246', '90693936'),
            (1111111109, '07081804', '68084774', '25091201'),
            (1111111111, '14050471', '67062674', '99943326'),
            (1234567890, '89005924', '91819424', '93441116'),
            (2000000000, '69279037', '90698825', '38618901'),
            (20000000000, '65353130', '77737706', '47863826')]
        for stamp, sha1, sha256, sha512 in vectors:
            for size, algorithm, expected in [(20, 'sha1', sha1), (32, 'sha256', sha256), (64, 'sha512', sha512)]:
                raw = (b'1234567890'*7)[:size]
                with self.subTest(stamp=stamp, algorithm=algorithm):
                    self.assertEqual(totp(base64.b32encode(raw).decode(), stamp//30, 8, algorithm), expected)

    def test_sessions_inventory_is_private_scoped_and_revokes_only_the_target(self):
        other = self.e.login({'username': 'alice', 'password': self.password}, '<script>device</script>\n')
        sessions = self.call(self.alice, 'security.sessions')['sessions']
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sum(s['current'] for s in sessions), 1)
        self.assertFalse(any(k in json.dumps(sessions) for k in [other['token'], self.alice['token'], 'csrf']))
        self.assertNotIn('\n', next(s['client'] for s in sessions if not s['current']))
        ident = next(s['id'] for s in sessions if not s['current'])
        self.denied(404, lambda: self.call(self.owner, 'security.revoke', {'id': ident}))
        self.denied(403, lambda: self.e.dispatch({'method': 'security.revoke', 'token': self.alice['token'], 'data': {'id': ident}}))
        self.call(self.alice, 'security.revoke', {'id': ident})
        self.denied(401, lambda: self.call(other, 'overview'))
        self.assertEqual(self.call(self.alice, 'overview')['user']['id'], self.uid)

    def test_revoke_others_and_current_session(self):
        other = self.e.login({'username': 'alice', 'password': self.password})
        self.call(self.alice, 'security.revoke', {'id': 'others'})
        self.denied(401, lambda: self.call(other, 'overview'))
        ident = self.call(self.alice, 'security.sessions')['sessions'][0]['id']
        self.assertTrue(self.call(self.alice, 'security.revoke', {'id': ident})['signed_out'])
        self.denied(401, lambda: self.call(self.alice, 'overview'))

    def test_session_limit_retains_latest_devices(self):
        # Session creation itself is tested, avoiding repeated password hashing.
        with self.e.db() as db:
            user = db.execute('SELECT * FROM users WHERE id=?', (self.uid,)).fetchone()
            for _ in range(MAX_SESSIONS):
                latest = self.e.session(db, user)
        self.denied(401, lambda: self.call(self.alice, 'overview'))
        self.assertEqual(len(self.call(latest, 'security.sessions')['sessions']), MAX_SESSIONS)

    def test_enrollment_requires_password_confirmation_and_its_own_session(self):
        other = self.e.login({'username': 'alice', 'password': self.password})
        self.denied(401, lambda: self.call(self.alice, 'security.enroll', {'password': 'incorrect'}))
        secret = self.call(self.alice, 'security.enroll', {'password': self.password})['secret']
        self.assertFalse(self.call(self.alice, 'security.status')['enabled'])
        data = {'password': self.password, 'verification_code': totp(secret, int(time.time())//30)}
        self.denied(409, lambda: self.call(other, 'security.confirm', data))
        self.call(self.alice, 'security.cancel')
        self.denied(409, lambda: self.call(self.alice, 'security.confirm', data))
        self.assertFalse(self.call(self.alice, 'security.status')['enabled'])

    def test_expired_enrollment_and_durable_enrollment_throttling(self):
        secret = self.call(self.alice, 'security.enroll', {'password': self.password})['secret']
        now = int(time.time())
        with patch('time.time', return_value=now+601):
            self.denied(409, lambda: self.call(self.alice, 'security.confirm', {'password': self.password,
                'verification_code': totp(secret, (now+601)//30)}))
        bad = '123'  # Invalid length, independent of the generated secret.
        for _ in range(5):
            self.denied(401, lambda: self.call(self.alice, 'security.confirm', {'password': self.password, 'verification_code': bad}))
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.denied(429, lambda: self.call(self.alice, 'security.confirm', {'password': self.password,
            'verification_code': totp(secret, int(time.time())//30)}))

    def test_mfa_login_does_not_issue_a_session_until_verified_and_rejects_replay(self):
        other = self.e.login({'username': 'alice', 'password': self.password})
        secret, step, codes = self.enroll()
        self.denied(401, lambda: self.call(other, 'overview'))
        pending = self.e.login({'username': 'alice', 'password': self.password})
        self.assertEqual(pending, {'mfa_required': True})
        self.denied(401, lambda: self.e.login({'username': 'alice', 'password': self.password, 'code': totp(secret, step)}))
        with patch('time.time', return_value=(step+1)*30+3):
            session = self.e.login({'username': 'alice', 'password': self.password, 'code': totp(secret, step+1)})
            self.assertEqual(self.call(session, 'overview')['user']['id'], self.uid)
            self.denied(401, lambda: self.e.login({'username': 'alice', 'password': self.password, 'code': totp(secret, step+1)}))
        self.assertEqual(len(codes), 8)

    def test_recovery_codes_are_one_use_hashed_and_durable(self):
        secret, step, codes = self.enroll()
        with self.e.db() as db:
            stored = [r[0] for r in db.execute('SELECT hash FROM recovery_codes')]
        self.assertFalse(set(stored) & set(codes))
        session = self.e.login({'username': 'alice', 'password': self.password, 'code': codes[0]})
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.denied(401, lambda: self.e.login({'username': 'alice', 'password': self.password, 'code': codes[0]}))
        self.assertEqual(self.call(session, 'security.status')['recovery_remaining'], 7)
        self.denied(401, lambda: self.call(session, 'security.disable', {'password': self.password}))
        replaced = self.call(session, 'security.recovery', {'password': self.password, 'code': codes[1]})['recovery_codes']
        self.denied(401, lambda: self.e.login({'username': 'alice', 'password': self.password, 'code': codes[2]}))
        self.call(session, 'security.disable', {'password': self.password, 'code': replaced[0]})
        self.assertFalse(self.call(session, 'security.status')['enabled'])
        self.assertIn('token', self.e.login({'username': 'alice', 'password': self.password}))

    def test_password_reset_revokes_sessions_preserves_mfa_and_requires_rotation(self):
        secret, step, codes = self.enroll()
        temporary, final = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self.call(self.owner, 'accounts.password', {'id': self.uid, 'new_password': temporary, 'password': self.password})
        self.denied(401, lambda: self.call(self.alice, 'overview'))
        self.assertEqual(self.e.login({'username': 'alice', 'password': temporary}), {'mfa_required': True})
        reset = self.e.login({'username': 'alice', 'password': temporary, 'code': codes[0]})
        self.assertTrue(reset['user']['password_change_required'])
        for method in ('sites.list', 'profile.get', 'security.sessions', 'accounts.list', 'files.list'):
            self.denied(403, lambda: self.call(reset, method))
        self.call(reset, 'security.password', {'password': temporary, 'new_password': final, 'code': codes[1]})
        self.denied(401, lambda: self.call(reset, 'overview'))
        changed = self.e.login({'username': 'alice', 'password': final, 'code': codes[2]})
        self.assertFalse(changed['user']['password_change_required'])
        self.assertEqual(self.call(changed, 'sites.list'), {'sites': []})

    def test_password_policy_keeps_legacy_login_and_rejects_predictable_new_secrets(self):
        for password in ('short', 'aaaaaaaaaaaaaaaaaaaa', 'passwordpassword', '123456789012345'):
            self.denied(400, lambda: self.call(self.alice, 'security.password', {'password': self.password, 'new_password': password}))
        self.denied(400, lambda: self.call(self.alice, 'security.password', {'password': self.password, 'new_password': self.password}))
        self.denied(403, lambda: self.call(self.alice, 'accounts.password', {'id': self.uid}))
        self.denied(404, lambda: self.call(self.owner, 'accounts.password', {'id': self.owner['user']['id']}))
        # Existing shorter credentials can authenticate and move to the new policy.
        legacy = 'OldPass123456'
        salt = b'legacy-test-salt'
        import hashlib
        hashed = 'pbkdf2_sha256$600000$%s$%s' % (salt.hex(), hashlib.pbkdf2_hmac('sha256', legacy.encode(), salt, 600000).hex())
        with self.e.db() as db:
            db.execute('UPDATE users SET password=? WHERE id=?', (hashed, self.uid))
        self.assertIn('token', self.e.login({'username': 'alice', 'password': legacy}))

    def test_security_password_failures_remain_throttled_after_restart(self):
        for _ in range(5):
            self.denied(401, lambda: self.call(self.alice, 'security.password', {'password': 'wrong', 'new_password': secrets.token_urlsafe(24)}))
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.denied(429, lambda: self.call(self.alice, 'security.password', {'password': self.password, 'new_password': secrets.token_urlsafe(24)}))
        # Equality with the existing password must not bypass credential throttling
        # or reveal that a guessed new_password matches the stored credential.
        self.denied(429, lambda: self.call(self.alice, 'security.password', {'password': 'wrong', 'new_password': self.password}))

    def test_login_names_cannot_collide_with_internal_attempt_counters_and_old_records_expire(self):
        for key in ('security:'+str(self.uid), 'enrollment:'+str(self.uid)):
            for _ in range(5):
                self.denied(401, lambda: self.e.login({'username': key, 'password': 'wrong'}))
            with self.e.db() as db:
                self.assertIsNone(db.execute('SELECT * FROM failures WHERE username=?', (key,)).fetchone())
        self.call(self.alice, 'profile.update', {'name': 'Still accessible', 'password': self.password})
        with self.e.db() as db:
            db.execute("INSERT INTO failures VALUES('expired_unknown',5,?,?)", (int(time.time())-2000, int(time.time())-1000))
        self.e.login({'username': 'alice', 'password': self.password})
        with self.e.db() as db:
            self.assertIsNone(db.execute("SELECT * FROM failures WHERE username='expired_unknown'").fetchone())

    def test_contact_changes_validate_inputs_and_do_not_modify_other_accounts(self):
        self.call(self.alice, 'profile.update', {'name': 'Alice Studio', 'contact_email': 'alice@example.com', 'password': self.password, 'id': self.owner['user']['id']})
        self.assertEqual(self.call(self.alice, 'profile.get')['name'], 'Alice Studio')
        self.assertEqual(self.call(self.owner, 'profile.get')['name'], 'Owner')
        for contact in ('bad', 'a@example.com\n', '<script>@example.com', 'a@localhost'):
            self.denied(400, lambda: self.call(self.owner, 'accounts.update', {'id': self.uid, 'name': 'Changed', 'contact_email': contact}))
        self.assertEqual(self.call(self.alice, 'profile.get')['name'], 'Alice Studio')
        self.call(self.owner, 'accounts.update', {'id': self.uid, 'name': 'Managed name', 'contact_email': ''})
        self.assertEqual(self.call(self.alice, 'profile.get')['name'], 'Managed name')

    def test_upgrade_preserves_a_four_column_legacy_session_and_credentials(self):
        legacy = self.root/'legacy'
        legacy.mkdir()
        with sqlite3.connect(str(legacy/'control.sqlite3')) as db:
            db.executescript('''CREATE TABLE users (id INTEGER PRIMARY KEY,username TEXT UNIQUE,name TEXT,password TEXT,role TEXT,active INTEGER DEFAULT 1,site_limit INTEGER DEFAULT 5,storage_mb INTEGER DEFAULT 100,created INTEGER);
            CREATE TABLE sessions (token TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires INTEGER);''')
            db.execute("INSERT INTO users(username,name,password,role,created) VALUES('legacy','Legacy',?,'admin',?)", (password_hash(self.password), int(time.time())))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest('old-token'), 1, 'old-csrf', int(time.time())+3600))
        engine = Engine(legacy, self.root/'legacy-sites', development=True)
        overview = engine.dispatch({'method': 'overview', 'token': 'old-token'})
        self.assertEqual(overview['user']['username'], 'legacy')
        self.assertEqual(overview['csrf'], 'old-csrf')
        self.assertIn('token', engine.login({'username': 'legacy', 'password': self.password}))
        with engine.db() as db:
            # The previous application inserts without a column list during rollback.
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest('rollback-token'), 1, 'rollback-csrf', int(time.time())+3600))
        engine = Engine(legacy, self.root/'legacy-sites', development=True)
        self.assertEqual(engine.dispatch({'method': 'overview', 'token': 'rollback-token'})['csrf'], 'rollback-csrf')

    def test_audit_does_not_record_credential_or_enrollment_material(self):
        secret, step, codes = self.enroll()
        events = json.dumps(self.call(self.alice, 'audit'))
        self.assertNotIn(secret, events)
        self.assertNotIn(self.password, events)
        self.assertFalse(any(code in events for code in codes))


if __name__ == '__main__':
    unittest.main()
