"""Account security, with authorization and credentials kept in the agent."""
import base64
import hmac
import re
import secrets
import struct
import time

from .core import Fault, digest, password_hash, password_matches, text

OPERATIONS = {'security.status', 'security.sessions', 'security.revoke',
              'security.password', 'security.enroll', 'security.confirm',
              'security.cancel', 'security.disable', 'security.recovery',
              'profile.get', 'profile.update', 'accounts.password'}
READ_ONLY = {'security.status', 'security.sessions', 'profile.get'}
MAX_SESSIONS = 20


def migrate(db):
    for table, definitions in {
        'users': [('password_change_required', 'INTEGER NOT NULL DEFAULT 0'),
                  ('contact_email', "TEXT NOT NULL DEFAULT ''")],
    }.items():
        columns = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
        for name, definition in definitions:
            if name not in columns:
                db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + name + ' ' + definition)
    db.executescript('''
      CREATE INDEX IF NOT EXISTS failure_windows ON failures(window);
      CREATE TABLE IF NOT EXISTS session_details (
        id TEXT PRIMARY KEY, token TEXT NOT NULL UNIQUE REFERENCES sessions(token) ON DELETE CASCADE,
        created INTEGER NOT NULL, last_seen INTEGER NOT NULL, client TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS second_factors (
        user_id INTEGER PRIMARY KEY REFERENCES users(id), secret TEXT,
        last_step INTEGER NOT NULL DEFAULT -1, enabled_at INTEGER NOT NULL DEFAULT 0,
        pending_secret TEXT, pending_session TEXT, pending_until INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS recovery_codes (
        user_id INTEGER NOT NULL REFERENCES users(id), hash TEXT NOT NULL,
        PRIMARY KEY(user_id,hash));
    ''')
    # Keep the original four-column session table compatible with startup rollback.
    for row in db.execute('SELECT s.token,s.expires FROM sessions s LEFT JOIN session_details d ON d.token=s.token WHERE d.id IS NULL').fetchall():
        created = max(0, row['expires'] - 8 * 3600)
        db.execute('INSERT INTO session_details VALUES(?,?,?,?,?)', (secrets.token_urlsafe(18), row['token'], created, created, ''))


def totp(secret, step, digits=6, algorithm='sha1'):
    """RFC 6238; algorithm/digits parameters also allow the published test vectors."""
    key = base64.b32decode(secret)
    value = hmac.new(key, struct.pack('>Q', step), algorithm).digest()
    offset = value[-1] & 15
    number = struct.unpack('>I', value[offset:offset + 4])[0] & 0x7fffffff
    return str(number % (10 ** digits)).zfill(digits)


def email(value):
    if not isinstance(value, str) or len(value) > 160 or value != value.strip():
        raise Fault('Enter a contact email address, or leave it empty.')
    if value and not re.fullmatch(r'[^\s@<>\x00-\x1f]+@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}', value):
        raise Fault('Enter a valid contact email address.')
    return value


