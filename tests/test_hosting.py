import io
import tarfile
import time
import unittest
from unittest.mock import patch
from test_boundaries import BoundaryTests as Fixture
from vectorcp.core import Fault
from vectorcp.hosting import safe_members

class HostingBoundaries(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call
    refused = Fixture.refused

    def test_hosting_operations_require_isolation_and_owner(self):
        self.engine.hosting.enabled = True
        for method in ('hosting.php','hosting.wordpress','hosting.tls','databases.create','backups.full'):
            self.refused(404, lambda: self.call(self.alice, method, {'site_id':self.b_site}))
            self.refused(409, lambda: self.call(self.alice, method, {'site_id':self.a_site}))
        self.refused(403, lambda: self.call(self.alice,'hosting.enable',{'id':self.alice['user']['id']}))

    def test_job_history_and_database_credentials_are_owned(self):
        now=int(time.time())
        with self.engine.db() as db:
            db.execute("INSERT INTO jobs VALUES('test',?,?,'hosting.php','complete','Done',?,?)",(self.alice['user']['id'],self.a_site,now,now))
        self.assertEqual(len(self.call(self.alice,'jobs.list')['jobs']),1)
        self.assertEqual(self.call(self.bob,'jobs.list')['jobs'],[])
        self.refused(404, lambda: self.call(self.bob,'databases.credentials',{'site_id':self.a_site}))

    def test_jobs_block_concurrent_customer_mutations(self):
        with self.engine.db() as db:
            db.execute("INSERT INTO jobs VALUES('busy',?,?,'backups.full','running','Busy',1,1)",(self.alice['user']['id'],self.a_site))
        self.refused(409, lambda: self.call(self.alice,'files.write',{'site_id':self.a_site,'path':'new.txt','content':'x','revision':'new'}))
        self.refused(409, lambda: self.call(self.alice,'sites.create',{'domain':'new.example.com'}))
        self.call(self.bob,'files.list',{'site_id':self.b_site})

    def test_backup_stream_and_deletion_require_ownership(self):
        backup=self.call(self.alice,'backups.create',{'site_id':self.a_site})['id']
        for method in ('backups.describe','backups.chunk','backups.delete'):
            self.refused(404, lambda: self.call(self.bob,method,{'id':backup,'offset':0}))
        self.refused(400, lambda: self.call(self.alice,'backups.chunk',{'id':'../../control','offset':0}))
        self.refused(400, lambda: self.call(self.alice,'backups.chunk',{'id':backup,'offset':-1}))
        self.assertGreater(self.call(self.alice,'backups.describe',{'id':backup})['bytes'],0)
        self.call(self.alice,'backups.delete',{'id':backup})
        self.refused(404, lambda: self.call(self.alice,'backups.describe',{'id':backup}))

    def test_additive_migration_preserves_existing_sessions(self):
        with self.engine.db() as db:
            self.assertIn('runtime',{r[1] for r in db.execute('PRAGMA table_info(sites)')})
        self.assertEqual(self.call(self.alice,'overview')['user']['username'],'alice')
        self.assertEqual(self.call(self.alice,'sites.list')['sites'][0]['runtime'],'static')

    def test_nginx_blocks_php_source_and_upload_execution(self):
        nginx=self.root/'nginx';nginx.mkdir()
        self.engine.nginx=nginx;self.engine.development=False
        with patch('vectorcp.core.run_fixed',return_value=''):
            self.engine.publish_config({'id':self.a_site,'user_id':self.alice['user']['id'],'domain':'alice.example.com'},'active')
        config=next(nginx.iterdir()).read_text()
        for required in ('location ~* \\.(php[0-9]*)','^/wp-content/uploads/','^/wp-config','disable_symlinks on'):
            self.assertIn(required,config)

del Fixture

class ArchiveSafetyTests(unittest.TestCase):
    def archive(self,name,kind=tarfile.REGTYPE):
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as archive:
            member=tarfile.TarInfo(name);member.type=kind;archive.addfile(member)
        output.seek(0)
        return tarfile.open(fileobj=output,mode='r:')

    def test_rejects_links_traversal_devices_and_other_roots(self):
        for name,kind in [('bundle/../secret',tarfile.REGTYPE),('/bundle/file',tarfile.REGTYPE),('elsewhere/file',tarfile.REGTYPE),('bundle/link',tarfile.SYMTYPE),('bundle/hard',tarfile.LNKTYPE),('bundle/device',tarfile.CHRTYPE),('bundle/.hidden',tarfile.REGTYPE)]:
            with self.subTest(name=name,kind=kind),self.archive(name,kind) as archive:
                with self.assertRaises(Fault):safe_members(archive,'bundle')

    def test_accepts_only_bounded_regular_content(self):
        with self.archive('bundle/public/index.php') as archive:
            members,total=safe_members(archive,'bundle')
            self.assertEqual(len(members),1);self.assertEqual(total,0)
