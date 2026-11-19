"""Opt-in native MariaDB, scheduler and SFTP checks on a disposable guest.

Requires acceptance_linux.py fixtures. Stops the guest agent while a candidate
Engine owns its state, and starts it again afterwards. Never use on a real host.
The SFTP endpoint is a separate restricted local user, not an offsite machine.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import pwd
import secrets
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vectorcp.core import Engine, Fault

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--allow-disposable-host', required=True, action='store_true')
args = p.parse_args()
state = Path('/var/lib/vectorcp')
if not sys.platform.startswith('linux') or os.geteuid()!=0 or not (state/'acceptance-context.json').is_file():
    raise SystemExit('Requires root and disposable acceptance fixtures.')
context = json.loads((state/'acceptance-context.json').read_text())
checks=[]

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout

def record(name):
    checks.append(name)
    print('PASS:', name, flush=True)

def call(method, data=None, session=None):
    who=session or owner
    return engine.dispatch({'method':method,'data':data or {},'token':who['token'],'csrf':who['csrf']})

def wait(job):
    for _ in range(240):
        with engine.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job['job_id'],)).fetchone()
        if row['status'] in ('complete','failed'):
            return dict(row)
        time.sleep(.25)
    raise AssertionError('Job did not finish')

def complete(job):
    row=wait(job)
    assert row['status']=='complete',row['message']
    return row

def rejected(fn):
    try:
        fn()
    except Fault:
        return
    raise AssertionError('Forbidden operation was accepted')

def sql_import(payload):
    return call('databases.import',{'site_id':sid,'confirm':name,'base64':base64.b64encode(payload).decode()})

sshd=None
offsite_config=state/'offsite/destinations.json'
if offsite_config.exists():
    raise SystemExit('Refusing to replace an existing offsite destination configuration.')
run(['systemctl','stop','vectorcp-agent'])
try:
    engine=Engine(state,'/srv/vectorcp/sites','/etc/nginx/conf.d')
    owner=engine.login(context['owner_login'])
    with engine.db() as db:
        customer=db.execute('SELECT * FROM users WHERE hosting_slot=1').fetchone()
    fixture_site=state/'data-acceptance-site.json'
    if fixture_site.exists():
        sid=json.loads(fixture_site.read_text())['site_id']
        with engine.db() as db:
            previous_site=db.execute('SELECT * FROM sites WHERE id=?',(sid,)).fetchone()
        assert previous_site['domain'].startswith('data-') and previous_site['domain'].endswith('.acceptance.test') and previous_site['user_id']==customer['id']
    else:
        sid=call('sites.create',{'domain':'data-'+secrets.token_hex(4)+'.acceptance.test','user_id':customer['id']})['id']
        fixture_site.write_text(json.dumps({'site_id':sid}));fixture_site.chmod(0o600)
    with engine.db() as db:
        has_database=db.execute('SELECT database_name FROM sites WHERE id=?',(sid,)).fetchone()[0]
        # Only this explicit disposable fixture's prior runs are reset.
        for row in db.execute('SELECT id FROM backups WHERE site_id=?',(sid,)).fetchall():
            (engine.backups/(row['id']+'.tar.gz')).unlink(missing_ok=True)
        db.execute('DELETE FROM backups WHERE site_id=?',(sid,))
        db.execute('DELETE FROM offsite_copies WHERE site_id=?',(sid,))
        db.execute('DELETE FROM backup_schedules WHERE site_id=?',(sid,))
    if not has_database:
        complete(call('databases.create',{'site_id':sid}))
    else:
        engine.hosting.replace_database('01','site_%d'%sid,b'')
    name='site_%d'%sid
    creds=call('databases.credentials',{'site_id':sid})
    with engine.db() as db:
        site=dict(db.execute('SELECT * FROM sites WHERE id=?',(sid,)).fetchone())
        customer=dict(db.execute('SELECT * FROM users WHERE id=?',(site['user_id'],)).fetchone())
    complete(sql_import(b'CREATE TABLE records(id INT PRIMARY KEY, value VARCHAR(120)); INSERT INTO records VALUES(1,"original"),(2,"<script>escaped</script>");'))
    inspected=call('databases.inspect',{'site_id':sid})
    wildcard='siteZ%d'%sid
    assert engine.hosting.sql('01',"SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='%s';"%wildcard).strip()==b'0'
    rejected(lambda:engine.databases.client('01',creds,('CREATE DATABASE '+wildcard+';').encode()))
    assert inspected['usage']['tables']==1
    browsed=call('databases.browse',{'site_id':sid,'table':'records'})
    assert browsed['rows'][0]==['1','original']
    assert inspected['usage']['bytes']>0
    record('Database creation, SQL import, table browser and size reporting use real MariaDB')

    additional=call('databases.users.create',{'site_id':sid,'label':'Native reporting','privileges':['SELECT']})
    assert next(u for u in call('databases.users',{'site_id':sid})['users'] if u['username']==additional['username'])['privileges']==['SELECT']
    assert b'original' in engine.databases.client('01',additional,b'SELECT value FROM records;')
    rejected(lambda:engine.databases.client('01',additional,b'INSERT INTO records VALUES(3,"denied");'))
    rejected(lambda:engine.databases.client('01',additional,b'SELECT * FROM mysql.global_priv;'))
    rejected(lambda:engine.databases.client('01',additional,b'SELECT * FROM site_1.wp_options;'))
    call('databases.users.grants',{'site_id':sid,'username':additional['username'],'privileges':['SELECT','INSERT']})
    assert set(next(u for u in call('databases.users',{'site_id':sid})['users'] if u['username']==additional['username'])['privileges'])=={'SELECT','INSERT'}
    engine.databases.client('01',additional,b'INSERT INTO records VALUES(3,"allowed");')
    rotated=call('databases.users.rotate',{'site_id':sid,'username':additional['username']})
    rejected(lambda:engine.databases.client('01',additional,b'SELECT 1;'))
    assert engine.databases.client('01',rotated,b'SELECT 1;').strip()==b'1'
    call('databases.users.delete',{'site_id':sid,'username':rotated['username'],'confirm':rotated['username']})
    rejected(lambda:engine.databases.client('01',rotated,b'SELECT 1;'))
    record('Read-only grants deny writes and other databases; grant edits, password rotation and user removal work')

    before=call('databases.browse',{'site_id':sid,'table':'records'})['rows']
    bad=wait(sql_import(b'DELETE FROM records; THIS IS INVALID SQL;'))
    assert bad['status']=='failed'
    assert call('databases.browse',{'site_id':sid,'table':'records'})['rows']==before
    marker=Path('/tmp/vectorcp-sql-command-must-not-run')
    assert not marker.exists()
    assert wait(sql_import(b'\\! touch /tmp/vectorcp-sql-command-must-not-run\n'))['status']=='failed'
    assert not marker.exists()
    assert wait(sql_import(b"SELECT 'forbidden' INTO OUTFILE '/tmp/vectorcp-sql-command-must-not-run';"))['status']=='failed'
    assert not marker.exists()
    exported=call('databases.export',{'site_id':sid})
    assert b'CREATE TABLE' in base64.b64decode(exported['base64'])
    assert call('databases.browse',{'site_id':sid,'table':'records'})['rows']==before
    record('Failed imports restore previous data; SQL shell commands and server file writes are refused; export works')

    fixture=Path('/var/lib/vectorcp-offsite-acceptance')
    fixture.mkdir(mode=0o755,exist_ok=True)
    try:
        ident=pwd.getpwnam('vectorcp-offsite-test')
    except KeyError:
        run(['useradd','--system','--home-dir',str(fixture),'--shell','/bin/bash','vectorcp-offsite-test'])
        ident=pwd.getpwnam('vectorcp-offsite-test')
    hashed=run(['openssl','passwd','-6','-stdin'],input=secrets.token_urlsafe(32).encode()).decode().strip()
    run(['usermod','--password',hashed,'vectorcp-offsite-test'])
    key=fixture/'client'
    host=fixture/'host'
    for path in (key,host):
        if not path.exists():
            run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(path)])
    authorized=fixture/'authorized_keys'
    authorized.write_text(key.with_suffix('.pub').read_text());authorized.chmod(0o644)
    backups=fixture/'backups';backups.mkdir(exist_ok=True)
    os.chown(backups,ident.pw_uid,ident.pw_gid)
    config=fixture/'sshd_config'
    config.write_text('Port 22222\nListenAddress 127.0.0.1\nHostKey '+str(host)+'\nPidFile '+str(fixture/'sshd.pid')+'\nAuthorizedKeysFile '+str(authorized)+'\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\nAllowUsers vectorcp-offsite-test\nPermitRootLogin no\nForceCommand internal-sftp\nDisableForwarding yes\nSubsystem sftp internal-sftp\n')
    # sshd uses the guest's enforcing SELinux policy and an existing SSH port type.
    try:
        run(['semanage','port','-a','-t','ssh_port_t','-p','tcp','22222'])
    except subprocess.CalledProcessError:
        run(['semanage','port','-m','-t','ssh_port_t','-p','tcp','22222'])
    sshd=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f',str(config)],stdout=subprocess.DEVNULL,stderr=(fixture/'sshd.log').open('wb'))
    time.sleep(1)
    hosts=fixture/'known_hosts'
    hosts.write_text('[127.0.0.1]:22222 '+host.with_suffix('.pub').read_text())
    offsite_config.parent.mkdir(mode=0o700,exist_ok=True)
    offsite_config.write_text(json.dumps([{'id':'test-sftp','label':'Disposable SFTP fixture','host':'127.0.0.1','port':22222,'user':'vectorcp-offsite-test','path':str(backups),'key':str(key),'known_hosts':str(hosts)}]));offsite_config.chmod(0o600)
    manual=complete(call('backups.full',{'site_id':sid}))
    saved=call('backups.list')['backups'][0]
    complete(call('backups.offsite.send',{'id':saved['id'],'destination':'test-sftp'}))
    remote=call('backups.offsite.list')['copies'][0]
    assert len(list(backups.glob(saved['id']+'-*.tar.gz')))==1
    assert list(backups.glob(saved['id']+'-*.tar.gz'))[0].stat().st_mode & 0o777 == 0o600
    complete(call('backups.offsite.send',{'id':saved['id'],'destination':'test-sftp'}))
    # A wrong pinned key fails, without damaging the verified inventory/local copy.
    previous_hosts=hosts.read_text(); hosts.write_text('[127.0.0.1]:22222 '+key.with_suffix('.pub').read_text())
    assert wait(call('backups.offsite.send',{'id':saved['id'],'destination':'test-sftp'}))['status']=='failed'
    hosts.write_text(previous_hosts)
    record('SFTP upload and round-trip hash verification succeed; wrong pinned host key fails closed')

    call('backups.delete',{'id':saved['id']})
    assert any(c['id']==remote['id'] for c in call('backups.offsite.list')['copies'])
    complete(call('backups.offsite.fetch',{'id':remote['id']}))
    assert call('backups.describe',{'id':saved['id']})['sha256']==remote['sha256']
    complete(sql_import(b'UPDATE records SET value="changed" WHERE id=1;'))
    complete(call('backups.restore',{'id':saved['id']}))
    assert call('databases.browse',{'site_id':sid,'table':'records'})['rows']==before
    record('Deleted local archive is recovered from SFTP and restores original database data')

    with engine.db() as db:
        other_copies=db.execute('SELECT COUNT(*) FROM backups WHERE user_id=? AND site_id<>?',(customer['id'],sid)).fetchone()[0]
    retained=min(2,3-other_copies)
    assert retained>=1,'Fixture customer needs space for a new recovery point; unrelated copies were preserved.'
    call('backups.schedule.save',{'site_id':sid,'frequency':'daily','hour':3,'weekday':0,'keep':retained,'enabled':True,'destination':'test-sftp'})
    for _ in range(3):
        with engine.db() as db:
            db.execute('UPDATE backup_schedules SET next_run=1 WHERE site_id=?',(sid,))
        engine.backup_policy.tick()
        policy=call('backups.schedules')['schedules'][0]
        complete({'job_id':policy['last_job']})
    copies=call('backups.list')['backups']
    assert len([c for c in copies if c['site_id']==sid])==retained+1
    assert any(c['id']==saved['id'] for c in copies)
    assert call('backups.schedules')['schedules'][0]['last_status']=='complete'
    record('Due schedules run real files/SQL/SFTP jobs, rotate scheduled copies and preserve manual/unrelated copies')
    with engine.db() as db:
        db.execute('UPDATE backup_schedules SET enabled=0 WHERE site_id=?',(sid,))
    assert run(['getenforce']).strip()==b'Enforcing'
    record('SELinux remains enforcing throughout native checks')
finally:
    offsite_config.unlink(missing_ok=True)
    if sshd:
        sshd.terminate();sshd.wait(timeout=10)
    run(['systemctl','start','vectorcp-agent'])
report=state/'data-acceptance-results.json'
report.write_text(json.dumps({'checks':checks,'source':str(Path(__file__).resolve().parents[1]),'production_acceptance':False},indent=2)+'\n')
report.chmod(0o600)
print('Native data acceptance:',len(checks),'groups passed',flush=True)
