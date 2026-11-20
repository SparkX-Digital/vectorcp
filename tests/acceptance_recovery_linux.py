"""Opt-in recovery checks on an existing disposable acceptance guest.

Uses only dedicated .test sites and preserves all pre-existing backup archives.
Stops the panel agent while this process owns the fixture database. Never run on
a production server. Public delegation and offsite transport are not tested here.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vectorcp.core import Engine
from vectorcp.backup_policy import next_run


def command(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-disposable-host', required=True, action='store_true')
    parser.parse_args()
    state = Path('/var/lib/vectorcp')
    context = state/'acceptance-context.json'
    assert os.geteuid() == 0 and sys.platform.startswith('linux') and context.is_file()
    os.umask(0o077)
    assert command(['getenforce']) == 'Enforcing'
    command(['systemctl','stop','vectorcp-agent'])
    checks = []
    engine = None
    schedule_site = None
    original_schedules = []
    def passed(message):
        checks.append(message)
        print('PASS:', message, flush=True)
    try:
        engine = Engine(state,'/srv/vectorcp/sites','/etc/nginx/conf.d')
        assert engine.dns.enabled and engine.dns.profile['mode'] == 'private'
        owner = engine.login(json.loads(context.read_text())['owner_login'])
        def call(method, data=None):
            return engine.dispatch({'method':method,'data':data or {},'token':owner['token'],'csrf':owner['csrf']})
        def zone(site): return call('dns.list',{'site_id':site})
        def change(site, method, **values):
            z = zone(site)['zone']
            return call(method,dict(site_id=site,serial=z['serial'] if z else None,**values))
        def probe(site):
            z = zone(site)
            for tcp in (False,True):
                answer = engine.dns.probe(z['domain'],tcp)
                assert answer['authoritative'] and answer['serial'] == z['zone']['serial'], answer
        def records(site):
            return sorted((r['name'],r['type'],r['ttl'],r['value']) for r in zone(site)['records'])
        with engine.db() as db:
            original_schedules = [dict(r) for r in db.execute('SELECT * FROM backup_schedules')]
            db.execute('UPDATE backup_schedules SET enabled=0')
            original_backups = {r['id']:dict(r) for r in db.execute('SELECT * FROM backups')}
            prior_records = [tuple(r) for r in db.execute('SELECT * FROM dns_records ORDER BY id')]
            customer = db.execute('SELECT u.* FROM users u WHERE hosting_slot=2 AND active=1').fetchone()
            assert customer and db.execute('SELECT COUNT(*) FROM sites WHERE user_id=?',(customer['id'],)).fetchone()[0] < customer['site_limit']
        original_archives = {ident:hashlib.sha256((engine.backups/(ident+'.tar.gz')).read_bytes()).hexdigest()
                             for ident in original_backups}
        prefix = 'recovery-'+secrets.token_hex(4)
        sites = [call('sites.create',{'domain':prefix+'-'+str(n)+'.acceptance.test'})['id'] for n in (1,2)]
        for site in sites: call('dns.create',{'site_id':site});probe(site)
        site, other = sites
        domain = zone(site)['domain']
        for typ,value in [('TXT','quoted "text" & \\'),('CAA','0 issue "letsencrypt.org"'),('AAAA','2001:db8::1')]:
            change(site,'dns.save',name=typ.lower(),type=typ,value=value,ttl=600)
        expected = records(site)
        snapshot = change(site,'dns.snapshot.create')['id']
        exported = call('dns.snapshot.export',{'site_id':site,'id':snapshot})
        assert hashlib.sha256(exported['content'].encode()).hexdigest() == exported['sha256']
        change(site,'dns.save',name='temporary',type='A',value='192.0.2.7')
        change(site,'dns.snapshot.restore',id=snapshot,confirm_domain=domain)
        assert records(site) == expected and not zone(site)['zone']['verified']
        probe(site)
        change(site,'dns.zone.delete',confirm_domain=domain)
        assert not zone(site)['zone']
        for tcp in (False,True): assert engine.dns.probe(domain,tcp)['serial'] is None
        change(site,'dns.snapshot.restore',id=snapshot,confirm_domain=domain)
        assert records(site) == expected
        probe(site);probe(other)
        passed('DNS snapshot export, restore, removal and recreation use real BIND over UDP and TCP')

        for committed in (False,True):
            name = 'committed' if committed else 'uncommitted'
            before = zone(site)['zone']['serial']
            child = os.fork()
            if child == 0:
                target = engine.dns.recovery if committed else engine.dns
                attribute = 'clear' if committed else 'commit'
                with patch.object(target,attribute,side_effect=lambda *a:os._exit(86)):
                    change(site,'dns.save',name=name,type='A',value='192.0.2.9')
                os._exit(87)
            _,status = os.waitpid(child,0)
            assert os.waitstatus_to_exitcode(status) == 86
            assert engine.dns.recovery.pending.exists()
            upgrade = subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'deploy/upgrade.py'),'--check'],capture_output=True,text=True)
            assert upgrade.returncode and 'pending DNS' in upgrade.stderr
            if not committed:
                # A failed boot must be repairable before attempting to start
                # BIND with the interrupted or damaged generated files.
                command(['systemctl','stop','vectorcp-dns'])
                (engine.dns.zones/('site-%d.zone'%site)).write_bytes(b'\xff interrupted disk file\n')
            engine = Engine(state,'/srv/vectorcp/sites','/etc/nginx/conf.d')
            assert (name in [r['name'] for r in zone(site)['records']]) == committed
            assert 0 < (zone(site)['zone']['serial']-before)%4294967296 < 2147483648
            assert not engine.dns.recovery.pending.exists()
            probe(site);probe(other)
        passed('Abrupt exits before and after commit recover committed records with forward SOAs; upgrades refuse pending changes')

        target = engine.dns.zones/('site-%d.zone'%site)
        target.write_bytes(b'\xff damaged operator file\n')
        (engine.dns.zones/('site-%d.zone'%other)).unlink()
        orphan = engine.dns.zones/'site-2147483647.zone'
        orphan.write_text('retained orphan\n')
        result = call('dns.repair',{'site_id':site,'confirm_domain':domain})
        retained = state/'dns-quarantine'/result['quarantine_id']
        assert (retained/target.name).read_bytes() == b'\xff damaged operator file\n'
        assert (retained/orphan.name).read_text() == 'retained orphan\n' and not orphan.exists()
        probe(site);probe(other)
        with engine.db() as db:
            original_ids = {r[0] for r in prior_records}
            assert [tuple(r) for r in db.execute('SELECT * FROM dns_records ORDER BY id') if r['id'] in original_ids] == prior_records
        passed('Owner repair rebuilds missing/corrupt zones and retains original and unreferenced files without changing existing records')

        schedule_site = call('sites.create',{'domain':prefix+'-monthly.acceptance.test','user_id':customer['id']})['id']
        call('backups.schedule.save',{'site_id':schedule_site,'frequency':'monthly','monthday':31,'hour':3,'keep':1,'enabled':True})
        for _ in range(3):
            with engine.db() as db: db.execute('UPDATE backup_schedules SET next_run=1 WHERE site_id=?',(schedule_site,))
            engine.backup_policy.tick()
            with engine.db() as db: job = db.execute('SELECT last_job FROM backup_schedules WHERE site_id=?',(schedule_site,)).fetchone()[0]
            for attempt in range(240):
                with engine.db() as db: row = db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
                if row['status'] in ('complete','failed'): break
                time.sleep(.25)
            assert row['status'] == 'complete',row['message']
        with engine.db() as db:
            policy = db.execute('SELECT * FROM backup_schedules WHERE site_id=?',(schedule_site,)).fetchone()
            assert policy['frequency'] == 'monthly' and policy['monthday'] == 31 and policy['next_run'] > int(time.time())
            assert db.execute('SELECT COUNT(*) FROM backups WHERE site_id=?',(schedule_site,)).fetchone()[0] == 1
            for ident,previous in original_backups.items(): assert dict(db.execute('SELECT * FROM backups WHERE id=?',(ident,)).fetchone()) == previous
        for ident,digest in original_archives.items(): assert hashlib.sha256((engine.backups/(ident+'.tar.gz')).read_bytes()).hexdigest() == digest
        stamp = lambda y,m,d:int(datetime.datetime(y,m,d,3,tzinfo=datetime.timezone.utc).timestamp())
        assert next_run(stamp(2026,1,31),'monthly',3,0,31) == stamp(2026,2,28)
        assert next_run(stamp(2028,1,31),'monthly',3,0,31) == stamp(2028,2,29)
        passed('Three due monthly jobs create real archives, retain one scheduled copy and preserve every pre-existing archive')
        assert command(['getenforce']) == 'Enforcing'
        passed('SELinux stays enforcing throughout recovery and backup checks')
    finally:
        if engine is not None:
            with engine.db() as db:
                if schedule_site: db.execute('UPDATE backup_schedules SET enabled=0 WHERE site_id=?',(schedule_site,))
                for row in original_schedules:
                    db.execute('UPDATE backup_schedules SET enabled=? WHERE site_id=?',(row['enabled'],row['site_id']))
        command(['systemctl','start','vectorcp-agent'])
    result = state/'recovery-acceptance-results.json'
    result.write_text(json.dumps({'checks':checks,'production_acceptance':False},indent=2)+'\n')
    result.chmod(0o600)
    print('Native recovery acceptance:',len(checks),'groups passed',flush=True)


if __name__ == '__main__':
    main()
