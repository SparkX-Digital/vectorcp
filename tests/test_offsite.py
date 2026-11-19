import json
import os
import secrets
import unittest
from unittest.mock import patch

from test_boundaries import BoundaryTests as Fixture
from vectorcp.core import Fault


class OffsiteTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call
    refused = Fixture.refused

    def config(self, **changes):
        directory = self.engine.state/'offsite'
        directory.mkdir(exist_ok=True, mode=0o700)
        key, hosts = directory/'key', directory/'known_hosts'
        key.write_text('private fixture'); key.chmod(0o600)
        hosts.write_text('pinned fixture'); hosts.chmod(0o600)
        d = dict(id='remote', label='Remote archive', host='127.0.0.1', port=2222, user='archive', path='/backups', key=str(key), known_hosts=str(hosts))
        d.update(changes)
        p = directory/'destinations.json'
        p.write_text(json.dumps([d])); p.chmod(0o600)
        return d

    def copy(self):
        bid, cid = secrets.token_hex(12), secrets.token_hex(12)
        with self.engine.db() as db:
            db.execute('INSERT INTO offsite_copies VALUES(?,?,?,?,?,?,?,?,?)', (cid, bid, self.a_site, self.alice['user']['id'], 'alice.example.com', 4, '0'*64, 'remote', 1))
        return bid, cid

    def test_destination_paths_are_owner_controlled_and_secrets_not_exposed(self):
        d = self.config()
        result = self.call(self.alice, 'backups.destinations')
        self.assertEqual(result, {'destinations': [{'id': 'remote', 'label': 'Remote archive'}]})
        self.assertNotIn(d['key'], json.dumps(result))
        for changes in ({'path': '/backup/../../etc'}, {'host': '-oProxyCommand=bad'}, {'user': 'root;exec'}, {'port': True}):
            self.config(**changes)
            self.refused(409, lambda: self.call(self.admin, 'backups.destinations'))
        d=self.config()
        os.chmod(d['key'], 0o644)
        self.refused(409, lambda: self.call(self.admin, 'backups.destinations'))

    def test_remote_inventory_and_jobs_are_owned(self):
        _, cid=self.copy()
        self.assertEqual(len(self.call(self.alice, 'backups.offsite.list')['copies']), 1)
        self.assertEqual(self.call(self.bob, 'backups.offsite.list')['copies'], [])
        self.refused(404, lambda: self.call(self.bob, 'backups.offsite.fetch', {'id': cid}))
        self.refused(403, lambda: self.call(self.alice, 'backups.offsite.fetch', {'id': cid}, csrf='forged'))

    def test_hash_mismatch_never_overwrites_existing_local_archive(self):
        self.config()
        bid,cid=self.copy()
        target=self.engine.backups/(bid+'.tar.gz')
        target.write_bytes(b'previous')
        def corrupt(destination, lines, folder):
            from pathlib import Path
            (Path(folder)/'incoming.tar.gz').write_bytes(b'evil')
        with self.engine.db() as db:
            site=dict(db.execute('SELECT * FROM sites WHERE id=?',(self.a_site,)).fetchone())
            owner=dict(db.execute('SELECT * FROM users WHERE id=?',(site['user_id'],)).fetchone())
        with patch.object(self.engine.offsite, 'transfer', side_effect=corrupt):
            with self.assertRaises(Fault):
                self.engine.offsite.fetch(cid,site,owner)
        self.assertEqual(target.read_bytes(),b'previous')

    def test_failed_sftp_is_not_recorded_as_verified(self):
        self.config()
        bid=secrets.token_hex(12)
        (self.engine.backups/(bid+'.tar.gz')).write_bytes(b'fixture')
        with self.engine.db() as db:
            db.execute("INSERT INTO backups VALUES(?,?,?,?,?,?,'full')",(bid,self.alice['user']['id'],self.a_site,'alice.example.com',7,1))
        with patch.object(self.engine.offsite,'transfer',side_effect=Fault('Failed')):
            with self.assertRaises(Fault):
                self.engine.offsite.send(bid,'remote')
        self.assertEqual(self.call(self.alice,'backups.offsite.list')['copies'],[])
        self.assertTrue((self.engine.backups/(bid+'.tar.gz')).exists())


del Fixture
