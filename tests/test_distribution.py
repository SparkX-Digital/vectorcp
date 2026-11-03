import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from veyra.core import Engine, Fault


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.e = Engine(self.root/'state', self.root/'sites', development=True)
        self.password = secrets.token_urlsafe(24)
        self.admin = self.e.bootstrap({'setup_token': self.e.setup_token(), 'username': 'owner', 'name': 'Owner', 'password': self.password})
        self.rplan = self.plan(self.admin, 'Reseller', kind='reseller', storage_mb=2048, site_limit=4, customer_limit=2)
        self.rid = self.customer(self.admin, 'reseller', plan_id=self.rplan, role='reseller')
        self.reseller = self.e.login({'username':'reseller', 'password':self.password})
        self.cplan = self.plan(self.reseller, 'Starter', storage_mb=1024, site_limit=2)
        self.cid = self.customer(self.reseller, 'client', plan_id=self.cplan)
        self.client = self.e.login({'username':'client', 'password':self.password})
        self.sid = self.call(self.reseller, 'sites.create', {'domain':'client.example.com','user_id':self.cid})['id']
        self.other_id = self.customer(self.admin, 'unrelated', storage_mb=1024)
        self.other = self.e.login({'username':'unrelated','password':self.password})
        self.other_site = self.call(self.other, 'sites.create', {'domain':'unrelated.example.com'})['id']

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, who, method, data=None, **extra):
        return self.e.dispatch(dict({'token':who['token'],'csrf':who['csrf'],'method':method,'data':data or {}}, **extra))

    def plan(self, who, name, **extra):
        return self.call(who,'plans.create',dict({'name':name,'kind':'customer','storage_mb':512,'site_limit':1,'customer_limit':0},**extra))['id']

    def customer(self, who, username, **extra):
        return self.call(who,'accounts.create',dict({'username':username,'name':username.title(),'password':self.password},**extra))['id']

    def denied(self, status, fn):
        with self.assertRaises(Fault) as caught:
            fn()
        self.assertEqual(caught.exception.status,status)

    def test_scope_covers_sites_files_databases_backups_jobs_and_audit(self):
        backup=self.call(self.other,'backups.create',{'site_id':self.other_site})['id']
        with self.e.db() as db:
            db.execute("INSERT INTO jobs VALUES('unrelatedjob',?,?,?,'complete','Done',1,1)",(self.other_id,self.other_site,'hosting.php'))
            db.execute("UPDATE sites SET database_name='private_db' WHERE id=?",(self.other_site,))
        self.assertEqual([a['id'] for a in self.call(self.reseller,'accounts.list')['accounts']],[self.cid])
        self.assertEqual([s['id'] for s in self.call(self.reseller,'sites.list')['sites']],[self.sid])
        self.assertEqual(self.call(self.reseller,'jobs.list')['jobs'],[])
        self.assertEqual(self.call(self.reseller,'databases.list')['databases'],[])
        self.assertEqual(self.call(self.reseller,'backups.list')['backups'],[])
        self.assertFalse(any('unrelated' in str(x) for x in self.call(self.reseller,'audit')['events']))
        for method,data in [('files.read',{'site_id':self.other_site,'path':'index.html'}),('databases.credentials',{'site_id':self.other_site}),('backups.describe',{'id':backup}),('backups.chunk',{'id':backup,'offset':0}),('backups.delete',{'id':backup}),('backups.download',{'id':backup})]:
            with self.subTest(method=method): self.denied(404,lambda:self.call(self.reseller,method,data))
        self.assertIn('ready',self.call(self.reseller,'files.read',{'site_id':self.sid,'path':'index.html'})['content'])

    def test_reservations_include_locked_customers_and_reject_overallocation(self):
        self.customer(self.reseller,'second',plan_id=self.cplan)
        self.call(self.reseller,'accounts.active',{'id':self.cid,'active':False})
        self.denied(409,lambda:self.customer(self.reseller,'third',plan_id=self.cplan))
        pool=self.call(self.reseller,'plans.list')['pool']
        self.assertEqual((pool['customers'],pool['storage_mb'],pool['sites']),(2,2048,4))

    def test_owner_holds_and_locks_cannot_be_reversed_by_reseller(self):
        self.call(self.admin,'sites.active',{'site_id':self.sid,'active':False})
        self.denied(403,lambda:self.call(self.reseller,'sites.active',{'site_id':self.sid,'active':True}))
        self.call(self.admin,'accounts.active',{'id':self.cid,'active':False})
        self.denied(403,lambda:self.call(self.reseller,'accounts.active',{'id':self.cid,'active':True}))
        self.call(self.admin,'accounts.active',{'id':self.cid,'active':True})
        self.call(self.reseller,'accounts.active',{'id':self.cid,'active':False})
        self.call(self.reseller,'accounts.active',{'id':self.cid,'active':True})

    def test_reseller_lock_revokes_child_and_parent_sessions_and_logins(self):
        self.call(self.admin,'accounts.active',{'id':self.rid,'active':False})
        for who in (self.reseller,self.client): self.denied(401,lambda:self.call(who,'overview'))
        for username in ('client','reseller'): self.denied(401,lambda:self.e.login({'username':username,'password':self.password}))
        self.assertEqual(self.call(self.admin,'sites.list')['sites'][0]['status'],'active')

    def test_role_and_owner_forgery_cannot_escape_delegation(self):
        self.denied(404,lambda:self.call(self.reseller,'sites.create',{'domain':'stolen.example.com','user_id':self.other_id}))
        self.denied(404,lambda:self.call(self.reseller,'accounts.active',{'id':self.other_id,'active':False}))
        self.denied(403,lambda:self.customer(self.reseller,'nested',role='reseller',plan_id=self.rplan))
        self.denied(403,lambda:self.customer(self.reseller,'forged',plan_id=self.rplan))
        self.denied(403,lambda:self.call(self.client,'plans.create',{'name':'forged'}))
        self.denied(400,lambda:self.customer(self.reseller,'noplan',site_limit=100,storage_mb=10000))
        self.denied(404,lambda:self.call(self.reseller,'sites.create',{'domain':'self.example.com'}))

    def test_immutable_plan_assignment_checks_usage_and_fixed_volume(self):
        small=self.plan(self.reseller,'Tiny',storage_mb=512,site_limit=1)
        with self.e.db() as db: db.execute('UPDATE users SET hosting_slot=2 WHERE id=?',(self.cid,))
        self.denied(409,lambda:self.call(self.reseller,'plans.assign',{'id':self.cid,'plan_id':small}))
        with self.e.db() as db: db.execute('UPDATE users SET hosting_slot=NULL WHERE id=?',(self.cid,))
        self.call(self.reseller,'plans.assign',{'id':self.cid,'plan_id':small})
        self.denied(409,lambda:self.call(self.client,'sites.create',{'domain':'extra.example.com'}))
        self.call(self.reseller,'plans.active',{'id':small,'active':False})
        self.denied(403,lambda:self.customer(self.reseller,'retired',plan_id=small))
        self.assertEqual(self.call(self.client,'overview')['user']['plan_id'],small)

    def test_feature_checks_are_enforced_on_jobs_and_cannot_be_escalated(self):
        static=self.plan(self.reseller,'Static',storage_mb=1024,site_limit=2,allow_php=False,allow_wordpress=False,allow_databases=False,allow_tls=False)
        self.call(self.reseller,'plans.assign',{'id':self.cid,'plan_id':static})
        with self.e.db() as db: db.execute('UPDATE users SET hosting_slot=2 WHERE id=?',(self.cid,))
        with patch.object(self.e.hosting,'enabled',True):
            for method in ('hosting.php','hosting.wordpress','hosting.tls','databases.create'):
                self.denied(403,lambda:self.call(self.client,method,{'site_id':self.sid}))
            self.denied(409,lambda:self.call(self.reseller,'hosting.enable',{'id':self.cid,'storage_mb':4096}))
        noapps=self.plan(self.admin,'Static reseller',kind='reseller',storage_mb=2048,site_limit=4,customer_limit=2,allow_php=False,allow_wordpress=False,allow_databases=False)
        self.denied(409,lambda:self.call(self.admin,'plans.assign',{'id':self.rid,'plan_id':noapps}))

    def test_owner_global_pool_prevents_overselling_without_charging_children_twice(self):
        self.customer(self.admin,'large',storage_mb=10240)
        self.denied(409,lambda:self.customer(self.admin,'too_large',storage_mb=4096))
        # A child consumes the already reserved reseller pool, not the host pool again.
        self.customer(self.reseller,'fits',plan_id=self.cplan)

    def test_a_second_reseller_and_its_customers_are_outside_scope(self):
        other_id=self.customer(self.admin,'other_reseller',role='reseller',plan_id=self.rplan)
        other=self.e.login({'username':'other_reseller','password':self.password})
        plan=self.plan(other,'Own starter')
        client=self.customer(other,'other_client',plan_id=plan)
        site=self.call(other,'sites.create',{'user_id':client,'domain':'other-client.example.com'})['id']
        self.denied(404,lambda:self.call(self.reseller,'files.read',{'site_id':site,'path':'index.html'}))
        self.denied(404,lambda:self.call(self.reseller,'accounts.active',{'id':client,'active':False}))
        self.denied(404,lambda:self.call(self.reseller,'accounts.active',{'id':other_id,'active':False}))
        self.assertEqual([a['id'] for a in self.call(self.reseller,'accounts.list')['accounts']],[self.cid])
        self.assertEqual([s['id'] for s in self.call(self.reseller,'sites.list')['sites']],[self.sid])

    def test_role_entry_does_not_grant_a_different_role(self):
        self.denied(403,lambda:self.e.login({'username':'client','password':self.password,'entry':'admin'}))
        r=self.e.login({'username':'reseller','password':self.password,'entry':'reseller'})
        self.assertEqual(r['user']['role'],'reseller')

    def test_plan_mutations_require_csrf(self):
        for method in ('plans.create','plans.active','plans.assign'):
            self.denied(403,lambda:self.call(self.reseller,method,{},csrf='forged'))

    def test_customer_sessions_expose_effective_role_and_preserve_existing_accounts(self):
        self.assertEqual(self.reseller['user']['role'],'reseller')
        self.assertEqual(self.client['user']['role'],'customer')
        self.assertIsNone(self.other['user']['parent_id'])
        self.assertEqual(self.call(self.reseller,'overview')['counts']['sites'],1)


if __name__=='__main__': unittest.main()
