"""Scoped MariaDB administration. User SQL never runs as database root."""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

from .core import Fault, integer, text

READ_ONLY = {'databases.inspect', 'databases.browse', 'databases.users'}
OPERATIONS = READ_ONLY | {'databases.users.create', 'databases.users.grants',
                         'databases.users.rotate', 'databases.users.delete',
                         'databases.export', 'databases.import'}
PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'INDEX',
              'DROP', 'CREATE VIEW', 'SHOW VIEW', 'TRIGGER')
SQL_LIMIT = 1024 * 1024


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS database_users (
      username TEXT PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES sites(id),
      label TEXT NOT NULL, created INTEGER NOT NULL)''')


def literal(value):
    return "CONVERT(0x%s USING utf8mb4)" % value.encode('utf-8').hex()


def identifier(value):
    return '`' + value.replace('`', '``') + '`'


def grant_pattern(value):
    # MariaDB treats underscores as wildcards even in quoted database GRANTs.
    return value.replace('\\', '\\\\').replace('_', '\\_').replace('%', '\\%')


def privileges(value):
    if not isinstance(value, list) or not value or len(value) > len(PRIVILEGES) or any(v not in PRIVILEGES for v in value):
        raise Fault('Choose one or more supported database permissions.')
    return [p for p in PRIVILEGES if p in value]


class Databases:
    def __init__(self, engine):
        self.e = engine

    def allocation(self, db, actor, data):
        site = self.e.owned_site(db, actor, data.get('site_id'))
        self.e.site_idle(db, site)
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        from .distribution import available
        if not available(db, owner):
            raise Fault('This customer or its reseller is locked.', 409)
        self.e.distribution.require_feature(db, owner, 'databases')
        slot = self.e.hosting.slot(owner)
        if site['database_name'] != 'site_%d' % site['id']:
            raise Fault('Create a database for this website first.', 409)
        return site, owner, slot

    def primary(self, site, slot):
        path = self.e.state / ('hosting/database-%d.json' % site['id'])
        try:
            values = json.loads(path.read_text())
            assert values['name'] == values['username'] == site['database_name']
            assert re.fullmatch(r'[A-Za-z0-9_-]{24,128}', values['password'])
        except (OSError, ValueError, KeyError, AssertionError, TypeError):
            raise Fault('The private database credentials need administrator review.', 409)
        return values

    def client(self, slot, credentials, sql, maximum=3 * 1024 * 1024):
        """Bounded, noninteractive client with no shell or LOCAL file commands.

        The password is in a private temporary option file, never argv or logs.
        Do not change this to root authentication for customer-supplied SQL.
        """
        with tempfile.TemporaryDirectory(dir=str(self.e.state / 'hosting')) as folder:
            config = Path(folder) / 'client.cnf'
            config.write_text('[client]\nuser=%s\npassword=%s\n' % (credentials['username'], credentials['password']))
            config.chmod(0o600)
            args = ['/usr/bin/prlimit', '--fsize=%d' % maximum, '--cpu=20', '--',
                    '/usr/bin/mariadb', '--defaults-file=' + str(config), '--protocol=socket',
                    '--socket=' + self.e.hosting.db_socket(slot), '--default-character-set=utf8mb4',
                    '--binary-mode=1', '--local-infile=0', '--batch', '--raw', '--skip-column-names',
                    credentials['name']]
            with tempfile.TemporaryFile(dir=folder) as output:
                try:
                    result = subprocess.run(args, input=sql, stdout=output, stderr=subprocess.DEVNULL, timeout=30)
                except subprocess.TimeoutExpired:
                    raise Fault('The database operation exceeded its time limit.', 409)
                if result.returncode:
                    raise Fault('The database rejected this operation. Check the SQL format and database permissions.', 409)
                output.seek(0)
                raw = output.read(maximum + 1)
                if len(raw) > maximum:
                    raise Fault('The database result exceeds the display limit.', 413)
                return raw

    def rows(self, slot, credentials, sql):
        raw = self.client(slot, credentials, ('SET STATEMENT max_statement_time=5 FOR ' + sql).encode())
        return [json.loads(line) for line in raw.decode('utf-8').splitlines() if line]

    def user_grants(self, slot, name, username):
        raw = self.e.hosting.sql(slot, 'SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s AND GRANTEE=%s ORDER BY PRIVILEGE_TYPE;' % (literal(grant_pattern(name)), literal("'%s'@'localhost'" % username)))
        return sorted(raw.decode().splitlines())

    def user(self, db, site, data):
        username = text(data.get('username'), 'database user', 64)
        if not re.fullmatch(r'v[1-9][0-9]*_[0-9a-f]{12}', username):
            raise Fault('Database user not found.', 404)
        row = db.execute('SELECT * FROM database_users WHERE username=? AND site_id=?', (username, site['id'])).fetchone()
        if not row:
            raise Fault('Database user not found.', 404)
        return row

    def disconnect(self, slot, username):
        raw = self.e.hosting.sql(slot, 'SELECT ID FROM information_schema.PROCESSLIST WHERE USER=%s;' % literal(username))
        for line in raw.decode().splitlines():
            if line.isdigit():
                with contextlib.suppress(Fault):
                    self.e.hosting.sql(slot, 'KILL CONNECTION %d;' % int(line))

    def dispatch(self, db, actor, method, data):
        site, owner, slot = self.allocation(db, actor, data)
        self.e.hosting.start_db(slot)
        name = site['database_name']
        credentials = self.primary(site, slot)
        if method == 'databases.inspect':
            tables = self.rows(slot, credentials, "SELECT JSON_OBJECT('name',TABLE_NAME,'kind',TABLE_TYPE,'rows',TABLE_ROWS,'bytes',COALESCE(DATA_LENGTH,0)+COALESCE(INDEX_LENGTH,0),'engine',ENGINE) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME LIMIT 201;" % literal(name))
            total = self.rows(slot, credentials, "SELECT JSON_OBJECT('bytes',COALESCE(SUM(DATA_LENGTH+INDEX_LENGTH),0),'tables',COUNT(*)) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s;" % literal(name))[0]
            return {'name': name, 'tables': tables[:200], 'more': len(tables)>200, 'usage': total, 'privileges': PRIVILEGES}
        if method == 'databases.browse':
            table = text(data.get('table'), 'table', 64)
            offset = integer(data.get('offset', 0), 'row offset', 0, 10000)
            columns = self.rows(slot, credentials, "SELECT JSON_OBJECT('name',COLUMN_NAME,'type',COLUMN_TYPE) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION LIMIT 65;" % (literal(name), literal(table)))
            if not columns:
                raise Fault('Table not found.', 404)
            if len(columns)>64:
                raise Fault('Browser view supports tables with up to 64 columns. Use a SQL export for this table.', 409)
            expressions = ','.join('HEX(LEFT(CAST(%s AS BINARY),512))' % identifier(c['name']) for c in columns)
            rows = self.rows(slot, credentials, 'SELECT JSON_ARRAY(%s) FROM %s LIMIT 26 OFFSET %d;' % (expressions, identifier(table), offset))
            decoded = [[None if cell is None else bytes.fromhex(cell).decode('utf-8', 'replace') + ('…' if len(cell)==1024 else '') for cell in row] for row in rows[:25]]
            return {'columns': columns, 'rows': decoded, 'offset': offset, 'more': len(rows)>25}
        if method == 'databases.users':
            users = [dict(r) for r in db.execute('SELECT * FROM database_users WHERE site_id=? ORDER BY created,username', (site['id'],))]
            for user in users:
                user['privileges'] = self.user_grants(slot, name, user['username'])
            return {'users': users, 'primary': credentials['username'], 'privileges': PRIVILEGES}
        if method == 'databases.users.create':
            label = text(data.get('label'), 'user label', 80)
            grants = privileges(data.get('privileges'))
            if db.execute('SELECT COUNT(*) FROM database_users WHERE site_id=?', (site['id'],)).fetchone()[0] >= 8:
                raise Fault('This database already has eight additional users.', 409)
            username, password = 'v%d_%s' % (site['id'], secrets.token_hex(6)), secrets.token_urlsafe(32)
            try:
                self.e.hosting.sql(slot, "CREATE USER '%s'@'localhost' IDENTIFIED BY '%s'; GRANT %s ON `%s`.* TO '%s'@'localhost';" % (username, password, ','.join(grants), grant_pattern(name), username))
                db.execute('INSERT INTO database_users VALUES(?,?,?,?)', (username, site['id'], label, int(time.time())))
                db.commit()
            except Exception:
                with contextlib.suppress(Fault):
                    self.e.hosting.sql(slot, "DROP USER IF EXISTS '%s'@'localhost';" % username)
                raise
            self.e.log(db, actor, 'database.user_created', site['domain'] + '/' + username)
            return {'username': username, 'password': password, 'name': name, 'socket': self.e.hosting.db_socket(slot)}
        if method in {'databases.users.grants', 'databases.users.rotate', 'databases.users.delete'}:
            user = self.user(db, site, data)
            username = user['username']
            if method == 'databases.users.grants':
                grants = privileges(data.get('privileges'))
                self.e.hosting.sql(slot, "REVOKE ALL PRIVILEGES, GRANT OPTION FROM '%s'@'localhost'; GRANT %s ON `%s`.* TO '%s'@'localhost';" % (username, ','.join(grants), grant_pattern(name), username))
                result = {'ok': True}
            elif method == 'databases.users.rotate':
                password = secrets.token_urlsafe(32)
                self.e.hosting.sql(slot, "ALTER USER '%s'@'localhost' IDENTIFIED BY '%s';" % (username, password))
                result = {'username': username, 'password': password, 'name': name, 'socket': self.e.hosting.db_socket(slot)}
            else:
                if data.get('confirm') != username:
                    raise Fault('Type the database username to confirm removal.')
                self.e.hosting.sql(slot, "DROP USER IF EXISTS '%s'@'localhost';" % username)
                db.execute('DELETE FROM database_users WHERE username=?', (username,))
                result = {'ok': True}
            self.disconnect(slot, username)
            self.e.log(db, actor, method, site['domain'] + '/' + username)
            return result
        if method == 'databases.export':
            payload = self.e.hosting.dump_database(slot, name, maximum=SQL_LIMIT)
            self.e.log(db, actor, 'database.exported', site['domain'])
            return {'filename': name + '.sql', 'base64': base64.b64encode(payload).decode(), 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
        raise Fault('Unknown database operation.', 404)

    def validate_import(self, data, site):
        if data.get('confirm') != site['database_name']:
            raise Fault('Type the database name to confirm SQL import.')
        try:
            encoded = data.get('base64')
            if not isinstance(encoded, str) or len(encoded) > (SQL_LIMIT+2)//3*4:
                raise ValueError()
            payload = base64.b64decode(encoded, validate=True)
            if not payload or len(payload)>SQL_LIMIT:
                raise ValueError()
        except (ValueError, TypeError):
            raise Fault('Choose a nonempty SQL file up to 1 MB.')
        return payload

    def import_sql(self, site, owner, data):
        payload = self.validate_import(data, site)
        slot = self.e.hosting.slot(owner)
        self.e.hosting.start_db(slot)
        credentials = self.primary(site, slot)
        username, password = credentials['username'], credentials['password']
        grants = self.e.hosting.sql(slot, "SHOW GRANTS FOR '%s'@'localhost';" % username, raw=True).decode().splitlines()
        accepted = {'GRANT USAGE ON *.*', 'GRANT ALL PRIVILEGES ON '+identifier(site['database_name'])+'.*',
                    'GRANT ALL PRIVILEGES ON '+identifier(grant_pattern(site['database_name']))+'.*'}
        if not grants or any(g.split(' TO ',1)[0] not in accepted or 'WITH GRANT OPTION' in g for g in grants):
            raise Fault('The application user has unexpected grants. Administrator review is required before SQL import.', 409)
        # Narrow legacy unescaped names before accepting any customer SQL. Keep
        # the existing password and application identity, and grant before revoke.
        legacy = 'GRANT ALL PRIVILEGES ON '+identifier(site['database_name'])+'.*'
        if any(g.split(' TO ',1)[0]==legacy for g in grants):
            self.e.hosting.sql(slot, "GRANT ALL ON `%s`.* TO '%s'@'localhost'; REVOKE ALL PRIVILEGES ON `%s`.* FROM '%s'@'localhost';" % (grant_pattern(site['database_name']), username, site['database_name'], username))
        # The protected application account has privileges only on this database.
        # Stable identity also keeps imported views/triggers' definers valid.
        with self.e.hosting.paused(slot):
            previous = self.e.hosting.dump_database(slot, site['database_name'])
            try:
                self.client(slot, credentials, payload, maximum=SQL_LIMIT)
            except Exception:
                self.disconnect(slot, username)
                self.e.hosting.replace_database(slot, site['database_name'], previous)
                raise
            finally:
                # SQL can change its own password. Reassert the private credential
                # and terminate outstanding client queries before PHP resumes.
                self.e.hosting.sql(slot, "ALTER USER '%s'@'localhost' IDENTIFIED BY '%s';" % (username, password))
                self.disconnect(slot, username)
        return {}