class Security:
    def __init__(self, engine):
        self.e = engine

    @staticmethod
    def enabled(db, user_id):
        return db.execute('SELECT * FROM second_factors WHERE user_id=? AND secret IS NOT NULL', (user_id,)).fetchone()

    @staticmethod
    def client(value):
        return ''.join(c for c in value if c.isprintable())[:180] if isinstance(value, str) else ''

    def session(self, db, user, client=''):
        from .core import SESSION_SECONDS
        now = int(time.time())
        token, csrf, ident = secrets.token_urlsafe(48), secrets.token_urlsafe(32), secrets.token_urlsafe(18)
        db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(token), user['id'], csrf, now + SESSION_SECONDS))
        db.execute('INSERT INTO session_details VALUES(?,?,?,?,?)', (ident, digest(token), now, now, self.client(client)))
        db.execute('DELETE FROM sessions WHERE user_id=? AND token NOT IN (SELECT s.token FROM sessions s JOIN session_details d ON d.token=s.token WHERE s.user_id=? ORDER BY d.created DESC,d.rowid DESC LIMIT ?)',
                   (user['id'], user['id'], MAX_SESSIONS))
        return {'token': token, 'csrf': csrf, 'user': self.e.public_user(user)}

    @staticmethod
    def check_limit(db, key):
        now = int(time.time())
        row = db.execute('SELECT * FROM failures WHERE username=?', (key,)).fetchone()
        if row and row['blocked_until'] > now:
            raise Fault('Too many attempts. Try again in 15 minutes.', 429)
        return row

    @staticmethod
    def failed(db, key, row):
        now = int(time.time())
        current = row and now - row['window'] < 900
        count, window = (row['count'] + 1, row['window']) if current else (1, now)
        db.execute('INSERT OR REPLACE INTO failures VALUES(?,?,?,?)', (key, count, window, now + 900 if count >= 5 else 0))
        db.commit()  # Failure counters must survive the rejected operation's rollback.
        raise Fault('Password or verification code is incorrect.', 401)

    @staticmethod
    def match_step(secret, code, after=-1):
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
            return None
        current = int(time.time()) // 30
        for step in (current, current - 1, current + 1):
            if step > after and hmac.compare_digest(totp(secret, step), code):
                return step
        return None

    def factor(self, db, user_id, code):
        factor = self.enabled(db, user_id)
        if not factor:
            return True
        step = self.match_step(factor['secret'], code, factor['last_step'])
        if step is not None:
            db.execute('UPDATE second_factors SET last_step=? WHERE user_id=?', (step, user_id))
            return True
        if isinstance(code, str) and re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{8}){3}', code):
            removed = db.execute('DELETE FROM recovery_codes WHERE user_id=? AND hash=?', (user_id, digest(code.lower()))).rowcount
            return removed == 1
        return False

    def verify(self, db, actor, data):
        key = 'security:' + str(actor['id'])
        failure = self.check_limit(db, key)
        if not password_matches(data.get('password'), actor['password']) or not self.factor(db, actor['id'], data.get('code')):
            self.failed(db, key, failure)
        db.execute('DELETE FROM failures WHERE username=?', (key,))

    def revoke_others(self, db, actor):
        db.execute('DELETE FROM sessions WHERE user_id=? AND token NOT IN (SELECT token FROM session_details WHERE id=?)', (actor['id'], actor['session_id']))

    @staticmethod
    def recovery(db, user_id):
        values = [secrets.token_hex(16) for _ in range(8)]
        codes = ['-'.join(value[i:i + 8] for i in range(0, 32, 8)) for value in values]
        db.execute('DELETE FROM recovery_codes WHERE user_id=?', (user_id,))
        db.executemany('INSERT INTO recovery_codes VALUES(?,?)', [(user_id, digest(code)) for code in codes])
        return codes

    def dispatch(self, db, actor, method, data):
        if method == 'profile.get':
            return {'name': actor['name'], 'contact_email': actor['contact_email'], 'username': actor['username']}
        if method == 'profile.update':
            name, contact = text(data.get('name'), 'name', 80), email(data.get('contact_email', ''))
            self.verify(db, actor, data)
            db.execute('UPDATE users SET name=?,contact_email=? WHERE id=?', (name, contact, actor['id']))
            self.e.log(db, actor, 'profile.updated', actor['username'])
            return {'ok': True}
        if method == 'security.status':
            factor = self.enabled(db, actor['id'])
            return {'enabled': bool(factor), 'enabled_at': factor['enabled_at'] if factor else None,
                    'recovery_remaining': db.execute('SELECT COUNT(*) FROM recovery_codes WHERE user_id=?', (actor['id'],)).fetchone()[0],
                    'password_change_required': bool(actor['password_change_required']),
                    'password_minimum': 15, 'password_maximum': 256}
        if method == 'security.sessions':
            return {'sessions': [dict(row, current=row['id'] == actor['session_id']) for row in db.execute(
                'SELECT d.id,d.created,d.last_seen,s.expires,d.client FROM sessions s JOIN session_details d ON d.token=s.token WHERE s.user_id=? AND s.expires>? ORDER BY d.last_seen DESC', (actor['id'], int(time.time())))]}
        if method == 'security.revoke':
            ident = data.get('id')
            if ident == 'others':
                self.revoke_others(db, actor)
            elif not isinstance(ident, str) or not db.execute('DELETE FROM sessions WHERE token IN (SELECT token FROM session_details WHERE id=?) AND user_id=?', (ident, actor['id'])).rowcount:
                raise Fault('Session not found.', 404)
            self.e.log(db, actor, 'session.revoked', 'other sessions' if ident == 'others' else ident)
            return {'ok': True, 'signed_out': ident == actor['session_id']}
        if method == 'security.password':
            new = data.get('new_password')
            hashed = password_hash(new)
            self.verify(db, actor, data)
            if password_matches(new, actor['password']):
                raise Fault('Choose a different password.')
            db.execute('UPDATE users SET password=?,password_change_required=0 WHERE id=?', (hashed, actor['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (actor['id'],))
            db.execute('UPDATE second_factors SET pending_secret=NULL,pending_session=NULL,pending_until=0 WHERE user_id=?', (actor['id'],))
            self.e.log(db, actor, 'password.changed', actor['username'])
            return {'ok': True, 'signed_out': True}
        if method == 'accounts.password':
            target = self.e.distribution.target(db, actor, data.get('id'))
            if actor['role'] == 'reseller' and target['admin_lock']:
                raise Fault('The server owner has locked this account.', 403)
            hashed = password_hash(data.get('new_password'))
            self.verify(db, actor, data)
            db.execute('UPDATE users SET password=?,password_change_required=1 WHERE id=?', (hashed, target['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (target['id'],))
            db.execute('UPDATE second_factors SET pending_secret=NULL,pending_session=NULL,pending_until=0 WHERE user_id=?', (target['id'],))
            self.e.log(db, actor, 'password.reset_required', target['username'])
            return {'ok': True}
        if method == 'security.cancel':
            db.execute('UPDATE second_factors SET pending_secret=NULL,pending_session=NULL,pending_until=0 WHERE user_id=? AND pending_session=?', (actor['id'], actor['session_id']))
            return {'ok': True}
        self.verify(db, actor, data)
        if method == 'security.enroll':
            if self.enabled(db, actor['id']):
                raise Fault('Two-factor authentication is already enabled.', 409)
            secret = base64.b32encode(secrets.token_bytes(20)).decode()
            db.execute('INSERT INTO second_factors(user_id,pending_secret,pending_session,pending_until) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET pending_secret=excluded.pending_secret,pending_session=excluded.pending_session,pending_until=excluded.pending_until',
                       (actor['id'], secret, actor['session_id'], int(time.time()) + 600))
            self.e.log(db, actor, 'two_factor.enrollment_started', actor['username'])
            return {'secret': secret, 'issuer': 'VectorCP', 'account': actor['username'], 'digits': 6, 'period': 30}
        if method == 'security.confirm':
            factor = db.execute('SELECT * FROM second_factors WHERE user_id=?', (actor['id'],)).fetchone()
            if not factor or factor['secret'] or factor['pending_session'] != actor['session_id'] or factor['pending_until'] <= int(time.time()) or not factor['pending_secret']:
                raise Fault('Enrollment expired. Start again.', 409)
            step = self.match_step(factor['pending_secret'], data.get('verification_code'))
            if step is None:
                # The password was correct; an invalid enrollment code still consumes an attempt.
                key = 'enrollment:' + str(actor['id'])
                self.failed(db, key, self.check_limit(db, key))
            self.check_limit(db, 'enrollment:' + str(actor['id']))
            db.execute('DELETE FROM failures WHERE username=?', ('enrollment:' + str(actor['id']),))
            db.execute('UPDATE second_factors SET secret=pending_secret,last_step=?,enabled_at=?,pending_secret=NULL,pending_session=NULL,pending_until=0 WHERE user_id=?', (step, int(time.time()), actor['id']))
            codes = self.recovery(db, actor['id'])
            self.revoke_others(db, actor)
            self.e.log(db, actor, 'two_factor.enabled', actor['username'])
            return {'ok': True, 'recovery_codes': codes}
        if method == 'security.disable':
            if not self.enabled(db, actor['id']):
                raise Fault('Two-factor authentication is not enabled.', 409)
            db.execute('DELETE FROM second_factors WHERE user_id=?', (actor['id'],))
            db.execute('DELETE FROM recovery_codes WHERE user_id=?', (actor['id'],))
            self.revoke_others(db, actor)
            self.e.log(db, actor, 'two_factor.disabled', actor['username'])
            return {'ok': True}
        if method == 'security.recovery':
            if not self.enabled(db, actor['id']):
                raise Fault('Enable two-factor authentication first.', 409)
            codes = self.recovery(db, actor['id'])
            self.revoke_others(db, actor)
            self.e.log(db, actor, 'two_factor.recovery_replaced', actor['username'])
            return {'ok': True, 'recovery_codes': codes}
        raise Fault('Unknown security operation.', 404)
