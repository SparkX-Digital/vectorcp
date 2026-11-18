import json
import os
import unittest
from unittest.mock import patch

from test_boundaries import BoundaryTests as Fixture
from vectorcp.core import Engine, Fault


class RoutingTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call
    refused = Fixture.refused

    def rule(self, path='/old/', target='https://destination.example/new/', **options):
        return dict(dict(path=path, match='prefix', target=target, code=301, keep_query=True,
                         append_path=True), **options)

    def save(self, **changes):
        data={'site_id':self.a_site,'revision':0,'force_https':True,'redirects':[], 'error_pages':{}}
        data.update(changes)
        return self.call(self.alice,'sites.routing.save',data)

    def native_config(self):
        nginx=self.root/'nginx';nginx.mkdir(exist_ok=True)
        self.engine.nginx=nginx;self.engine.development=False
        with self.engine.db() as db:
            site=dict(db.execute('SELECT * FROM sites WHERE id=?',(self.a_site,)).fetchone())
        return nginx/('vectorcp-site-%d.conf'%self.a_site),site

    def test_ownership_csrf_and_account_lock_cover_routing(self):
        for method in ('sites.routing.get','sites.routing.save'):
            self.refused(404,lambda:self.call(self.bob,method,{'site_id':self.a_site}))
        self.refused(403,lambda:self.call(self.alice,'sites.routing.save',{'site_id':self.a_site},csrf='forged'))
        self.call(self.admin,'accounts.active',{'id':self.alice['user']['id'],'active':False})
        self.refused(401,lambda:self.call(self.alice,'sites.routing.get',{'site_id':self.a_site}))

    def test_defaults_migration_and_restart_preserve_sessions_and_rules(self):
        original=self.call(self.alice,'sites.routing.get',{'site_id':self.a_site})
        self.assertEqual(original['revision'],0);self.assertTrue(original['force_https'])
        self.save(redirects=[self.rule()])
        self.engine=Engine(self.engine.state,self.engine.sites,development=True)
        saved=self.call(self.alice,'sites.routing.get',{'site_id':self.a_site})
        self.assertEqual(saved['redirects'],[self.rule()]);self.assertEqual(saved['revision'],1)

    def test_stale_settings_and_suspension_preserve_current_rules(self):
        self.save(redirects=[self.rule()])
        self.refused(409,lambda:self.save(force_https=False))
        self.call(self.admin,'sites.active',{'site_id':self.a_site,'active':False})
        self.refused(409,lambda:self.save(revision=1))
        self.assertFalse(self.call(self.alice,'sites.routing.get',{'site_id':self.a_site})['editable'])

    def test_redirect_injection_urls_and_resource_bounds(self):
        for target in ['javascript:alert(1)','https://user:pass@example.com/',
                       'https://example.com/;return 200;','https://example.com/$host',
                       'https://example.com/%0d%0aX:yes','https://example.com/%ZZ',
                       'https://example.com/#fragment','https://example.com/"']:
            self.refused(400,lambda:self.save(redirects=[self.rule(target=target)]))
        for path in ['/../x/','/.hidden/','/bad path/','/a?b/','/_vectorcp_error/404/']:
            self.refused(400,lambda:self.save(redirects=[self.rule(path=path)]))
        self.refused(400,lambda:self.save(redirects=[self.rule()]*21))
        self.refused(400,lambda:self.save(redirects=[self.rule(code=True)]))
        self.refused(400,lambda:self.save(redirects=[self.rule(code=303)]))
        self.refused(400,lambda:self.save(redirects=[self.rule(target='https://example.com/new/?')]))

    def test_duplicate_rules_and_same_site_cycles_are_rejected(self):
        self.refused(400,lambda:self.save(redirects=[self.rule(),self.rule()]))
        self.refused(400,lambda:self.save(redirects=[self.rule(target='https://alice.example.com/old/new/')]))
        rules=[self.rule('/a','https://alice.example.com/b',match='exact',append_path=False),
               self.rule('/b','https://alice.example.com/a',match='exact',append_path=False)]
        self.refused(400,lambda:self.save(redirects=rules))

    def test_static_error_files_are_owned_regular_html_and_bounded(self):
        root=self.engine.site_root({'id':self.a_site,'user_id':self.alice['user']['id']})
        (root/'404.html').write_text('<h1>Missing</h1>')
        (root/'link.html').symlink_to(self.root/'sites'/str(self.b_site)/'public/index.html')
        (root/'empty.html').touch();(root/'large.html').write_bytes(b'x'*262145)
        for path,status in [('link.html',409),('../index.html',400),('index.php',400),
                            ('missing.html',409),('empty.html',400),('large.html',400)]:
            self.refused(status,lambda:self.save(error_pages={'404':path}))
        self.refused(400,lambda:self.save(error_pages={'200':'404.html'}))
        self.save(error_pages={'404':'404.html'})

    def test_failed_nginx_test_restores_config_and_database_revision(self):
        path,site=self.native_config();path.write_bytes(b'previous-vhost')
        def fail(argv):
            if argv==['/usr/sbin/nginx','-t'] and path.read_bytes()!=b'previous-vhost':
                raise Fault('Injected validation failure',503)
            return ''
        with patch('vectorcp.core.run_fixed',side_effect=fail):
            self.refused(503,lambda:self.save(redirects=[self.rule()]))
        self.assertEqual(path.read_bytes(),b'previous-vhost')
        self.assertEqual(self.call(self.alice,'sites.routing.get',{'site_id':self.a_site})['revision'],0)

    def test_failed_reload_restores_previous_vhost(self):
        path,site=self.native_config();path.write_bytes(b'previous-vhost')
        def fail(argv):
            if 'reload' in argv and path.read_bytes()!=b'previous-vhost':raise Fault('Injected reload failure',503)
            return ''
        with patch('vectorcp.core.run_fixed',side_effect=fail):
            self.refused(503,lambda:self.save(redirects=[self.rule()]))
        self.assertEqual(path.read_bytes(),b'previous-vhost')

    def test_https_toggle_keeps_certificate_and_acme_route(self):
        path,site=self.native_config()
        with self.engine.db() as db:db.execute('UPDATE sites SET tls=1 WHERE id=?',(self.a_site,))
        with patch('vectorcp.core.run_fixed',return_value=''):
            self.save(force_https=False)
        text=path.read_text();self.assertIn('listen 443 ssl;',text)
        self.assertIn('ssl_certificate ',text);self.assertNotIn('return 308 https://alice.example.com',text)
        self.assertIn('location ^~ /.well-known/acme-challenge/',text)
        with patch('vectorcp.core.run_fixed',return_value=''):
            self.save(revision=1,force_https=True)
        self.assertIn('return 308 https://alice.example.com$request_uri;',path.read_text())

    def test_maps_use_raw_uri_and_custom_errors_do_not_execute_php(self):
        path,site=self.native_config()
        root=self.engine.site_root(site);(root/'404.html').write_text('Not found')
        with patch('vectorcp.core.run_fixed',return_value=''):
            self.save(redirects=[self.rule()],error_pages={'404':'404.html'})
        text=path.read_text();self.assertIn('map $request_uri',text)
        self.assertIn('internal; disable_symlinks on; types { } default_type text/html; try_files /404.html =404;',text)
        with patch('vectorcp.core.run_fixed',return_value=''):
            self.engine.publish_config(site,'suspended')
        self.assertNotIn('destination.example',path.read_text());self.assertNotIn('error_page 404',path.read_text())


del Fixture
