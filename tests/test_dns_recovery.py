import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch, PropertyMock

from test_dns import DNSBoundaries as Fixture
from vectorcp.core import Engine, Fault
from vectorcp.dns_recovery import parse


class Interrupted(BaseException):
    """Simulate process loss, bypassing ordinary exception recovery."""


class DNSRecoveryTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call

    def state(self):
        return self.call(self.alice, 'dns.list', {'site_id': self.site})

    def create(self):
        self.call(self.alice, 'dns.create', {'site_id': self.site})

    def change(self, method, **values):
        return self.call(self.alice, method, dict(site_id=self.site,
            serial=self.state()['zone']['serial'] if self.state()['zone'] else None, **values))

    def snapshot(self):
        return self.change('dns.snapshot.create')['id']

    def records(self):
        return sorted((r['name'],r['type'],r['ttl'],r['value']) for r in self.state()['records'])

    def refused(self, status, method, **values):
        with self.assertRaises(Fault) as caught:
            self.change(method, **values)
        self.assertEqual(caught.exception.status, status)

    def restart(self):
        self.e = Engine(self.e.state, self.e.sites, development=True)

    def test_record_snapshot_roundtrip_and_integrity_include_all_supported_types(self):
        self.create()
        for i,(typ,value) in enumerate([('AAAA','2001:db8::1'),('MX','10 mail.example.com'),
            ('NS','ns.example.com'),('TXT','quoted "text" </script> & \\'),
            ('CAA','0 issue "letsencrypt.org; policy=\\"test\\""'),
            ('SRV','1 0 443 target.example.com'),('CNAME','target.example.com')]):
            self.change('dns.save',name='r'+str(i),type=typ,value=value,ttl=600)
        original = self.records()
        ident = self.snapshot()
        exported = self.change('dns.snapshot.export',id=ident)
        self.assertEqual(hashlib.sha256(exported['content'].encode()).hexdigest(),exported['sha256'])
        payload=json.loads(exported['content'])
        self.assertNotIn('challenge',payload)
        self.assertNotIn('published',payload)
        self.assertNotIn('site_id',payload)
        self.change('dns.save',name='changed',type='A',value='192.0.2.77',ttl=600)
        old_challenge=self.state()['zone']['challenge']
        self.change('dns.snapshot.restore',id=ident,confirm_domain='alice.example.com')
        self.assertEqual(self.records(),original)
        self.assertEqual(self.state()['zone']['published'],0)
        self.assertEqual(self.state()['zone']['verified'],0)
        self.assertNotEqual(self.state()['zone']['challenge'],old_challenge)
        self.assertEqual(len(self.state()['snapshots']),2)
        self.assertFalse(self.e.dns.recovery.pending.exists())

    def test_removed_zone_has_recovery_copy_and_restore_preserves_serial_history(self):
        self.create()
        self.call(self.admin,'dns.create',{'site_id':self.other})
        other=self.e.dns.zones/('site-%d.zone'%self.other)
        unrelated=other.read_bytes()
        original=self.records();serial=self.state()['zone']['serial']
        self.change('dns.zone.delete',confirm_domain='alice.example.com')
        state=self.state()
        self.assertIsNone(state['zone'])
        self.assertEqual(state['records'],[])
        self.assertFalse((self.e.dns.zones/('site-%d.zone'%self.site)).exists())
        self.assertNotIn('alice.example.com',(self.e.dns.config/'zones.conf').read_text())
        ident=state['snapshots'][0]['id']
        self.restart()
        self.change('dns.snapshot.restore',id=ident,confirm_domain='alice.example.com')
        self.assertEqual(self.records(),original)
        self.assertEqual(self.state()['zone']['serial'],(serial+1)%4294967296)
        self.assertEqual(other.read_bytes(),unrelated)

    def test_public_zone_must_be_stopped_and_restore_never_reactivates_it(self):
        self.create();ident=self.snapshot()
        profile=self.e.dns.config/'installed.json'
        profile.write_text(json.dumps({'mode':'public','nameservers':['ns1.hosting.example','ns2.hosting.example'],'listen':['192.0.2.2']}))
        profile.chmod(0o600)
        with patch.object(self.e.dns,'ownership',return_value=True):
            self.change('dns.activate',confirm_domain='alice.example.com')
        self.refused(409,'dns.snapshot.restore',id=ident,confirm_domain='alice.example.com')
        self.refused(409,'dns.zone.delete',confirm_domain='alice.example.com')
        self.assertEqual(len(self.state()['snapshots']),1)
        self.change('dns.deactivate',confirm_domain='alice.example.com')
        self.change('dns.snapshot.restore',id=ident,confirm_domain='alice.example.com')
        self.assertEqual(self.state()['zone']['published'],0)
        self.assertEqual(self.state()['zone']['verified'],0)
        self.assertNotIn('alice.example.com',(self.e.dns.config/'zones.conf').read_text())

    def test_full_snapshot_storage_does_not_discard_copies_or_change_records(self):
        self.create();ids=[self.snapshot() for _ in range(5)]
        self.change('dns.save',name='keep',type='A',value='192.0.2.1')
        before=self.state()
        self.refused(409,'dns.snapshot.create')
        self.refused(409,'dns.snapshot.restore',id=ids[0],confirm_domain='alice.example.com')
        self.refused(409,'dns.zone.delete',confirm_domain='alice.example.com')
        self.assertEqual(self.state(),before)

    def test_cross_site_snapshot_access_and_forged_csrf_are_rejected(self):
        self.create();ident=self.snapshot()
        for method in ('dns.snapshot.export','dns.snapshot.restore','dns.snapshot.delete'):
            with self.subTest(method=method),self.assertRaises(Fault) as caught:
                self.call(self.admin,method,{'site_id':self.other,'id':ident,'confirm_domain':'owner.example.com'})
            self.assertEqual(caught.exception.status,404)
        for method in ('dns.snapshot.create','dns.snapshot.import','dns.snapshot.restore','dns.snapshot.delete','dns.zone.delete','dns.recover'):
            with self.subTest(method=method),self.assertRaises(Fault) as caught:
                self.call(self.alice,method,{'site_id':self.site},csrf='forged')
            self.assertEqual(caught.exception.status,403)

    def test_snapshot_removal_requires_confirmation_and_never_changes_current_records(self):
        self.create();ident=self.snapshot();before=self.records()
        self.refused(409,'dns.snapshot.delete',id=ident,confirm_domain='wrong.example.com')
        self.change('dns.snapshot.delete',id=ident,confirm_domain='alice.example.com')
        self.assertEqual(self.state()['snapshots'],[])
        self.assertEqual(self.records(),before)

    def test_stale_restore_and_changed_absence_are_rejected(self):
        self.create();ident=self.snapshot();serial=self.state()['zone']['serial']
        self.change('dns.save',name='latest',type='A',value='192.0.2.1')
        before=self.state()
        with self.assertRaises(Fault) as caught:
            self.call(self.alice,'dns.snapshot.restore',{'site_id':self.site,'serial':serial,'id':ident,'confirm_domain':'alice.example.com'})
        self.assertEqual(caught.exception.status,409)
        self.assertEqual(self.state(),before)

    def test_import_is_scoped_validated_and_does_not_restore_until_requested(self):
        self.create();ident=self.snapshot()
        payload=self.change('dns.snapshot.export',id=ident)['content']
        before=self.records();imported=self.change('dns.snapshot.import',content=payload)
        self.assertEqual(imported['records'],len(before))
        self.assertEqual(self.records(),before)
        self.refused(400,'dns.snapshot.import')
        self.refused(400,'dns.snapshot.import',content='x'*262145)
        bad=json.loads(payload);bad['domain']='foreign.example.com'
        self.refused(409,'dns.snapshot.import',content=json.dumps(bad))
        for records in ([{'name':'_vectorcp','type':'TXT','value':'stolen-proof','ttl':300}],
                        [{'name':'bad;','type':'A','value':'192.0.2.1','ttl':300}],
                        [{'name':'same','type':'A','value':'192.0.2.1','ttl':300}]*2,
                        [{'name':'same','type':'A','value':'192.0.2.1','ttl':300},
                         {'name':'same','type':'CNAME','value':'target.example.com','ttl':300}]):
            bad=json.loads(payload);bad['records']=records
            with self.subTest(records=records),self.assertRaises(Fault):parse(json.dumps(bad),'alice.example.com')

    def test_corrupt_snapshot_is_not_exported_or_restored(self):
        self.create();ident=self.snapshot()
        with self.e.db() as db:db.execute("UPDATE dns_snapshots SET payload='{}' WHERE id=?",(ident,))
        self.refused(409,'dns.snapshot.export',id=ident)
        self.refused(409,'dns.snapshot.restore',id=ident,confirm_domain='alice.example.com')

    def test_crash_before_commit_rebuilds_old_records_on_restart_with_new_serial(self):
        self.create();before=self.records();serial=self.state()['zone']['serial']
        with patch.object(self.e.dns,'commit',side_effect=Interrupted):
            with self.assertRaises(Interrupted):self.change('dns.save',name='uncommitted',type='A',value='192.0.2.3')
        self.assertTrue(self.e.dns.recovery.pending.exists())
        self.assertIn('uncommitted',(self.e.dns.zones/('site-%d.zone'%self.site)).read_text())
        self.restart()
        self.assertEqual(self.records(),before)
        self.assertEqual(self.state()['zone']['serial'],(serial+2)%4294967296)
        self.assertNotIn('uncommitted',(self.e.dns.zones/('site-%d.zone'%self.site)).read_text())
        self.assertFalse(self.e.dns.recovery.pending.exists())

    def test_crash_after_commit_keeps_new_records_and_rebuilds_on_restart(self):
        self.create();serial=self.state()['zone']['serial']
        with patch.object(self.e.dns.recovery,'clear',side_effect=Interrupted):
            with self.assertRaises(Interrupted):self.change('dns.save',name='committed',type='A',value='192.0.2.4')
        self.restart()
        self.assertIn('committed',[r['name'] for r in self.state()['records']])
        self.assertEqual(self.state()['zone']['serial'],(serial+2)%4294967296)
        self.assertFalse(self.state()['recovery_required'])

    def test_failed_repair_blocks_more_edits_until_owner_recovers(self):
        self.create();before=self.records()
        with patch.object(self.e.dns,'write',side_effect=Fault('Injected persistent storage failure',503)):
            self.refused(503,'dns.save',name='not-saved',type='A',value='192.0.2.1')
        self.assertTrue(self.state()['recovery_required'])
        self.refused(503,'dns.save',name='blocked',type='A',value='192.0.2.2')
        self.refused(403,'dns.recover',confirm_domain='alice.example.com')
        self.call(self.admin,'dns.recover',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(self.records(),before)
        self.assertFalse(self.state()['recovery_required'])

    def test_recovery_serial_wrap_is_forward_not_a_regression(self):
        self.create()
        with self.e.db() as db:db.execute('UPDATE dns_zones SET serial=4294967295 WHERE site_id=?',(self.site,))
        with patch.object(self.e.dns,'commit',side_effect=Interrupted):
            with self.assertRaises(Interrupted):self.change('dns.save',name='uncommitted',type='A',value='192.0.2.3')
        self.restart()
        self.assertEqual(self.state()['zone']['serial'],1)

    def test_untrusted_marker_is_retained_and_not_followed(self):
        self.create();outside=self.root/'outside';outside.write_text('private marker')
        self.e.dns.recovery.pending.symlink_to(outside)
        self.refused(503,'dns.save',name='blocked',type='A',value='192.0.2.1')
        with self.assertRaises(Fault):self.call(self.admin,'dns.recover',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(outside.read_text(),'private marker')
        self.assertTrue(self.e.dns.recovery.pending.is_symlink())

    def test_owner_repair_rebuilds_missing_zones_and_quarantines_corrupt_and_orphan_files(self):
        self.create()
        self.call(self.admin,'dns.create',{'site_id':self.other})
        original=self.records();serial=self.state()['zone']['serial']
        target=self.e.dns.zones/('site-%d.zone'%self.site)
        broken=b'\xff manually damaged zone\n';target.write_bytes(broken)
        other=self.e.dns.zones/('site-%d.zone'%self.other);other.unlink()
        orphan=self.e.dns.zones/'site-999.zone';orphan.write_text('unreferenced zone')
        result=self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(result['zones'],2);self.assertEqual(result['quarantined'],2)
        retained=self.e.state/'dns-quarantine'/result['quarantine_id']
        self.assertEqual((retained/target.name).read_bytes(),broken)
        self.assertEqual((retained/orphan.name).read_text(),'unreferenced zone')
        self.assertTrue(other.exists());self.assertFalse(orphan.exists())
        self.assertEqual(self.records(),original)
        self.assertEqual(self.state()['zone']['serial'],serial+1)
        self.assertFalse(self.state()['recovery_required'])
        # A second repair is idempotent and consumes no quarantine directory.
        again=self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(again['quarantined'],0)
        self.assertEqual(self.state()['zone']['serial'],serial+1)

    def test_repair_is_owner_only_and_checks_confirmation(self):
        self.create()
        self.refused(403,'dns.repair',confirm_domain='alice.example.com')
        with self.assertRaises(Fault) as caught:
            self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'wrong.example.com'})
        self.assertEqual(caught.exception.status,409)
        self.assertFalse(self.state()['recovery_required'])
        with self.e.db() as db:db.execute('UPDATE users SET active=0 WHERE username=?',('alice',))
        result=self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertTrue(result['ok'])

    def test_unsafe_zone_file_is_preserved_and_keeps_repair_checkpoint(self):
        self.create();outside=self.root/'outside-zone';outside.write_text('keep this')
        target=self.e.dns.zones/('site-%d.zone'%self.site);target.unlink();target.symlink_to(outside)
        with self.assertRaises(Fault) as caught:
            self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(caught.exception.status,503)
        self.assertTrue(target.is_symlink());self.assertEqual(outside.read_text(),'keep this')
        self.assertTrue(self.state()['recovery_required'])

    def test_quarantine_capacity_keeps_existing_files_and_pending_checkpoint(self):
        self.create();root=self.e.state/'dns-quarantine';root.mkdir(mode=0o700)
        for i in range(8):(root/str(i)).mkdir()
        orphan=self.e.dns.zones/'site-999.zone';orphan.write_text('retain me')
        with self.assertRaises(Fault):
            self.call(self.admin,'dns.repair',{'site_id':self.site,'confirm_domain':'alice.example.com'})
        self.assertEqual(orphan.read_text(),'retain me')
        self.assertTrue(self.state()['recovery_required'])
        self.assertEqual(len(list(root.iterdir())),8)

    def test_full_record_name_is_validated_before_publication(self):
        self.create();before=self.state()
        name='.'.join(['a'*63]*3+['b'*50])
        self.refused(400,'dns.save',name=name,type='A',value='192.0.2.1')
        self.assertEqual(self.state(),before)
        value={'format':'vectorcp-dns-records','version':1,'domain':'alice.example.com',
               'created':1,'source_serial':1,'records':[{'name':name,'type':'A','ttl':300,'value':'192.0.2.1'}]}
        with self.assertRaises(Fault):parse(json.dumps(value),'alice.example.com')

    def test_identical_quarantine_is_reused_during_repeated_recovery(self):
        self.create();orphan=self.e.dns.zones/'site-999.zone';orphan.write_text('same orphan')
        first=self.e.dns.recovery.quarantine([orphan])
        self.assertEqual(self.e.dns.recovery.quarantine([orphan]),first)
        self.assertEqual(len(list((self.e.state/'dns-quarantine').iterdir())),1)
        self.assertEqual(orphan.read_text(),'same orphan')

    def test_started_service_retries_transient_probe_failure(self):
        self.create();serial=self.state()['zone']['serial']
        ready={'authoritative':True,'serial':serial}
        self.e.development=False
        try:
            with patch.object(type(self.e.dns),'profile',new_callable=PropertyMock,return_value={'mode':'private'}),\
                 patch.object(type(self.e),'public_ipv4',new_callable=PropertyMock,return_value='127.0.0.1'),\
                 patch.object(self.e.dns,'run') as run,patch.object(self.e.dns,'write'),\
                 patch.object(self.e.dns,'probe',side_effect=[Fault('Not ready',503),ready,ready]) as probe:
                with self.e.db() as db:result=self.e.dns.repair_all(db)
            self.assertEqual(result['zones'],1);self.assertEqual(probe.call_count,3)
            self.assertIn((['/usr/bin/systemctl','reload-or-restart','vectorcp-dns'],),[c.args for c in run.call_args_list])
        finally:
            self.e.development=True


del Fixture
