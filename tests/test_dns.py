import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from veyra.core import Engine, Fault
from veyra.dns import validate


class DNSRecords(unittest.TestCase):
    def test_types_and_escaping(self):
        for typ,value in [('A','1.2.3.4'),('AAAA','2001:db8::1'),('CNAME','target.example.com'),('MX','10 mail.example.com'),('NS','ns.example.com'),('TXT','hello "quoted"; world'),('CAA','0 issue letsencrypt.org'),('SRV','10 0 443 target.example.com')]:
            with self.subTest(typ=typ):
                r=validate({'name':'www','type':typ,'value':value})
                self.assertEqual(r['type'],typ)
        self.assertEqual(validate({'name':'*','type':'A','value':'1.2.3.4'})['name'],'*')
        self.assertEqual(validate({'name':'_sip._tcp','type':'SRV','value':'1 0 443 sip.example.com'})['name'],'_sip._tcp')
        self.assertIn('\\"',validate({'type':'TXT','value':'"; include "/etc/shadow";'})['value'])

    def test_injection_malformed_and_unbounded_data_rejected(self):
        bad=[{'name':'bad;','type':'A','value':'1.2.3.4'}, {'name':'@','type':'CNAME','value':'target.example.com'}, {'type':'MX','value':'1 bad.example.com;'}, {'type':'TXT','value':'line\nbreak'}, {'type':'AAAA','value':'1.2.3.4'}, {'type':'TXT','value':'x'*256}, {'type':'CAA','value':'0 issue bad\nline'}, {'type':'SOA','value':'anything'}, {'type':'SRV','value':'1 0 65536 target.example.com'}, {'type':'A','value':'1.2.3.4','ttl':1}]
        for data in bad:
            with self.subTest(data=data),self.assertRaises(Fault): validate(data)


class DNSBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.e=Engine(self.root/'state',self.root/'sites',development=True)
        self.admin=self.e.bootstrap({'username':'owner','name':'Owner','password':'long-private-password','setup_token':self.e.setup_token()})
        self.call(self.admin,'accounts.create',{'username':'alice','name':'Alice','password':'long-private-password'})
        self.alice=self.e.login({'username':'alice','password':'long-private-password'})
        self.site=self.call(self.alice,'sites.create',{'domain':'alice.example.com'})['id']
        self.other=self.call(self.admin,'sites.create',{'domain':'owner.example.com'})['id']

    def tearDown(self): self.tmp.cleanup()

    def call(self,who,method,data=None,**kw):
        return self.e.dispatch(dict({'method':method,'data':data or {},'token':who['token'],'csrf':who['csrf']},**kw))

    def test_editor_export_cname_conflicts_and_serials(self):
        self.call(self.alice,'dns.create',{'site_id':self.site})
        a=self.call(self.alice,'dns.list',{'site_id':self.site})
        self.assertEqual(a['mode'],'private');self.assertFalse(a['zone']['verified'])
        self.call(self.alice,'dns.save',{'site_id':self.site,'name':'www','type':'CNAME','value':'alice.example.com'})
        with self.assertRaises(Fault): self.call(self.alice,'dns.save',{'site_id':self.site,'name':'www','type':'A','value':'1.2.3.4'})
        b=self.call(self.alice,'dns.list',{'site_id':self.site})
        self.assertEqual(b['zone']['serial'],a['zone']['serial']+1)
        exported=self.call(self.alice,'dns.export',{'site_id':self.site})['content']
        self.assertIn('www 3600 IN CNAME alice.example.com.',exported)
        rid=next(r['id'] for r in b['records'] if r['name']=='www')
        self.call(self.alice,'dns.delete',{'site_id':self.site,'id':rid})
        self.assertEqual(len(self.call(self.alice,'dns.list',{'site_id':self.site})['records']),1)

    def test_ownership_and_csrf_apply_to_every_dns_operation(self):
        for method in ('dns.list','dns.create','dns.save','dns.delete','dns.export','dns.verify'):
            with self.subTest(method=method),self.assertRaises(Fault) as caught:
                self.call(self.alice,method,{'site_id':self.other})
            self.assertEqual(caught.exception.status,404)
        for method in ('dns.create','dns.save','dns.delete','dns.verify'):
            with self.assertRaises(Fault) as caught:self.call(self.alice,method,{'site_id':self.site},csrf='forged')
            self.assertEqual(caught.exception.status,403)

    def test_failed_zone_publication_rolls_back_records_and_files(self):
        self.call(self.alice,'dns.create',{'site_id':self.site})
        path=self.e.dns.zones/('site-%d.zone'%self.site)
        original=path.read_text()
        write=self.e.dns.write
        calls=[]
        def fail_config(path,payload):
            calls.append(path)
            if len(calls)==2: raise Fault('Validation failed')
            return write(path,payload)
        with patch.object(self.e.dns,'write',side_effect=fail_config):
            with self.assertRaises(Fault):self.call(self.alice,'dns.save',{'site_id':self.site,'name':'new','type':'A','value':'1.2.3.4'})
        self.assertEqual(path.read_text(),original)
        self.assertEqual(len(self.call(self.alice,'dns.list',{'site_id':self.site})['records']),1)
