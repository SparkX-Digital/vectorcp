"""Opt-in real Nginx routing checks on an already marked disposable Linux guest.

Uses its own loopback listeners/configuration, not the installed web service.
Requires root, Nginx, OpenSSL and /var/lib/vectorcp/acceptance-context.json.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vectorcp.core import Engine, Fault


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-disposable-host',action='store_true')
    args=parser.parse_args()
    marker=Path('/var/lib/vectorcp/acceptance-context.json')
    if not args.allow_disposable_host or sys.platform!='linux' or os.geteuid()!=0 or not marker.is_file():
        parser.error('Requires explicit opt-in on a marked disposable Linux guest as root')
    for port in (18080,18443):
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    checks=[]
    with tempfile.TemporaryDirectory(prefix='vectorcp-routing-check-',dir='/srv') as temporary:
        root=Path(temporary);root.chmod(0o755)
        engine=Engine(root/'state',root/'sites',root/'vhosts',development=True)
        engine.nginx.mkdir(mode=0o755)
        password=secrets.token_urlsafe(24)
        actor=engine.bootstrap({'setup_token':engine.setup_token(),'username':'routingadmin','name':'Routing QA','password':password})
        def call(method,data):return engine.dispatch({'method':method,'data':data,'token':actor['token'],'csrf':actor['csrf']})
        a=call('sites.create',{'domain':'routing.example.com'})['id']
        b=call('sites.create',{'domain':'unrelated.example.com'})['id']
        site=dict(id=a,user_id=actor['user']['id'],domain='routing.example.com',runtime='static',tls=1,status='active')
        other=dict(id=b,user_id=actor['user']['id'],domain='unrelated.example.com',runtime='static',tls=0,status='active')
        public=engine.site_root(site)
        for code in (403,404,500):(public/(str(code)+'.html')).write_text('<h1>Custom %d</h1>'%code)
        cert=root/'certs'/('vectorcp-site-%d'%a);cert.mkdir(parents=True)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=routing.example.com',
                        '-keyout',str(cert/'privkey.pem'),'-out',str(cert/'fullchain.pem')],check=True,capture_output=True)
        config=root/'nginx.conf'
        config.write_text('user nginx; worker_processes 1; pid '+str(root/'nginx.pid')+'; error_log '+str(root/'error.log')+';\n'
                          'events { worker_connections 64; } http { include /etc/nginx/mime.types; access_log off; '
                          'include '+str(engine.nginx/'*.conf')+'; }\n')
        with engine.db() as db:db.execute('UPDATE sites SET tls=1 WHERE id=?',(a,))
        engine.development=False
        daemon=None
        def fixed(argv):
            if argv==['/usr/sbin/nginx','-t']:
                for path in engine.nginx.glob('*.conf'):
                    value=path.read_text().replace('listen 80;','listen 127.0.0.1:18080;').replace('listen 443 ssl;','listen 127.0.0.1:18443 ssl;')
                    value=value.replace('/etc/letsencrypt/live/',str(root/'certs')+'/')
                    # A test-only upstream failure trigger exercises custom 500 fallback.
                    value=value.replace('server_name routing.example.com;','server_name routing.example.com; location = /native-failure { return 500; }')
                    path.write_text(value)
                result=subprocess.run(['/usr/sbin/nginx','-t','-c',str(config)],capture_output=True,text=True)
                if result.returncode:raise Fault(result.stderr,503)
            elif daemon is not None:
                os.kill(int((root/'nginx.pid').read_text()),signal.SIGHUP)
                time.sleep(.15)
            return ''
        def get(path,host='routing.example.com',tls=False):
            connection=(http.client.HTTPSConnection('127.0.0.1',18443,timeout=5,context=ssl._create_unverified_context())
                        if tls else http.client.HTTPConnection('127.0.0.1',18080,timeout=5))
            # The private fixture certificate is deliberately self-signed, not public trust evidence.
            connection.request('GET',path,headers={'Host':host})
            response=connection.getresponse();result=(response.status,dict(response.getheaders()),response.read())
            connection.close();return result
        revision=0
        def save(rules=None,pages=None,force=False):
            nonlocal revision
            result=call('sites.routing.save',{'site_id':a,'revision':revision,'force_https':force,
                       'redirects':rules or [],'error_pages':pages or {}})
            revision=result['revision']
        rules=[{'path':'/old/','match':'prefix','target':'https://target.example/new/','code':308,'keep_query':True,'append_path':True},
               {'path':'/old/specific','match':'exact','target':'https://target.example/exact?fixed=1','code':302,'keep_query':True,'append_path':False}]
        try:
            with patch('vectorcp.core.run_fixed',side_effect=fixed):
                engine.publish_config(other,'active');save(rules,{str(c):str(c)+'.html' for c in (403,404,500)})
                daemon=subprocess.Popen(['/usr/sbin/nginx','-c',str(config),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                for attempt in range(50):
                    try:
                        if get('/')[0]==200:break
                    except OSError:pass
                    if daemon.poll() is not None:raise RuntimeError(daemon.stderr.read().decode())
                    time.sleep(.1)
                assert get('/old/a%20b?x=1')[1]['Location']=='https://target.example/new/a%20b?x=1'
                checks.append('prefix_remaining_path_and_query')
                assert get('/old/specific?x=2')[1]['Location']=='https://target.example/exact?fixed=1&x=2'
                checks.append('exact_precedence_and_destination_query')
                for code,path in [(403,'/wp-config.php'),(404,'/not-present'),(500,'/native-failure')]:
                    result=get(path);assert result[0]==code and ('Custom %d'%code).encode() in result[2],result
                checks.append('custom_403_404_500_preserve_status')
                (public/'500.html').unlink();assert get('/native-failure')[0]==500
                checks.append('missing_custom_file_preserves_500')
                (public/'404.html').unlink();(public/'404.html').symlink_to(engine.site_root(other)/'index.html')
                response=get('/not-present');assert response[0]==404 and b'Your website is ready' not in response[2]
                checks.append('replacement_symlink_cannot_expose_another_site')
                (public/'404.html').unlink();(public/'404.html').write_text('<h1>Custom 404</h1>')
                result=get('/old/%0d%0aX-Injected:yes');assert 'X-Injected' not in result[1]
                assert '\r' not in result[1].get('Location','') and '\n' not in result[1].get('Location','')
                checks.append('encoded_header_control_not_decoded_in_redirect')
                save(rules,{'404':'404.html'},force=True)
                assert get('/old/file?x=3')[1]['Location']=='https://routing.example.com/old/file?x=3'
                assert get('/old/file?x=3',tls=True)[1]['Location']=='https://target.example/new/file?x=3'
                checks.append('https_preference_before_custom_rules')
                save(force=False);assert get('/')[0]==200 and get('/',tls=True)[0]==200
                checks.append('disable_force_https_keeps_both_listeners')
                call('sites.active',{'site_id':a,'active':False})
                response=get('/');assert response[0]==503 and b'Website suspended' in response[2]
                assert get('/old/file')[0]==503
                checks.append('suspension_overrides_customer_routes')
                assert get('/',host='unrelated.example.com')[0]==200
                checks.append('unrelated_virtual_host_preserved')
        finally:
            if daemon is not None:
                daemon.send_signal(signal.SIGQUIT)
                try:daemon.communicate(timeout=10)
                except subprocess.TimeoutExpired:daemon.kill();daemon.communicate()
        print(json.dumps({'checks':checks,'passed':len(checks),'real_nginx':True,
                          'scope':'Standalone loopback Nginx in a disposable Linux guest; not production installation or public TLS validation.'},indent=2))


if __name__=='__main__':main()
