import base64
import json
import secrets
import unittest
from unittest.mock import patch

from test_boundaries import BoundaryTests as Fixture
from vectorcp.core import Fault
from vectorcp.databases import grant_pattern, identifier, literal, privileges


class DatabaseBoundaries(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call
    refused = Fixture.refused

    def enable(self):
        self.engine.hosting.enabled = True
        with self.engine.db() as db:
            db.execute('UPDATE users SET hosting_slot=1 WHERE id=?', (self.alice['user']['id'],))
            db.execute('UPDATE sites SET database_name=? WHERE id=?', ('site_%d' % self.a_site, self.a_site))
        folder = self.engine.state / 'hosting'
        folder.mkdir(exist_ok=True)
        (folder / ('database-%d.json' % self.a_site)).write_text(json.dumps({'name': 'site_%d' % self.a_site, 'username': 'site_%d' % self.a_site, 'password': secrets.token_urlsafe(32)}))

    def test_every_operation_checks_ownership_and_csrf(self):
        from vectorcp.databases import OPERATIONS, READ_ONLY
        for method in OPERATIONS:
            self.refused(404, lambda: self.call(self.bob, method, {'site_id': self.a_site}))
            if method not in READ_ONLY:
                self.refused(403, lambda: self.call(self.alice, method, {'site_id': self.a_site}, csrf='forged'))

    def test_sql_identifier_literal_and_privilege_allowlist(self):
        self.assertEqual(identifier('a`b'), '`a``b`')
        self.assertEqual(grant_pattern('site_1'), 'site\\_1')
        self.assertNotIn("'", literal("bad';DROP USER root;"))
        for value in ([], ['SUPER'], ['SELECT,FILE'], ['SELECT', {}], 'SELECT'):
            with self.assertRaises(Fault):
                privileges(value)
        self.assertEqual(privileges(['SELECT', 'SELECT', 'INSERT']), ['SELECT', 'INSERT'])

    def test_existing_application_user_cannot_be_changed(self):
        self.enable()
        with patch.object(self.engine.hosting, 'start_db'):
            for method in ('databases.users.grants', 'databases.users.delete', 'databases.users.rotate'):
                self.refused(404, lambda: self.call(self.alice, method, {'site_id': self.a_site, 'username': 'site_%d' % self.a_site}))

    def test_user_secret_is_returned_once_and_never_in_audit_or_metadata(self):
        self.enable()
        with patch.object(self.engine.hosting, 'start_db'), patch.object(self.engine.hosting, 'sql', return_value=b'SELECT\n'):
            user = self.call(self.alice, 'databases.users.create', {'site_id': self.a_site, 'label': 'Reporting', 'privileges': ['SELECT']})
            listed = self.call(self.alice, 'databases.users', {'site_id': self.a_site})
            self.assertEqual(listed['users'][0]['privileges'], ['SELECT'])
            self.assertNotIn(user['password'], json.dumps(listed))
            self.assertNotIn(user['password'], json.dumps(self.call(self.admin, 'audit')))
            self.refused(400, lambda: self.call(self.alice, 'databases.users.delete', {'site_id': self.a_site, 'username': user['username'], 'confirm': 'wrong'}))

    def test_import_validates_size_and_confirmation_before_starting_job(self):
        self.enable()
        for values in ({'base64': '%%%%'}, {'base64': base64.b64encode(b'SELECT 1').decode()}, {'base64': '', 'confirm': 'site_%d' % self.a_site}):
            self.refused(400, lambda: self.call(self.alice, 'databases.import', dict(values, site_id=self.a_site)))
        with self.engine.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

    def test_failed_import_restores_previous_database_and_protected_password(self):
        self.enable()
        with self.engine.db() as db:
            site = dict(db.execute('SELECT * FROM sites WHERE id=?', (self.a_site,)).fetchone())
            owner = dict(db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone())
        from contextlib import nullcontext
        def result(slot, statement, **kwargs):
            return ('GRANT ALL PRIVILEGES ON `site\\_%d`.* TO `site_%d`@`localhost`\n' % (self.a_site, self.a_site)).encode() if statement.startswith('SHOW GRANTS') else b''
        with patch.object(self.engine.hosting, 'start_db'), patch.object(self.engine.hosting, 'paused', return_value=nullcontext()), patch.object(self.engine.hosting, 'dump_database', return_value=b'previous SQL'), patch.object(self.engine.hosting, 'sql', side_effect=result) as sql, patch.object(self.engine.databases, 'client', side_effect=Fault('Rejected SQL')), patch.object(self.engine.hosting, 'replace_database') as restore:
            with self.assertRaises(Fault):
                self.engine.databases.import_sql(site, owner, {'confirm': site['database_name'], 'base64': base64.b64encode(b'DROP TABLE example;INVALID').decode()})
            restore.assert_called_once_with('01', site['database_name'], b'previous SQL')
            self.assertTrue(any('ALTER USER' in c.args[1] for c in sql.call_args_list))

    def test_import_refuses_unexpected_global_grants_before_running_customer_sql(self):
        self.enable()
        with self.engine.db() as db:
            site=dict(db.execute('SELECT * FROM sites WHERE id=?',(self.a_site,)).fetchone())
            owner=dict(db.execute('SELECT * FROM users WHERE id=?',(site['user_id'],)).fetchone())
        with patch.object(self.engine.hosting,'start_db'), patch.object(self.engine.hosting,'sql',return_value=b'GRANT ALL PRIVILEGES ON *.* TO `unexpected`@`localhost`\n'), patch.object(self.engine.databases,'client') as client, patch.object(self.engine.hosting,'dump_database') as dump:
            with self.assertRaisesRegex(Fault,'unexpected grants'):
                self.engine.databases.import_sql(site,owner,{'confirm':site['database_name'],'base64':base64.b64encode(b'SELECT 1;').decode()})
            client.assert_not_called()
            dump.assert_not_called()


del Fixture
