import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vectorcp.core import Engine, Fault
from vectorcp.dns import DNS, OPERATIONS, READ_ONLY
from vectorcp.dns_profile import configuration, load, profile, stored


class ProfileRules(unittest.TestCase):
    def test_incomplete_profile_recovery_has_a_distinct_owner_exit_status(self):
        from vectorcp.dns_profile import main, RecoveryRequired
        with patch('sys.argv', ['dns_profile', '--private']), patch('vectorcp.dns_profile.apply', side_effect=RecoveryRequired('Recovery required', 503)), patch('sys.stderr'):
            with self.assertRaises(SystemExit) as caught: main()
        self.assertEqual(caught.exception.code, 75)

    def test_explicit_interfaces_and_authoritative_acl(self):
        p = profile({'mode': 'public', 'nameservers': ['NS1.Example.net.', 'ns2.example.net'],
                     'listen': ['192.0.2.2', '2001:db8::2', '192.0.2.2']})
        self.assertEqual(p['nameservers'], ['ns1.example.net', 'ns2.example.net'])
        self.assertEqual(p['ipv4'], ['127.0.0.1', '192.0.2.2'])
        self.assertEqual(profile(stored(p)), p)
        rendered = configuration(p)
        for rule in ('recursion no;', 'allow-recursion { none; };', 'allow-query-cache { none; };',
                     'allow-transfer { none; };', 'allow-update { none; };', 'allow-query { any; };'):
            self.assertIn(rule, rendered)
        self.assertIn('listen-on-v6 port 53 { 2001:db8::2; };', rendered)
        self.assertNotIn('allow-query { any; };', configuration(profile({'mode': 'private'})))

    def test_configuration_injection_and_ambiguous_addresses_refused(self):
        good = {'mode': 'public', 'nameservers': ['ns1.example.net', 'ns2.example.net'], 'listen': ['192.0.2.2']}
        for changes in ({'nameservers': ['ns1.example.net']}, {'nameservers': ['ns1.example.net'] * 2},
                        {'nameservers': ['ns1.example.net;};', 'ns2.example.net']},
                        {'listen': ['0.0.0.0']}, {'listen': ['::']}, {'listen': ['127.0.0.1']},
                        {'listen': ['224.0.0.1']}, {'listen': ['fe80::1%eth0']}, {'listen': '192.0.2.2'},
                        {'mode': 'invalid'}, {'listen': [None]}):
            with self.subTest(changes=changes), self.assertRaises(Fault):
                profile(dict(good, **changes))

    def test_profile_file_refuses_symlink_and_untrusted_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'installed.json'
            path.write_text('{"mode":"private"}')
            path.chmod(0o666)
            with self.assertRaises(Fault): load(path)
            link = Path(tmp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(Fault): load(link, development=True)
            path.write_text('invalid JSON')
            with self.assertRaises(Fault): load(path, development=True)


class PublicDNSBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.e = Engine(self.root / 'state', self.root / 'sites', development=True)
        self.admin = self.e.bootstrap({'username': 'owner', 'name': 'Owner', 'password': 'long-private-password', 'setup_token': self.e.setup_token()})
        self.call(self.admin, 'accounts.create', {'username': 'alice', 'name': 'Alice', 'password': 'long-private-password'})
        self.alice = self.e.login({'username': 'alice', 'password': 'long-private-password'})
        self.site = self.call(self.alice, 'sites.create', {'domain': 'alice.example.com'})['id']
        self.other = self.call(self.admin, 'sites.create', {'domain': 'owner.example.com'})['id']
        self.set_profile(['ns1.hosting.example', 'ns2.hosting.example'])
        self.call(self.alice, 'dns.create', {'site_id': self.site})

    def tearDown(self): self.tmp.cleanup()

    def call(self, who, method, data=None, **kw):
        return self.e.dispatch(dict({'method': method, 'data': data or {}, 'token': who['token'], 'csrf': who['csrf']}, **kw))

    def set_profile(self, names):
        self.e.dns.config.mkdir(exist_ok=True)
        path = self.e.dns.config / 'installed.json'
        path.write_text(json.dumps({'mode': 'public', 'nameservers': names, 'listen': ['192.0.2.2']}))
        path.chmod(0o600)

    def state(self): return self.call(self.alice, 'dns.list', {'site_id': self.site})

    def change(self, method, **values):
        return self.call(self.alice, method, dict(site_id=self.site, serial=self.state()['zone']['serial'], **values))

    def activate(self):
        with patch.object(self.e.dns, 'ownership', return_value=True):
            return self.change('dns.activate', confirm_domain='alice.example.com')

    def test_drafts_excluded_until_fresh_verification_and_explicit_activation(self):
        zone = self.state()['zone']
        self.assertEqual(zone['published'], 0)
        include = self.e.dns.config / 'zones.conf'
        self.assertNotIn('alice.example.com', include.read_text())
        self.assertNotIn('_vectorcp 300 IN TXT', self.call(self.alice, 'dns.export', {'site_id': self.site})['content'])
        with patch.object(self.e.dns, 'ownership', return_value=False), self.assertRaises(Fault):
            self.change('dns.activate', confirm_domain='alice.example.com')
        self.assertEqual(self.state()['zone'], zone)
        with patch.object(self.e.dns, 'ownership', return_value=True) as verify:
            self.change('dns.activate', confirm_domain='alice.example.com')
            verify.assert_called_once_with('alice.example.com', zone['challenge'])
        self.assertEqual(self.state()['zone']['published'], 1)
        self.assertIn('alice.example.com', include.read_text())
        self.assertIn('_vectorcp 300 IN TXT ' + json.dumps(zone['challenge']), self.call(self.alice, 'dns.export', {'site_id': self.site})['content'])
        self.change('dns.deactivate', confirm_domain='alice.example.com')
        self.assertNotIn('alice.example.com', include.read_text())
        self.assertTrue(self.state()['records'])

    def test_wrong_confirmation_stale_serial_and_private_mode_refused(self):
        before = self.state()
        with self.assertRaises(Fault): self.change('dns.activate', confirm_domain='wrong.example.com')
        with self.assertRaises(Fault):
            self.call(self.alice, 'dns.activate', {'site_id': self.site, 'serial': before['zone']['serial'] - 1, 'confirm_domain': before['domain']})
        (self.e.dns.config / 'installed.json').write_text('{"mode":"private"}')
        with self.assertRaises(Fault): self.change('dns.activate', confirm_domain='alice.example.com')
        self.assertEqual(self.state()['zone']['published'], 0)

    def test_public_hosting_can_be_stopped_after_server_ip_marker_loss(self):
        self.activate()
        with patch.object(Engine, 'public_ipv4', new=property(lambda self: None)):
            self.change('dns.deactivate', confirm_domain='alice.example.com')
            self.assertEqual(self.state()['zone']['published'], 0)
            (self.e.dns.config / 'installed.json').write_text('{"mode":"private"}')
            with self.assertRaises(Fault) as caught: self.call(self.alice, 'dns.export', {'site_id': self.site})
            self.assertEqual(caught.exception.status, 409)

    def test_in_zone_nameservers_keep_their_addresses_while_active(self):
        self.set_profile(['ns1.alice.example.com', 'ns2.hosting.example'])
        with self.assertRaises(Fault): self.activate()
        self.change('dns.save', name='ns1', type='A', value='192.0.2.2')
        self.activate()
        record = next(r for r in self.state()['records'] if r['name'] == 'ns1')
        with self.assertRaises(Fault): self.change('dns.delete', id=record['id'])
        with self.assertRaises(Fault): self.change('dns.update', id=record['id'], name='other', type='A', value='192.0.2.2')
        self.assertIn(record, self.state()['records'])
        exported = self.call(self.alice, 'dns.export', {'site_id': self.site})['content']
        self.assertIn('@ IN NS ns1.alice.example.com.', exported)
        self.assertNotIn('ns1 IN A 127.0.0.1', exported)

    def test_failed_publication_preserves_state_records_and_unrelated_files(self):
        self.call(self.admin, 'dns.create', {'site_id': self.other})
        target = self.e.dns.zones / ('site-%d.zone' % self.site)
        other = self.e.dns.zones / ('site-%d.zone' % self.other)
        old_target, old_other = target.read_bytes(), other.read_bytes()
        old_state = self.state()
        original = self.e.dns.write
        counter = []
        def fail(path, content):
            counter.append(path)
            if len(counter) == 2: raise Fault('Injected config write failure', 503)
            return original(path, content)
        with patch.object(self.e.dns, 'write', side_effect=fail), self.assertRaises(Fault): self.activate()
        expected_serial=(old_state['zone']['serial']+2)%4294967296
        expected_target=old_target.replace(str(old_state['zone']['serial']).encode(),str(expected_serial).encode(),1)
        old_state['zone']['serial']=expected_serial
        self.assertEqual(self.state(), old_state)
        self.assertEqual(target.read_bytes(), expected_target)
        self.assertEqual(other.read_bytes(), old_other)

    def test_record_edit_duplicate_conflict_and_stale_form(self):
        self.change('dns.save', name='www', type='A', value='192.0.2.1')
        self.change('dns.save', name='mail', type='A', value='192.0.2.2')
        before = self.state()
        record = next(r for r in before['records'] if r['name'] == 'www')
        self.change('dns.update', id=record['id'], name='www', type='CNAME', value='alice.example.com', ttl=600)
        with self.assertRaises(Fault):
            self.call(self.alice, 'dns.update', {'site_id': self.site, 'serial': before['zone']['serial'], 'id': record['id'], 'name': 'www', 'type': 'A', 'value': '192.0.2.3'})
        with self.assertRaises(Fault): self.change('dns.update', id=record['id'], name='mail', type='CNAME', value='alice.example.com')
        with self.assertRaises(Fault): self.change('dns.save', name='_vectorcp', type='TXT', value='spoof')
        self.assertEqual(next(r for r in self.state()['records'] if r['id'] == record['id'])['type'], 'CNAME')

    def test_new_operations_enforce_ownership_csrf_and_allowlists(self):
        from vectorcp.web import OPERATIONS as WEB_OPERATIONS
        for method in OPERATIONS:
            self.assertIn(method, WEB_OPERATIONS)
            with self.subTest(method=method), self.assertRaises(Fault) as caught:
                self.call(self.alice, method, {'site_id': self.other})
            self.assertEqual(caught.exception.status, 404)
            if method not in READ_ONLY:
                with self.assertRaises(Fault) as caught: self.call(self.alice, method, {'site_id': self.site}, csrf='forged')
                self.assertEqual(caught.exception.status, 403)

    def test_busy_locked_and_plan_disabled_accounts_cannot_change_zones(self):
        with self.e.db() as db:
            db.execute("INSERT INTO jobs(id,user_id,action,status,message,created,updated) VALUES('busy',?,'test','running','test',1,1)", (self.alice['user']['id'],))
        with self.assertRaises(Fault): self.change('dns.rebuild')
        with self.e.db() as db:
            db.execute("DELETE FROM jobs WHERE id='busy'")
            db.execute('UPDATE users SET active=0 WHERE id=?', (self.alice['user']['id'],))
        with self.assertRaises(Fault): self.call(self.admin, 'dns.rebuild', {'site_id': self.site, 'serial': self.state_serial()})
        with self.e.db() as db: db.execute('UPDATE users SET active=1 WHERE id=?', (self.alice['user']['id'],))
        plan = self.call(self.admin, 'plans.create', {'name': 'No DNS', 'kind': 'customer', 'storage_mb': 512, 'site_limit': 3, 'allow_dns': False})['id']
        self.call(self.admin, 'plans.assign', {'id': self.alice['user']['id'], 'plan_id': plan})
        for method in ('dns.save', 'dns.activate', 'dns.verify', 'dns.diagnostics', 'dns.rebuild'):
            with self.subTest(method=method), self.assertRaises(Fault) as caught:
                self.call(self.alice, method, {'site_id': self.site})
            self.assertEqual(caught.exception.status, 403)

    def state_serial(self):
        with self.e.db() as db: return db.execute('SELECT serial FROM dns_zones WHERE site_id=?', (self.site,)).fetchone()[0]

    def test_ownership_requires_both_resolvers_and_failure_is_closed(self):
        challenge = self.state()['zone']['challenge']
        for answers, expected in (([json.dumps(challenge), json.dumps(challenge)], True),
                                  ([json.dumps(challenge), '"wrong"'], False),
                                  ([Fault('timeout'), json.dumps(challenge)], False)):
            with self.subTest(expected=expected), patch.object(self.e, 'development', False), patch.object(self.e.dns, 'run', side_effect=answers) as run:
                self.assertEqual(self.e.dns.ownership('alice.example.com', challenge), expected)
                self.assertEqual([c.args[0][1] for c in run.call_args_list], ['@1.1.1.1', '@8.8.8.8'])

    def test_probe_rejects_foreign_soa_and_reports_transport_and_authority(self):
        answer = ';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n;; flags: qr aa; QUERY: 1\nalice.example.com. 300 IN SOA ns1.example.net. hostmaster.example.net. 123 1 2 3 4\n'
        with patch.object(self.e.dns, 'run', return_value=answer):
            self.assertEqual(self.e.dns.probe('alice.example.com', True), {'transport': 'TCP', 'status': 'NOERROR', 'authoritative': True, 'serial': 123})
            self.assertIsNone(self.e.dns.probe('other.example.com')['serial'])

    def test_native_mutations_share_the_owner_profile_lock(self):
        import fcntl
        import builtins
        native_open = builtins.open
        lock_path = self.root / 'profile.lock'
        with native_open(lock_path, 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def redirected(path, *args, **kw):
                self.assertEqual(path, '/var/lib/vectorcp/profile-maintenance.lock')
                return native_open(lock_path, *args, **kw)
            with patch.object(self.e, 'development', False), patch('builtins.open', side_effect=redirected), patch.object(self.e.dns, 'operation') as operation:
                with self.assertRaises(Fault) as caught: self.e.dns.dispatch(None, None, 'dns.rebuild', {})
                self.assertEqual(caught.exception.status, 409)
                operation.assert_not_called()

    def test_serial_wrap_and_additive_migration_leave_zones_unpublished(self):
        with self.e.db() as db: db.execute('UPDATE dns_zones SET serial=4294967295 WHERE site_id=?', (self.site,))
        self.change('dns.rebuild')
        self.assertEqual(self.state_serial(), 0)
        with self.e.db() as db:
            db.execute('DROP TABLE dns_records')
            db.execute('DROP TABLE dns_zones')
            db.execute('CREATE TABLE dns_zones(site_id INTEGER PRIMARY KEY REFERENCES sites(id), serial INTEGER NOT NULL, challenge TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, checked INTEGER, created INTEGER NOT NULL)')
            db.execute("INSERT INTO dns_zones VALUES(?,123,'existing-token',1,10,1)", (self.site,))
        DNS(self.e)
        with self.e.db() as db:
            row = db.execute('SELECT * FROM dns_zones').fetchone()
            self.assertEqual((row['serial'], row['challenge'], row['verified'], row['published']), (123, 'existing-token', 1, 0))


if __name__ == '__main__': unittest.main()
