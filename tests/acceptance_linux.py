"""Opt-in acceptance against an UNUSED disposable native Linux installation.

This creates test accounts and databases and restarts the panel agent. Never run
on an occupied or production server. No cleanup or public DNS/TLS is performed.
"""
import argparse
import json
import os
import platform
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-disposable-host',action='store_true')
    args=parser.parse_args()
    if not args.allow_disposable_host:
        parser.error('Use --allow-disposable-host only on an unused disposable installation.')
    sys.path.insert(0,'/opt/vectorcp')
    from vectorcp.agent import rpc
    from vectorcp.core import Fault
    assert os.geteuid()==0 and sys.platform=='linux', 'Root on a disposable Linux host is required'
    os.umask(0o077)
    context=Path('/var/lib/vectorcp/acceptance-context.json')
    assert not context.exists(), 'Do not recreate existing acceptance records'
    with sqlite3.connect('/var/lib/vectorcp/control.sqlite3') as preflight_db:
        assert not preflight_db.execute('SELECT 1 FROM users LIMIT 1').fetchone(), 'Existing accounts detected: acceptance requires an unused installation'
    results=[]
    def passed(name, **evidence):
        results.append(dict(check=name, passed=True, **evidence)); print('PASS',name,flush=True)
    def command(args, **kwargs):
        return subprocess.run(args,check=True,capture_output=True,text=True,timeout=240,**kwargs).stdout.strip()
    def call(session,method,data=None):
        return rpc('/run/vectorcp/agent.sock',{'token':session['token'],'csrf':session['csrf'],'method':method,'data':data or {}})
    def job(session,method,data):
        ident=call(session,method,data)['job_id']; deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            record=next(j for j in call(session,'jobs.list')['jobs'] if j['id']==ident)
            if record['status']=='failed': raise AssertionError(method+': '+record['message'])
            if record['status']=='complete': passed(method,job=ident); return
            time.sleep(1)
        raise AssertionError(method+': timeout')
    assert command(['getenforce'])=='Enforcing'
    assert command(['systemctl','is-active','vectorcp-agent','vectorcp-web','nginx','vectorcp-dns']).splitlines()==['active']*4
    passed('fresh native services under SELinux enforcing')
    source=Path(__file__).resolve().parents[1]
    preflight=subprocess.run(['bash',str(source/'deploy/install.sh'),'--check'],capture_output=True,text=True)
    assert preflight.returncode and 'Existing application' in preflight.stderr
    passed('fresh installer refuses an existing application')
    token=command(['python3','-m','vectorcp.agent','--setup-token'],cwd='/opt/vectorcp')
    password=secrets.token_urlsafe(28)
    admin=rpc('/run/vectorcp/agent.sock',{'method':'bootstrap','data':{'setup_token':token,'username':'acceptowner','name':'Acceptance owner','password':password}})
    plan=call(admin,'plans.create',{'name':'Acceptance 512','kind':'customer','site_limit':3,'storage_mb':512,'allow_php':True,'allow_wordpress':True,'allow_databases':True,'allow_tls':True,'allow_dns':True,'allow_mail':False})['id']
    customers=[]; sites=[]
    for n in (1,2):
        user='accept'+str(n); pwd=secrets.token_urlsafe(28)
        ident=call(admin,'accounts.create',{'username':user,'name':'Acceptance '+str(n),'password':pwd,'plan_id':plan})['id']
        job(admin,'hosting.enable',{'id':ident,'storage_mb':512})
        customer=rpc('/run/vectorcp/agent.sock',{'method':'login','data':{'username':user,'password':pwd,'entry':'customer'}})
        site=call(customer,'sites.create',{'domain':'account'+str(n)+'.acceptance.test'})['id']
        customers.append(customer);sites.append(site)
    a,b=customers; first,second=sites
    try: call(a,'files.read',{'site_id':second,'path':'index.html'})
    except Fault as error: assert error.status==404
    else: raise AssertionError('Cross-customer file read accepted')
    passed('customer ownership enforced on Linux')
    def write(session,site,path,content):
        try: rev=call(session,'files.read',{'site_id':site,'path':path})['revision']
        except Fault: rev='new'
        return call(session,'files.write',{'site_id':site,'path':path,'content':content,'revision':rev})
    write(b,second,'private-marker.txt','customer two private marker')
    job(a,'hosting.php',{'site_id':first})
    job(a,'databases.create',{'site_id':first})
    credentials=call(a,'databases.credentials',{'site_id':first})
    with sqlite3.connect('/var/lib/vectorcp/control.sqlite3') as db:
        slot=db.execute('SELECT hosting_slot FROM users WHERE id=?',(b['user']['id'],)).fetchone()[0]
    sibling='/srv/vectorcp/accounts/%02d/sites/%d/public/private-marker.txt'%(slot,second)
    php='''<?php
    $pdo=new PDO(%s,%s,%s,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $pdo->exec("CREATE TABLE IF NOT EXISTS acceptance_probe (id INT PRIMARY KEY, value INT)");
    $pdo->exec("INSERT IGNORE INTO acceptance_probe VALUES (1,11)");
    echo json_encode(['database'=>(int)$pdo->query('SELECT value FROM acceptance_probe WHERE id=1')->fetchColumn(), 'sibling'=>@file_get_contents(%s), 'control'=>@file_get_contents('/var/lib/vectorcp/control.sqlite3'), 'write'=>file_put_contents(__DIR__.'/runtime-ok.txt','runtime write')]);
    '''%(json.dumps('mysql:unix_socket='+credentials['socket']+';dbname='+credentials['name']),json.dumps(credentials['username']),json.dumps(credentials['password']),json.dumps(sibling))
    write(a,first,'probe.php',php)
    def fetch():
        return json.loads(command(['curl','--fail','--silent','--show-error','--max-time','20','--resolve','account1.acceptance.test:80:127.0.0.1','http://account1.acceptance.test/probe.php']))
    probe=fetch(); assert probe=={'database':11,'sibling':False,'control':False,'write':13},probe
    passed('PHP and private SQL work; sibling volume and control state denied')
    assert command(['getsebool','httpd_can_network_connect_db']).endswith('off')
    passed('database uses private socket without global network permission')
    write(a,first,'restore-proof.txt','before backup')
    job(a,'backups.full',{'site_id':first})
    backup=call(a,'backups.list')['backups'][0]
    write(a,first,'restore-proof.txt','after backup')
    command(['mariadb','--no-defaults','--protocol=socket','--socket='+credentials['socket'],'--user=root',credentials['name']],input='UPDATE acceptance_probe SET value=22 WHERE id=1;')
    assert fetch()['database']==22
    job(a,'backups.restore',{'id':backup['id']})
    assert call(a,'files.read',{'site_id':first,'path':'restore-proof.txt'})['content']=='before backup'
    assert fetch()['database']==11
    passed('files and database restore preserves a working PHP website')
    listeners=command(['ss','-H','-lntp'])
    assert ':3306 ' not in listeners and '127.0.0.1:8765' in listeners
    passed('private panel listener and no TCP SQL listener')

    # Exercise transfer staging across an agent restart on an actual customer volume.
    import base64, hashlib
    content=bytes(range(256))*12289
    info={'site_id':first,'path':'upload.bin','bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    ticket=call(a,'files.upload.start',info)
    step=ticket['chunk_bytes']
    call(a,'files.upload.chunk',{'site_id':first,'id':ticket['id'],'offset':0,'base64':base64.b64encode(content[:step]).decode()})
    command(['systemctl','restart','vectorcp-agent','vectorcp-web'])
    for attempt in range(30):
        try:
            received=call(a,'files.upload.status',{'site_id':first,'id':ticket['id']})['received'];break
        except (OSError,Fault):time.sleep(.2)
    else:raise AssertionError('The restarted agent did not become ready')
    assert received==step
    for offset in range(received,len(content),step):
        call(a,'files.upload.chunk',{'site_id':first,'id':ticket['id'],'offset':offset,'base64':base64.b64encode(content[offset:offset+step]).decode()})
    call(a,'files.upload.finish',{'site_id':first,'id':ticket['id']})
    assert call(a,'files.upload.finish',{'site_id':first,'id':ticket['id']})['ok']
    described=call(a,'files.describe',{'site_id':first,'path':'upload.bin'})
    parts=[]
    for offset in range(0,described['bytes'],described['chunk_bytes']):
        chunk=call(a,'files.chunk',{'site_id':first,'path':'upload.bin','revision':described['revision'],'offset':offset})
        parts.append(base64.b64decode(chunk['base64']))
    assert b''.join(parts)==content
    passed('binary upload resumes after agent restart and download matches SHA-256',bytes=len(content))
    call(a,'files.copy',{'site_id':first,'path':'upload.bin','destination':'copy.bin','revision':described['revision']})
    item=next(f for f in call(a,'files.list',{'site_id':first})['files'] if f['name']=='copy.bin')
    call(a,'files.move',{'site_id':first,'path':'copy.bin','destination':'renamed.bin','revision':item['revision']})
    found=call(a,'files.search',{'site_id':first,'query':'renamed'})['files']
    assert [f['path'] for f in found]==['renamed.bin']
    call(a,'files.remove',{'site_id':first,'path':'renamed.bin','revision':found[0]['revision']})
    assert not call(a,'files.search',{'site_id':first,'query':'renamed'})['files']
    passed('copy, move, search and removal work on isolated Linux storage')
    assert fetch()['database']==11

    record={'owner_login':{'username':'acceptowner','password':password},'admin':admin,'customers':customers,'sites':sites,'backup':backup['id'],'results':results,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    context.write_text(json.dumps(record));context.chmod(0o600)
    Path('/var/lib/vectorcp/acceptance-results.json').write_text(json.dumps(results,indent=2))
    print('Linux acceptance passed. Private resume context remains in the disposable host state directory.',flush=True)


if __name__=='__main__':
    main()
