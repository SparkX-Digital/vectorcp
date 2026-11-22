"""Opt-in portable transfer checks on a marked disposable AlmaLinux guest.

Creates one new isolated destination and a separate control database, simulating
another server without changing the source domains or production web listeners.
Preserves existing fixtures; no public routing, mail or full-machine restore.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vectorcp.core import Engine, Fault
from vectorcp import transfer_format as fmt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-disposable-host',required=True,action='store_true')
    parser.parse_args()
    state=Path('/var/lib/vectorcp');context=state/'acceptance-context.json'
    assert sys.platform=='linux' and os.geteuid()==0 and context.is_file()
    os.umask(0o077)
    def command(argv):return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=90).stdout.strip()
    assert command(['getenforce'])=='Enforcing'
    with socket.socket() as probe:probe.bind(('127.0.0.1',18091))
    checks=[];daemon=None;destination=None
    def passed(name):checks.append(name);print('PASS:',name,flush=True)
    def call(engine,who,method,data=None):return engine.dispatch({'method':method,'data':data or {},'token':who['token'],'csrf':who['csrf']})
    def complete(engine,job,success=True):
        for attempt in range(600):
            with engine.db() as db:row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(job['job_id'],)).fetchone())
            if row['status'] in ('complete','failed'):
                assert row['status']==('complete' if success else 'failed'),row['message'];return
            time.sleep(.25)
        raise AssertionError('Transfer job timed out')
    command(['systemctl','stop','vectorcp-agent'])
    try:
        source=Engine(state,'/srv/vectorcp/sites','/etc/nginx/conf.d')
        actor=source.login(json.loads(context.read_text())['owner_login'])
        with source.db() as db:
            owner=dict(db.execute('SELECT * FROM users WHERE hosting_slot=1').fetchone())
            original=[dict(r) for r in db.execute('SELECT * FROM sites ORDER BY id')]
        before={s['id']:fmt.checksum(source.site_root(s)/'index.php' if (source.site_root(s)/'index.php').is_file() else source.site_root(s)/'index.html') for s in original}
        with source.db() as db:previous=db.execute("SELECT id FROM transfers WHERE direction='export' AND status='complete' AND user_id=? ORDER BY created DESC LIMIT 1",(owner['id'],)).fetchone()
        if previous:exported={'id':previous['id']}
        else:
            exported=call(source,actor,'transfers.export',{'user_id':owner['id'],'confirm_username':owner['username']});complete(source,exported)
        info=call(source,actor,'transfers.describe',{'id':exported['id']})
        archive=source.transfers.folder/(exported['id']+'.tar.gz')
        assert fmt.checksum(archive)==info['sha256']
        with fmt.opened(archive,source.transfers.folder) as (_,value):manifest=value
        assert any(s['database'] for s in manifest['sites'])
        passed('real multi-site files and primary SQL export verified')

        # Provision through the real owner workflow. Keep its empty account in
        # the original database; the second control plane maps this allocation.
        suffix=secrets.token_hex(4);name='transfer_'+suffix;password=secrets.token_urlsafe(24)
        with source.db() as db:previous=db.execute("SELECT id,username FROM users WHERE username LIKE 'transfer_%' AND hosting_slot IS NULL AND NOT EXISTS(SELECT 1 FROM sites WHERE user_id=users.id) ORDER BY id LIMIT 1").fetchone()
        if previous:ident,name=previous['id'],previous['username']
        else:ident=call(source,actor,'accounts.create',{'username':name,'name':'Disposable transfer target','password':password,'site_limit':10,'storage_mb':512})['id']
        complete(source,call(source,actor,'hosting.enable',{'id':ident,'storage_mb':512}))
        with source.db() as db:allocated=dict(db.execute('SELECT * FROM users WHERE id=?',(ident,)).fetchone())
        root=state/('transfer-acceptance-'+suffix);root.mkdir(mode=0o700)
        (root/'hosting').mkdir();(root/'hosting/enabled').touch()
        vhosts=Path('/etc/nginx')/('transfer-acceptance-'+suffix);vhosts.mkdir(mode=0o700)
        destination=Engine(root,'/srv/vectorcp/sites',vhosts)
        admin=destination.bootstrap({'setup_token':destination.setup_token(),'username':'transferowner','name':'Transfer QA','password':password})
        target_id=call(destination,admin,'accounts.create',{'username':name,'name':'Preserved destination','password':password,'site_limit':10,'storage_mb':512})['id']
        with destination.db() as db:
            db.execute('UPDATE users SET hosting_slot=? WHERE id=?',(allocated['hosting_slot'],target_id))
            # Force a different destination database identity.
            db.execute("INSERT INTO sites(id,user_id,domain,status,created) VALUES(100,?,'unrelated.transfer.test','suspended',1)",(admin['user']['id'],))
            target_before=dict(db.execute('SELECT * FROM users WHERE id=?',(target_id,)).fetchone())
        slot=destination.hosting.slot(target_before)
        def upload():
            uploaded=call(destination,admin,'transfers.upload.start',{'bytes':info['bytes'],'sha256':info['sha256']})
            offset=0
            with archive.open('rb') as incoming:
                while True:
                    block=incoming.read(uploaded['chunk_bytes'])
                    if not block:break
                    payload={'id':uploaded['id'],'offset':offset,'base64':base64.b64encode(block).decode()}
                    result=call(destination,admin,'transfers.upload.chunk',payload)
                    assert call(destination,admin,'transfers.upload.chunk',payload)==result
                    offset=result['received']
            call(destination,admin,'transfers.upload.finish',{'id':uploaded['id']})
            complete(destination,call(destination,admin,'transfers.inspect',{'id':uploaded['id'],'user_id':target_id}))
            row=call(destination,admin,'transfers.get',{'id':uploaded['id']});assert row['status']=='ready',row
            return uploaded['id']
        def importing(tid):return call(destination,admin,'transfers.import',{'id':tid,'user_id':target_id,'confirm_username':name,'sha256':info['sha256']})

        # Inject a failure after the real restricted SQL client committed data.
        tid=upload();client=destination.databases.client
        def fail_after_sql(*args,**kwargs):client(*args,**kwargs);raise Fault('Injected native SQL completion failure.',409)
        with patch.object(destination.databases,'client',side_effect=fail_after_sql):complete(destination,importing(tid),success=False)
        assert call(destination,admin,'transfers.get',{'id':tid})['status']=='rolled_back'
        with destination.db() as db:assert db.execute('SELECT COUNT(*) FROM sites WHERE user_id=?',(target_id,)).fetchone()[0]==0
        assert not list((destination.hosting.mounted(slot)/'sites').iterdir())
        assert not list((root/'hosting').glob('database-*.json'))
        assert not destination.hosting.sql(slot,"SHOW DATABASES LIKE 'site\\_%';").strip()
        passed('native SQL failure removes only newly created files identities and rows')
        call(destination,admin,'transfers.delete',{'id':tid})

        tid=upload()
        config=root/'nginx.conf'
        config.write_text('user nginx; worker_processes 1; pid '+str(root/'nginx.pid')+'; error_log '+str(root/'error.log')+';\n'
            'events { worker_connections 64; } http { include /etc/nginx/mime.types; access_log off; include '+str(vhosts/'*.conf')+'; }\n')
        def nginx(argv):
            if argv==['/usr/sbin/nginx','-t']:
                for path in vhosts.glob('*.conf'):path.write_text(path.read_text().replace('listen 80;','listen 127.0.0.1:18091;'))
                result=subprocess.run(['/usr/sbin/nginx','-t','-c',str(config)],capture_output=True)
                if result.returncode:raise Fault('Native transfer web configuration failed.',503)
            elif daemon is not None:os.kill(int((root/'nginx.pid').read_text()),signal.SIGHUP)
            return ''
        with patch('vectorcp.core.run_fixed',side_effect=nginx):complete(destination,importing(tid))
        assert call(destination,admin,'transfers.get',{'id':tid})['status']=='complete'
        with destination.db() as db:
            sites=[dict(r) for r in db.execute('SELECT * FROM sites WHERE user_id=? ORDER BY id',(target_id,))]
            assert dict(db.execute('SELECT * FROM users WHERE id=?',(target_id,)).fetchone())==target_before
            assert db.execute('SELECT COUNT(*) FROM sites WHERE id=100').fetchone()[0]==1
            for site in sites:assert site['status']=='suspended' and site['tls']==0
            assert db.execute('SELECT COUNT(*) FROM dns_zones').fetchone()[0]==0
            assert not db.execute('SELECT 1 FROM backup_schedules WHERE enabled=1').fetchone()
        for site,meta in zip(sites,manifest['sites']):
            public=destination.site_root(site)
            for name,item in meta['files'].items():assert fmt.checksum(public/name)==item['sha256']
            if meta['database']:
                original_site=next(s for s in original if s['domain']==site['domain'])
                source_tables=source.hosting.sql('01','SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=\'%s\' ORDER BY TABLE_NAME;'%original_site['database_name'])
                dest_tables=destination.hosting.sql(slot,'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=\'%s\' ORDER BY TABLE_NAME;'%site['database_name'])
                assert dest_tables==source_tables and dest_tables.strip()
                from vectorcp.databases import identifier
                for table in source_tables.decode().splitlines():
                    old=source.hosting.sql('01','CHECKSUM TABLE %s.%s EXTENDED;'%(identifier(original_site['database_name']),identifier(table))).split(b'\t')[-1].strip()
                    new=destination.hosting.sql(slot,'CHECKSUM TABLE %s.%s EXTENDED;'%(identifier(site['database_name']),identifier(table))).split(b'\t')[-1].strip()
                    assert new==old,(site['domain'],table,'row checksum mismatch')
                credentials=destination.databases.primary(site,slot)
                assert credentials['name']!=original_site['database_name']
                for sql in (b'SELECT * FROM mysql.user;',b"SELECT LOAD_FILE('/etc/shadow');",b"CREATE USER 'escape'@'localhost';"):
                    try:result=client(slot,credentials,sql)
                    except Fault:continue
                    assert result.strip() in (b'NULL',b'')
        passed('native import verifies file hashes tables row checksums fresh credentials and SQL privilege denial')
        passed('destination login plan ownership unrelated records and inactive services preserved')
        daemon=subprocess.Popen(['/usr/sbin/nginx','-c',str(config),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for attempt in range(50):
            try:
                connection=http.client.HTTPConnection('127.0.0.1',18091,timeout=2);connection.request('GET','/',headers={'Host':sites[0]['domain']});response=connection.getresponse();payload=response.read();connection.close()
                assert response.status==503 and b'Website suspended' in payload;break
            except OSError:time.sleep(.1)
        else:raise AssertionError('Suspended website did not respond')
        passed('real Nginx returns suspended response before application execution')
        # Reproduce the durable state left by SIGKILL between a maintenance
        # stop and its context-manager cleanup, then recover through the API.
        assert command(['systemctl','is-active','vectorcp-php@01'])=='active'
        with source.db() as db:db.execute("UPDATE transfers SET status='exporting',journal=? WHERE id=?",(json.dumps({'pause':{'slot':'01','restore':True}}),exported['id']))
        command(['systemctl','stop','vectorcp-php@01'])
        source=Engine(state,'/srv/vectorcp/sites','/etc/nginx/conf.d')
        actor=source.login(json.loads(context.read_text())['owner_login'])
        assert call(source,actor,'transfers.get',{'id':exported['id']})['status']=='needs_inspection'
        complete(source,call(source,actor,'transfers.rollback',{'id':exported['id'],'confirm_username':owner['username']}))
        assert command(['systemctl','is-active','vectorcp-php@01'])=='active'
        passed('interrupted export checkpoint holds account and explicit recovery restores PHP')
        with source.db() as db:
            for old in original:assert dict(db.execute('SELECT * FROM sites WHERE id=?',(old['id'],)).fetchone())==old
        for site in original:assert fmt.checksum(source.site_root(site)/'index.php' if (source.site_root(site)/'index.php').is_file() else source.site_root(site)/'index.html')==before[site['id']]
        assert command(['getenforce'])=='Enforcing'
        passed('source sites and SELinux enforcement preserved')
        (root/'result.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'real_mariadb':True,'real_nginx':True,'selinux':'Enforcing','scope':'portable files and primary SQL; no mail or full-machine recovery'},indent=2))
        print('RESULT:',root/'result.json',flush=True)
    finally:
        if daemon is not None:
            daemon.send_signal(signal.SIGQUIT)
            try:daemon.communicate(timeout=10)
            except subprocess.TimeoutExpired:daemon.kill();daemon.communicate()
        command(['systemctl','start','vectorcp-agent'])


if __name__=='__main__':main()
