import base64
import contextlib
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from test_boundaries import BoundaryTests as Fixture
from vectorcp.core import Engine, Fault
from vectorcp import transfer_format as fmt


def manifest(payload=b'Private website\n', domain='transfer.example.com', database=None):
    return {'format':'vectorcp-account','version':1,'account':{'username':'source','name':'Source'},'sites':[
        {'domain':domain,'runtime':'static','wordpress_version':None,
         'files':{'index.html':{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}},
         'directories':['empty','.well-known'],'database':database,'dns':None,
         'routing':{'redirects':[],'error_pages':{}},'schedule':None}]}


def make_archive(value=None,payload=b'Private website\n',extra=None,manifest_bytes=None):
    value=value or manifest(payload)
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for index,site in enumerate(value['sites']):
            for directory in site['directories']:
                item=tarfile.TarInfo('account/sites/%d/public/%s'%(index,directory));item.type=tarfile.DIRTYPE
                archive.addfile(item)
            for name in site['files']:fmt.add_bytes(archive,'account/sites/%d/public/%s'%(index,name),payload)
            if site['database']:fmt.add_bytes(archive,'account/sites/%d/database.sql'%index,SQL)
        fmt.add_bytes(archive,'account/manifest.json',manifest_bytes or json.dumps(value).encode())
        if extra:extra(archive)
    return gzip.compress(raw.getvalue())


SQL=b'CREATE TABLE example (id INT); INSERT INTO example VALUES (3);'


class FormatTests(unittest.TestCase):
    def check(self,payload):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'archive.tar.gz';path.write_bytes(payload)
            with fmt.opened(path,folder) as (archive,value):return value

    def test_verified_format_retains_empty_and_hidden_folders(self):
        self.assertEqual(self.check(make_archive()),manifest())

    def test_missing_extra_duplicate_and_corrupt_members_rejected(self):
        extras=[lambda a:fmt.add_bytes(a,'extra',b'x'),lambda a:fmt.add_bytes(a,'account/sites/0/public/index.html',b'x')]
        for extra in extras:
            with self.assertRaises(Fault):self.check(make_archive(extra=extra))
        value=manifest();value['sites'][0]['files']['index.html']['sha256']='0'*64
        with self.assertRaises(Fault):self.check(make_archive(value))

    def test_links_extended_headers_and_traversal_rejected(self):
        def link(archive):
            item=tarfile.TarInfo('link');item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd';archive.addfile(item)
        with self.assertRaises(Fault):self.check(make_archive(extra=link))
        for path in ('../escape','/etc/passwd','a//b','a/./b','a\\b','a\x00b'):
            with self.assertRaises(Fault):fmt.path_name(path)
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w',format=tarfile.PAX_FORMAT) as archive:
            item=tarfile.TarInfo('x');item.pax_headers={'comment':'extended'};archive.addfile(item)
        with self.assertRaises(Fault):self.check(gzip.compress(raw.getvalue()))

    def test_gzip_truncation_trailing_members_and_expansion_bounded(self):
        archive=make_archive()
        for value in (archive[:-1],archive+b'junk',archive+archive,b'not gzip'):
            with self.assertRaises(Fault):self.check(value)
        with patch.object(fmt,'MAX_ARCHIVE',1024),self.assertRaises(Fault):self.check(archive)

    def test_strict_manifest_types_duplicate_keys_and_inventory_budget(self):
        for change in (lambda v:v.update(password='never accepted'),lambda v:v['sites'][0].update(wordpress_version=6),lambda v:v['sites'][0].update(directories=['empty','empty'])):
            value=manifest();change(value)
            with self.assertRaises(Fault):self.check(make_archive(value))
        raw=json.dumps(manifest()).replace('"version": 1','"version": 1, "version": 1').encode()
        with self.assertRaises(Fault):self.check(make_archive(manifest_bytes=raw))
        value=manifest();value['sites'].append(copy.deepcopy(value['sites'][0]));value['sites'][1]['domain']='second.example.com'
        with patch.object(fmt,'MAX_FILES',4),self.assertRaises(Fault):fmt.metadata(value)


class TransferTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    call=Fixture.call
    refused=Fixture.refused

    def prepare(self):
        result=self.call(self.admin,'accounts.create',{'username':'destination','name':'Destination','password':self.password,'storage_mb':512,'site_limit':5})
        with self.engine.db() as db:self.target=dict(db.execute("SELECT * FROM users WHERE username='destination'").fetchone())
        self.scope=patch.object(self.engine.hosting,'slot',return_value='01');self.scope.start();self.addCleanup(self.scope.stop)
        self.pause=patch.object(self.engine.hosting,'paused',side_effect=lambda slot:contextlib.nullcontext());self.pause.start();self.addCleanup(self.pause.stop)
        # Jobs still pass the real queue/worker, synchronously for deterministic
        # assertions, with separate committed database connections.
        class Immediate:
            def __init__(self,target,args,**kw):self.target=target;self.args=args
            def start(self):self.target(*self.args)
        self.thread=patch('vectorcp.transfers.threading.Thread',Immediate);self.thread.start();self.addCleanup(self.thread.stop)

    def upload(self,archive=None):
        archive=archive or make_archive();sha=hashlib.sha256(archive).hexdigest()
        ident=self.call(self.admin,'transfers.upload.start',{'bytes':len(archive),'sha256':sha})['id']
        chunk={'id':ident,'offset':0,'base64':base64.b64encode(archive).decode()}
        self.call(self.admin,'transfers.upload.chunk',chunk)
        self.call(self.admin,'transfers.upload.finish',{'id':ident})
        return ident,sha

    def inspect(self,ident):
        self.call(self.admin,'transfers.inspect',{'id':ident,'user_id':self.target['id']})
        return self.call(self.admin,'transfers.get',{'id':ident})

    def run_import(self,ident,sha):
        self.call(self.admin,'transfers.import',{'id':ident,'user_id':self.target['id'],'confirm_username':'destination','sha256':sha})
        return self.call(self.admin,'transfers.get',{'id':ident})

    def test_scope_csrf_and_upload_resume_exact_retry(self):
        self.refused(403,lambda:self.call(self.alice,'transfers.list'))
        self.refused(403,lambda:self.call(self.admin,'transfers.upload.start',{},csrf='forged'))
        payload=make_archive();sha=hashlib.sha256(payload).hexdigest()
        ident=self.call(self.admin,'transfers.upload.start',{'bytes':len(payload),'sha256':sha})['id']
        chunk={'id':ident,'offset':0,'base64':base64.b64encode(payload[:100]).decode()}
        self.assertEqual(self.call(self.admin,'transfers.upload.chunk',chunk)['received'],100)
        self.assertEqual(self.call(self.admin,'transfers.upload.chunk',chunk)['received'],100)
        self.refused(409,lambda:self.call(self.admin,'transfers.upload.chunk',dict(chunk,base64=base64.b64encode(b'x'*100).decode())))
        self.refused(409,lambda:self.call(self.admin,'transfers.upload.finish',{'id':ident}))
        self.assertEqual(self.call(self.admin,'transfers.upload.status',{'id':ident})['received'],100)

    def test_import_is_suspended_and_preserves_accounts_and_unrelated_data(self):
        self.prepare();before=(self.root/'sites'/str(self.a_site)/'public/index.html').read_bytes()
        with self.engine.db() as db:account=dict(db.execute('SELECT * FROM users WHERE id=?',(self.target['id'],)).fetchone())
        ident,sha=self.upload();self.assertEqual(self.inspect(ident)['status'],'ready')
        self.assertEqual(self.run_import(ident,sha)['status'],'complete')
        with self.engine.db() as db:
            site=dict(db.execute('SELECT * FROM sites WHERE user_id=?',(self.target['id'],)).fetchone())
            self.assertEqual(dict(db.execute('SELECT * FROM users WHERE id=?',(self.target['id'],)).fetchone()),account)
            self.assertEqual(db.execute('SELECT force_https FROM site_routing WHERE site_id=?',(site['id'],)).fetchone()[0],0)
        self.assertEqual((site['status'],site['tls'],site['admin_hold']),('suspended',0,1))
        root=self.engine.site_root(site);self.assertEqual((root/'index.html').read_bytes(),b'Private website\n');self.assertTrue((root/'empty').is_dir())
        self.assertEqual((self.root/'sites'/str(self.a_site)/'public/index.html').read_bytes(),before)
        self.refused(409,lambda:self.call(self.admin,'transfers.inspect',{'id':ident,'user_id':self.target['id']}))

    def test_conflict_preflight_and_changed_destination_never_overwritten(self):
        self.prepare();ident,sha=self.upload(make_archive(manifest(domain='alice.example.com')))
        self.assertEqual(self.inspect(ident)['status'],'blocked')
        self.assertIn('Domain already exists',self.call(self.admin,'transfers.get',{'id':ident})['report']['conflicts'][0])
        self.call(self.admin,'transfers.delete',{'id':ident})
        ident,sha=self.upload();self.inspect(ident)
        self.call(self.admin,'sites.create',{'domain':'existing.example.com','user_id':self.target['id']})
        self.refused(409,lambda:self.run_import(ident,sha))

    def test_failure_rolls_back_only_new_allocations_and_keeps_archive(self):
        self.prepare();ident,sha=self.upload();self.inspect(ident)
        with patch.object(self.engine,'publish_config',side_effect=RuntimeError('injected')):
            self.assertEqual(self.run_import(ident,sha)['status'],'rolled_back')
        with self.engine.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM sites').fetchone()[0],2)
        self.assertTrue((self.engine.transfers.folder/(ident+'.tar.gz')).exists())
        self.assertEqual({p.name for p in self.engine.sites.iterdir()},{str(self.a_site),str(self.b_site)})

    def test_orphan_folder_is_preserved_and_not_claimed_for_cleanup(self):
        self.prepare();ident,sha=self.upload();self.inspect(ident)
        orphan=self.engine.sites/str(max(self.a_site,self.b_site)+1);orphan.mkdir();(orphan/'unrelated').write_text('preserve')
        self.assertEqual(self.run_import(ident,sha)['status'],'rolled_back')
        self.assertEqual((orphan/'unrelated').read_text(),'preserve')

    def test_database_uses_scoped_client_and_rejects_existing_identity(self):
        self.prepare();value=manifest(database={'bytes':len(SQL),'sha256':hashlib.sha256(SQL).hexdigest()})
        ident,sha=self.upload(make_archive(value));self.inspect(ident)
        creds={'name':'site_3','username':'site_3','password':'fresh','socket':'/private/mysql.sock'}
        with patch.object(self.engine.hosting,'start_db'),patch.object(self.engine.hosting,'sql',return_value=b'') as root_sql,patch.object(self.engine.hosting,'create_database',return_value=creds),patch.object(self.engine.databases,'client',return_value=b'') as scoped,patch.object(self.engine.databases,'disconnect'):
            self.assertEqual(self.run_import(ident,sha)['status'],'complete')
            self.assertEqual(scoped.call_args.args[2],SQL)
            self.assertTrue(all(SQL.decode() not in c.args[1] for c in root_sql.call_args_list))

    def test_existing_database_identity_is_never_dropped(self):
        self.prepare();value=manifest(database={'bytes':len(SQL),'sha256':hashlib.sha256(SQL).hexdigest()})
        ident,sha=self.upload(make_archive(value));self.inspect(ident)
        with patch.object(self.engine.hosting,'start_db'),patch.object(self.engine.hosting,'sql',return_value=b'site_3\n') as sql,patch.object(self.engine.hosting,'create_database') as create:
            self.assertEqual(self.run_import(ident,sha)['status'],'rolled_back')
            create.assert_not_called();self.assertEqual(sql.call_count,1)
            self.assertNotIn('DROP',sql.call_args.args[1])

    def test_dns_and_schedules_remain_inactive_after_import(self):
        self.prepare();value=manifest();value['sites'][0]['dns']={'format':'vectorcp-dns-records','version':1,'domain':'transfer.example.com','source_serial':12,'created':1,'records':[{'name':'@','type':'A','ttl':3600,'value':'192.0.2.10'}]}
        value['sites'][0]['schedule']={'frequency':'monthly','hour':3,'weekday':0,'monthday':31,'keep':2}
        ident,sha=self.upload(make_archive(value));self.assertEqual(self.inspect(ident)['status'],'ready')
        self.assertEqual(self.run_import(ident,sha)['status'],'complete')
        with self.engine.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM dns_zones').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM dns_snapshots').fetchone()[0],1)
            schedule=db.execute('SELECT * FROM backup_schedules').fetchone()
            self.assertEqual((schedule['enabled'],schedule['frequency'],schedule['monthday'],schedule['destination']),(0,'monthly',31,''))

    def test_managed_wordpress_settings_are_remapped_without_php_evaluation(self):
        path=self.root/'wp-config.php'
        path.write_text("<?php\n"+''.join("define('%s', 'old');\n"%key for key in ('DB_NAME','DB_USER','DB_PASSWORD','DB_HOST'))+"// kept\n")
        self.engine.transfers.remap_wordpress(path,{'name':'site_9','username':'site_9','password':'fresh_credential','socket':'/private/mysql.sock'})
        content=path.read_text();self.assertIn("define('DB_NAME', 'site_9');",content);self.assertIn('localhost:/private/mysql.sock',content);self.assertIn('// kept',content)
        path.write_text("<?php define('DB_NAME', getenv('DB_NAME')); system('never executed');")
        with self.assertRaises(Fault):self.engine.transfers.remap_wordpress(path,{'name':'site_9','username':'site_9','password':'new','socket':'/private/mysql.sock'})

    def test_reseller_transfer_scope_and_owner_locks(self):
        self.prepare()
        plan=self.call(self.admin,'plans.create',{'name':'Reseller','kind':'reseller','storage_mb':2048,'site_limit':10,'customer_limit':2})['id']
        rid=self.call(self.admin,'accounts.create',{'username':'reseller','name':'Reseller','password':self.password,'role':'reseller','plan_id':plan})['id']
        reseller=self.engine.login({'username':'reseller','password':self.password})
        self.refused(404,lambda:self.call(reseller,'transfers.export',{'user_id':self.alice['user']['id'],'confirm_username':'alice'}))
        ident,sha=self.upload()
        self.refused(404,lambda:self.call(reseller,'transfers.get',{'id':ident}))
        with self.engine.db() as db:db.execute('UPDATE users SET parent_id=?,admin_lock=1,active=0 WHERE id=?',(rid,self.alice['user']['id']))
        self.refused(409,lambda:self.call(reseller,'transfers.export',{'user_id':self.alice['user']['id'],'confirm_username':'alice'}))

    def test_interrupted_import_holds_customer_until_explicit_owner_recovery(self):
        self.prepare();ident,sha=self.upload();self.inspect(ident)
        class Crash(BaseException):pass
        with patch.object(self.engine,'publish_config',side_effect=Crash):
            with self.assertRaises(Crash):self.run_import(ident,sha)
        self.engine=Engine(self.engine.state,self.engine.sites,development=True)
        with patch.object(self.engine.hosting,'slot',return_value='01'),patch.object(self.engine.hosting,'paused',side_effect=lambda slot:contextlib.nullcontext()):
            row=self.call(self.admin,'transfers.get',{'id':ident});self.assertEqual(row['status'],'needs_inspection');self.assertTrue(row['recoverable'])
            self.refused(409,lambda:self.call(self.admin,'sites.create',{'domain':'not-now.example.com','user_id':self.target['id']}))
            self.refused(409,lambda:self.call(self.admin,'transfers.delete',{'id':ident}))
            self.call(self.admin,'transfers.rollback',{'id':ident,'confirm_username':'destination'})
            self.assertEqual(self.call(self.admin,'transfers.get',{'id':ident})['status'],'rolled_back')

    def test_export_is_checksummed_scoped_and_round_trips(self):
        self.prepare()
        result=self.call(self.admin,'transfers.export',{'user_id':self.alice['user']['id'],'confirm_username':'alice'})
        row=self.call(self.admin,'transfers.get',{'id':result['id']});self.assertEqual(row['status'],'complete')
        info=self.call(self.admin,'transfers.describe',{'id':row['id']})
        data=base64.b64decode(self.call(self.admin,'transfers.chunk',{'id':row['id'],'offset':0})['base64'])
        self.assertEqual(hashlib.sha256(data).hexdigest(),info['sha256'])
        with fmt.opened(self.engine.transfers.folder/(row['id']+'.tar.gz'),self.engine.transfers.folder) as (_,value):self.assertEqual(value['account']['username'],'alice')

    def test_export_pause_checkpoint_survives_restart_and_preserves_source(self):
        self.prepare();ident,sha=self.upload()
        with self.engine.db() as db:
            db.execute("UPDATE transfers SET user_id=?,direction='export',status='exporting',journal=? WHERE id=?",(self.alice['user']['id'],json.dumps({'pause':{'slot':'01','restore':True}}),ident))
        self.engine=Engine(self.engine.state,self.engine.sites,development=True)
        self.assertEqual(self.call(self.admin,'transfers.get',{'id':ident})['status'],'needs_inspection')
        self.refused(409,lambda:self.call(self.alice,'files.write',{'site_id':self.a_site,'path':'index.html','content':'blocked','revision':'new'}))
        with patch.object(self.engine.hosting,'slot',return_value='01'),patch.object(self.engine.hosting,'paused',side_effect=lambda slot:contextlib.nullcontext()),patch.object(self.engine.hosting,'start_php') as start,patch('vectorcp.hosting.command'),patch.object(self.engine.dns,'maintenance',side_effect=contextlib.nullcontext),patch.object(self.engine,'development',False):
            self.call(self.admin,'transfers.rollback',{'id':ident,'confirm_username':'alice'})
            start.assert_called_once_with('01')
        with self.engine.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sites').fetchone()[0],2)
        self.assertEqual(self.call(self.admin,'transfers.get',{'id':ident})['status'],'rolled_back')


del Fixture
