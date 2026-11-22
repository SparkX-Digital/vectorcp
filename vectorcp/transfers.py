"""Scoped portable-account transfers into empty, existing hosting allocations."""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import threading
import time

from .core import Fault, integer
from .distribution import manages, available
from . import transfer_format as fmt

CHUNK = 256 * 1024
READ_ONLY = {'transfers.list','transfers.get','transfers.describe','transfers.chunk','transfers.upload.status'}
OPERATIONS = READ_ONLY | {'transfers.export','transfers.upload.start','transfers.upload.chunk',
    'transfers.upload.finish','transfers.inspect','transfers.import','transfers.rollback','transfers.delete'}
BUSY = ('queued','checking','exporting','importing','needs_inspection','rolling_back')


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS transfers(
      id TEXT PRIMARY KEY,actor_id INTEGER NOT NULL REFERENCES users(id),
      user_id INTEGER REFERENCES users(id),direction TEXT NOT NULL,status TEXT NOT NULL,
      bytes INTEGER NOT NULL DEFAULT 0,received INTEGER NOT NULL DEFAULT 0,
      sha256 TEXT NOT NULL DEFAULT '',created INTEGER NOT NULL,updated INTEGER NOT NULL,
      job_id TEXT,message TEXT NOT NULL DEFAULT '',manifest TEXT NOT NULL DEFAULT '{}',
      report TEXT NOT NULL DEFAULT '{}',journal TEXT NOT NULL DEFAULT '{}')''')
    db.execute('CREATE INDEX IF NOT EXISTS transfer_owner ON transfers(user_id,status)')
    db.execute("UPDATE transfers SET status='needs_inspection',message='Interrupted transfer. The server owner must inspect its new allocations and recorded PHP maintenance stop.' WHERE status IN ('importing','rolling_back') OR (status IN ('queued','exporting') AND journal<>'{}')")
    db.execute("UPDATE transfers SET status='failed',message='Interrupted before publication; retry inspection or export.' WHERE status IN ('queued','checking','exporting')")


class Transfers:
    def __init__(self,engine):
        self.e=engine
        self.folder=engine.state/'transfers';self.folder.mkdir(mode=0o700,exist_ok=True)
        if self.folder.is_symlink():raise Fault('Inspect the private transfer staging directory.',503)
        os.chmod(self.folder,0o700)

    def account(self,db,actor,ident,empty=False):
        if actor['role'] not in ('admin','reseller'):raise Fault('Account transfers require an owner or authorized reseller.',403)
        ident=integer(ident,'customer',1,2147483647)
        owner=db.execute("SELECT * FROM users WHERE id=? AND role='customer' AND is_reseller=0",(ident,)).fetchone()
        if not owner or not manages(db,actor,ident):raise Fault('Customer not found in your account scope.',404)
        self.e.hosting.slot(owner)
        if actor['role']=='reseller' and not available(db,owner):raise Fault('Choose an active customer in your account scope.',409)
        if empty:
            if not available(db,owner):raise Fault('Choose an active target customer.',409)
            if db.execute('SELECT 1 FROM sites WHERE user_id=?',(ident,)).fetchone():raise Fault('The destination customer must have no websites. Existing accounts are never overwritten.',409)
        return dict(owner)

    def idle(self,db,user_id):
        if db.execute("SELECT 1 FROM transfers WHERE user_id=? AND status IN ('queued','importing','needs_inspection','rolling_back')",(user_id,)).fetchone():
            raise Fault('This customer has an unfinished transfer. Inspect it in Account transfers first.',409)

    def row(self,db,actor,ident):
        if actor['role'] not in ('admin','reseller'):raise Fault('Account transfers require an owner or authorized reseller.',403)
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{24}',ident):raise Fault('Transfer not found.',404)
        row=db.execute('SELECT * FROM transfers WHERE id=?',(ident,)).fetchone()
        if not row or (row['actor_id']!=actor['id'] and actor['role']!='admin'):
            raise Fault('Transfer not found.',404)
        if row['user_id'] and not manages(db,actor,row['user_id']):raise Fault('Transfer not found.',404)
        return dict(row)

    def path(self,row,partial=False):
        path=self.folder/(row['id']+('.part' if partial else '.tar.gz'))
        if path.exists() or path.is_symlink():
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or info.st_mode&0o077 or info.st_size>fmt.MAX_ARCHIVE:
                raise Fault('Inspect unsafe transfer staging files before continuing.',409)
        return path

    def capacity(self,db,actor,size):
        count,total=db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM transfers').fetchone()
        own=db.execute('SELECT COUNT(*) FROM transfers WHERE actor_id=?',(actor['id'],)).fetchone()[0]
        if count>=8 or own>=2 or total+size>2*1024**3:
            raise Fault('Transfer storage is full: retain at most two archives per operator, eight and 2 GB globally. Download and remove an old archive first.',409)
        if shutil.disk_usage(self.folder).free<size+fmt.MAX_ARCHIVE+64*fmt.MIB:
            raise Fault('Transfer staging needs room for the archive, bounded inspection and 64 MB headroom.',409)

    def summary(self,row):
        return {k:row[k] for k in ('id','user_id','direction','status','bytes','received','sha256','created','updated','job_id','message')}

    def dispatch(self,db,actor,method,data):
        if actor['role'] not in ('admin','reseller'):raise Fault('Account transfers require an owner or authorized reseller.',403)
        if method=='transfers.list':
            rows=db.execute('SELECT * FROM transfers '+('' if actor['role']=='admin' else 'WHERE actor_id=? ')+'ORDER BY created DESC,id DESC LIMIT 50',() if actor['role']=='admin' else (actor['id'],))
            return {'transfers':[self.summary(r) for r in rows if not r['user_id'] or manages(db,actor,r['user_id'])],
                    'max_bytes':fmt.MAX_ARCHIVE,'chunk_bytes':CHUNK}
        if method in ('transfers.export','transfers.upload.start'):
            size=fmt.MAX_ARCHIVE if method=='transfers.export' else integer(data.get('bytes'),'archive bytes',1,fmt.MAX_ARCHIVE)
            self.capacity(db,actor,size)
            ident=secrets.token_hex(12);now=int(time.time())
            if method=='transfers.upload.start':
                sha=data.get('sha256')
                if not isinstance(sha,str) or not fmt.HEX.fullmatch(sha):raise Fault('The archive SHA-256 is invalid.')
                row={'id':ident}
                self.path(row,True).touch(mode=0o600,exist_ok=False)
                db.execute("INSERT INTO transfers(id,actor_id,direction,status,bytes,sha256,created,updated) VALUES(?,?,'import','uploading',?,?,?,?)",(ident,actor['id'],size,sha,now,now))
                return {'id':ident,'received':0,'chunk_bytes':CHUNK}
            owner=self.account(db,actor,data.get('user_id'))
            if data.get('confirm_username')!=owner['username']:raise Fault('Type the source username to confirm its export.',409)
            self.idle(db,owner['id'])
            db.execute("INSERT INTO transfers(id,actor_id,user_id,direction,status,bytes,created,updated) VALUES(?,?,?,'export','uploaded',?,?,?)",(ident,actor['id'],owner['id'],size,now,now))
            return self.queue(db,actor,self.row(db,actor,ident),'export',owner)
        row=self.row(db,actor,data.get('id'))
        path=self.path(row)
        if method=='transfers.get':
            return dict(self.summary(row),report=json.loads(row['report']),recoverable=bool(json.loads(row['journal'])))
        if method in ('transfers.describe','transfers.chunk'):
            if row['direction']!='export' or row['status']!='complete' or not path.is_file() or path.stat().st_size!=row['bytes']:
                raise Fault('A completed account export is required.',409)
            if method=='transfers.describe':return {'filename':'VectorCP-account-'+row['id']+'.tar.gz','bytes':row['bytes'],'sha256':row['sha256'],'chunk_bytes':CHUNK}
            offset=integer(data.get('offset'),'download offset',0,row['bytes'])
            with path.open('rb') as stream:stream.seek(offset);payload=stream.read(CHUNK)
            return {'offset':offset,'base64':base64.b64encode(payload).decode()}
        if method.startswith('transfers.upload.'):
            if row['direction']!='import' or row['status']!='uploading':raise Fault('This upload is no longer open.',409)
            partial=self.path(row,True)
            if method=='transfers.upload.status':return {'id':row['id'],'received':row['received'],'bytes':row['bytes'],'chunk_bytes':CHUNK}
            if method=='transfers.upload.finish':
                candidate=partial if partial.exists() else path
                if row['received']!=row['bytes'] or not candidate.exists() or candidate.stat().st_size!=row['bytes'] or fmt.checksum(candidate)!=row['sha256']:
                    raise Fault('The complete archive must match its expected size and SHA-256.',409)
                if partial.exists():os.replace(partial,path)
                self.sync()
                db.execute("UPDATE transfers SET status='uploaded',updated=? WHERE id=?",(int(time.time()),row['id']))
                return {'ok':True}
            offset=integer(data.get('offset'),'upload offset',0,row['bytes'])
            try:
                encoded=data.get('base64')
                if not isinstance(encoded,str) or len(encoded)>(CHUNK+2)//3*4:raise ValueError()
                payload=base64.b64decode(encoded,validate=True)
                if not payload or len(payload)>CHUNK or offset+len(payload)>row['bytes']:raise ValueError()
            except (ValueError,TypeError):raise Fault('Choose a valid transfer chunk up to 256 KB.')
            if not partial.is_file():raise Fault('Inspect or finish the interrupted upload.',409)
            with partial.open('r+b') as stream:
                if offset<row['received']:
                    stream.seek(offset)
                    if offset+len(payload)<=row['received'] and stream.read(len(payload))==payload:return {'received':row['received']}
                    raise Fault('The retried chunk differs from accepted data.',409)
                if offset!=row['received']:raise Fault('Resume at the last accepted upload offset.',409)
                stream.truncate(row['received']);stream.seek(offset);stream.write(payload);stream.flush();os.fsync(stream.fileno())
            received=offset+len(payload)
            db.execute('UPDATE transfers SET received=?,updated=? WHERE id=?',(received,int(time.time()),row['id']))
            return {'received':received}
        if method=='transfers.delete':
            if row['status'] in BUSY or json.loads(row['journal']):raise Fault('Finish or recover this transfer before removing its archive.',409)
            temporary=self.folder/(row['id']+'.exporting')
            if temporary.exists() or temporary.is_symlink():
                info=temporary.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or info.st_mode&0o077:raise Fault('Inspect unsafe transfer staging files before continuing.',409)
                temporary.unlink()
            path.unlink(missing_ok=True);self.path(row,True).unlink(missing_ok=True);self.sync()
            db.execute('DELETE FROM transfers WHERE id=?',(row['id'],));self.e.log(db,actor,method,row['id'])
            return {'ok':True}
        if method=='transfers.rollback':
            if actor['role']!='admin':raise Fault('Only the server owner can roll back an interrupted transfer.',403)
            owner=self.account(db,actor,row['user_id'])
            if row['status']!='needs_inspection' or data.get('confirm_username')!=owner['username']:
                raise Fault('Confirm the affected customer username of an interrupted transfer.',409)
            return self.queue(db,actor,row,'rollback',owner)
        if method in ('transfers.inspect','transfers.import'):
            if row['direction']!='import' or row['status'] not in ('uploaded','ready','blocked','failed','rolled_back') or json.loads(row['journal']):
                raise Fault('Finish uploading or recover this transfer before inspection.',409)
            owner=self.account(db,actor,data.get('user_id'),empty=True)
            self.idle(db,owner['id'])
            if method=='transfers.import':
                if row['status']!='ready' or row['user_id']!=owner['id'] or data.get('confirm_username')!=owner['username'] or data.get('sha256')!=row['sha256']:
                    raise Fault('Inspect this archive for the selected customer and confirm its username and SHA-256.',409)
            db.execute('UPDATE transfers SET user_id=? WHERE id=?',(owner['id'],row['id']))
            row['user_id']=owner['id']
            return self.queue(db,actor,row,'inspect' if method=='transfers.inspect' else 'import',owner)
        raise Fault('Unknown account-transfer operation.',404)

    def sync(self):
        fd=os.open(self.folder,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def queue(self,db,actor,row,operation,owner):
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():raise Fault('Wait for the current hosting job before transferring an account.',409)
        if not self.e.development and Path('/run/vectorcp-profile-maintenance').exists():raise Fault('Wait for service maintenance to finish.',409)
        job=secrets.token_hex(12);now=int(time.time())
        db.execute("INSERT INTO jobs VALUES(?,?,NULL,?,'queued','Waiting to start.',?,?)",(job,owner['id'],'transfers.'+operation,now,now))
        db.execute("UPDATE transfers SET status=?,job_id=?,message='Waiting to start.',updated=? WHERE id=?",('rolling_back' if operation=='rollback' else 'queued',job,now,row['id']))
        self.e.log(db,actor,'transfers.'+operation+'.queued',owner['username']);db.commit()
        thread=threading.Thread(target=self.run,args=(row['id'],job,dict(actor),operation,owner['id']),daemon=True)
        thread.start()
        return {'ok':True,'id':row['id'],'job_id':job}

    def update(self,ident,**values):
        with self.e.db() as db:
            values['updated']=int(time.time())
            db.execute('UPDATE transfers SET '+','.join(k+'=?' for k in values)+' WHERE id=?',tuple(values.values())+(ident,))

    def run(self,ident,job,actor,operation,user_id):
        try:
            with self.e.hosting.worker_lock,self.e.dns.maintenance():
                with self.e.lock,self.e.db() as db:
                    row=self.row(db,actor,ident);owner=self.account(db,actor,user_id,empty=operation in ('inspect','import'))
                    db.execute("UPDATE jobs SET status='running',message='Checking account transfer.',updated=? WHERE id=?",(int(time.time()),job))
                self.update(ident,status={'export':'exporting','inspect':'checking','import':'importing','rollback':'rolling_back'}[operation])
                if operation=='export':self.export(ident,owner)
                elif operation=='rollback':self.rollback(ident,owner)
                else:
                    if fmt.checksum(self.path(row))!=row['sha256']:raise Fault('The staged archive changed. Upload it again.',409)
                    if shutil.disk_usage(self.folder).free<fmt.MAX_ARCHIVE+64*fmt.MIB:raise Fault('Inspection requires 414 MB of private staging headroom.',409)
                    with fmt.opened(self.path(row),self.folder) as (archive,manifest):
                        with self.e.lock,self.e.db() as db:report=self.preflight(db,actor,owner,manifest)
                        self.update(ident,manifest=json.dumps(manifest),report=json.dumps(report))
                        if operation=='inspect':self.update(ident,status='blocked' if report['conflicts'] else 'ready',message='Resolve conflicts before importing.' if report['conflicts'] else 'Inspection passed. Confirm the destination to import.')
                        else:
                            if report['conflicts']:raise Fault('Preflight changed: '+report['conflicts'][0],409)
                            self.import_account(ident,owner,manifest,archive,actor)
                with self.e.db() as db:
                    db.execute("UPDATE jobs SET status='complete',message='Account transfer operation finished.',updated=? WHERE id=?",(int(time.time()),job))
                    self.e.log(db,actor,'transfers.'+operation+'.complete',owner['username'])
        except Exception as error:
            message=str(error) if isinstance(error,Fault) else 'The transfer failed. Inspect the private server state before retrying.'
            with self.e.db() as db:row=dict(db.execute('SELECT * FROM transfers WHERE id=?',(ident,)).fetchone())
            if operation=='rollback' and json.loads(row['journal']):
                self.update(ident,status='needs_inspection',message=message[:350])
            if operation in ('import','export') and json.loads(row['journal']):
                try:
                    with self.e.hosting.worker_lock,self.e.dns.maintenance():self.rollback(ident,owner)
                except Exception:self.update(ident,status='needs_inspection',message='Transfer stopped; rollback could not finish. The server owner must inspect this transfer.')
            with self.e.db() as db:
                current=db.execute('SELECT status FROM transfers WHERE id=?',(ident,)).fetchone()[0]
                if current not in ('needs_inspection','rolled_back'):db.execute("UPDATE transfers SET status='failed',message=?,updated=? WHERE id=?",(message[:350],int(time.time()),ident))
                db.execute("UPDATE jobs SET status='failed',message=?,updated=? WHERE id=?",(message[:350],int(time.time()),job))
                self.e.log(db,actor,'transfers.'+operation+'.failed',str(user_id))

    def preflight(self,db,actor,owner,manifest):
        owner=self.account(db,actor,owner['id'],empty=True)
        features=self.e.distribution.features(db,owner);conflicts=[];files=sql=0;sites=[]
        from .dns_recovery import SNAPSHOTS_GLOBAL
        if db.execute('SELECT COUNT(*) FROM dns_snapshots').fetchone()[0]+sum(s['dns'] is not None for s in manifest['sites'])>SNAPSHOTS_GLOBAL:
            conflicts.append('DNS recovery storage is full. Remove an old recovery copy before importing.')
        if len(manifest['sites'])>owner['site_limit']:conflicts.append('The destination hosting plan has too few website slots.')
        for site in manifest['sites']:
            if db.execute('SELECT 1 FROM sites WHERE domain=?',(site['domain'],)).fetchone():conflicts.append('Domain already exists: '+site['domain'])
            required=[]
            if site['runtime']!='static':required.append('php')
            if site['runtime']=='wordpress':required.append('wordpress')
            if site['database']:required.append('databases')
            if site['dns'] is not None:required.append('dns')
            if any(not features[f] for f in required):conflicts.append('The destination plan does not include the required tools for '+site['domain'])
            size=sum(r['bytes'] for r in site['files'].values());dbsize=site['database']['bytes'] if site['database'] else 0
            files+=size;sql+=dbsize
            sites.append({'domain':site['domain'],'runtime':site['runtime'],'files':len(site['files']),'file_bytes':size,'sql_bytes':dbsize,'dns_records':len(site['dns']['records']) if site['dns'] else 0})
        estimate=files+3*sql+64*fmt.MIB
        target=self.e.hosting.mounted(self.e.hosting.slot(owner)) if not self.e.development else self.e.sites
        if estimate>owner['storage_mb']*fmt.MIB or shutil.disk_usage(target).free<estimate:conflicts.append('The empty customer volume needs website files, three times SQL size and 64 MB staging headroom.')
        return {'source':manifest['account'],'target_username':owner['username'],'sites':sites,'conflicts':conflicts,
            'estimated_bytes':estimate,'warnings':['Imported websites stay suspended. Review applications and reissue certificates before activation.',
                'Database identities and passwords change. General applications need their connection settings updated; managed WordPress settings are remapped.',
                'DNS records are retained as inactive recovery copies. Schedules are paused; offsite destinations, access credentials and TLS keys are excluded.']}

    def export(self,ident,owner):
        from .routing import settings
        path=self.path({'id':ident});temporary=self.folder/(ident+'.exporting')
        with self.e.db() as db:
            sites=[dict(r) for r in db.execute('SELECT * FROM sites WHERE user_id=? ORDER BY id',(owner['id'],))]
            if not 1<=len(sites)<=fmt.MAX_SITES:raise Fault('Export supports accounts with 1–10 websites.',409)
        manifest={'format':'vectorcp-account','version':1,'account':{'username':owner['username'],'name':owner['name']},'sites':[]}
        budget={'entries':0,'bytes':0};sql_total=0
        try:
            with self.paused(ident,self.e.hosting.slot(owner)),tarfile.open(temporary,'w:gz',format=tarfile.USTAR_FORMAT) as archive:
                os.chmod(temporary,0o600)
                for index,site in enumerate(sites):
                    prefix='account/sites/%d/'%index
                    files,dirs=fmt.snapshot_files(self.e,self.e.site_root(site),archive,prefix+'public',budget)
                    database=None
                    if site['database_name']:
                        payload=self.e.hosting.dump_database(self.e.hosting.slot(owner),site['database_name'])
                        sql_total+=len(payload)
                        if not payload or sql_total>fmt.SQL_TOTAL:raise Fault('Transfer SQL supports 64 MB per site and 128 MB total.',409)
                        fmt.add_bytes(archive,prefix+'database.sql',payload)
                        database={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
                    dns=None
                    with self.e.db() as db:
                        zone=db.execute('SELECT * FROM dns_zones WHERE site_id=?',(site['id'],)).fetchone()
                        if zone:
                            from .dns_recovery import encode
                            records=[]
                            for record in db.execute('SELECT name,type,ttl,value FROM dns_records WHERE site_id=? ORDER BY id',(site['id'],)):
                                record=dict(record)
                                if record['type']=='TXT':record['value']=json.loads(record['value'])
                                if record['type']=='CAA':
                                    flags,tag,value=record['value'].split(None,2);record['value']=flags+' '+tag+' '+json.loads(value)
                                records.append(record)
                            dns={'format':'vectorcp-dns-records','version':1,'domain':site['domain'],'source_serial':zone['serial'],'created':int(time.time()),'records':records}
                        route=settings(db,site['id'])
                        policy=db.execute('SELECT * FROM backup_schedules WHERE site_id=?',(site['id'],)).fetchone()
                    manifest['sites'].append({'domain':site['domain'],'runtime':site['runtime'],'wordpress_version':site['wordpress_version'],
                        'files':files,'directories':dirs,'database':database,'dns':dns,
                        'routing':{k:route[k] for k in ('redirects','error_pages')},
                        'schedule':{k:policy[k] for k in ('frequency','hour','weekday','monthday','keep')} if policy else None})
                fmt.metadata(manifest);payload=json.dumps(manifest,sort_keys=True).encode()
                if len(payload)>fmt.MAX_MANIFEST:raise Fault('The transfer manifest exceeds 2 MB.',409)
                fmt.add_bytes(archive,'account/manifest.json',payload)
            if temporary.stat().st_size>fmt.MAX_ARCHIVE:raise Fault('The transfer archive exceeds 350 MB.',409)
            with fmt.opened(temporary,self.folder):pass
            with temporary.open('rb') as stream:os.fsync(stream.fileno())
            os.replace(temporary,path);self.sync()
            self.update(ident,status='complete',bytes=path.stat().st_size,sha256=fmt.checksum(path),message='Export verified. Keep this archive private; it contains website secrets.',report=json.dumps({'sites':[{'domain':s['domain'],'runtime':s['runtime']} for s in manifest['sites']]}))
        finally:temporary.unlink(missing_ok=True)

    def journal(self,ident,change):
        with self.e.db() as db:
            value=json.loads(db.execute('SELECT journal FROM transfers WHERE id=?',(ident,)).fetchone()[0]);change(value)
            db.execute('UPDATE transfers SET journal=?,updated=? WHERE id=?',(json.dumps(value),int(time.time()),ident))

    @contextlib.contextmanager
    def paused(self,ident,slot):
        """Keep a restoration intent across process death, not only exceptions."""
        active=False
        if not self.e.development:
            active=subprocess.run(['/usr/bin/systemctl','is-active','--quiet','vectorcp-php@'+slot],timeout=10,check=False).returncode==0
            self.journal(ident,lambda j:j.update(pause={'slot':slot,'restore':active}))
        try:
            with self.e.hosting.paused(slot):yield
        finally:
            if not self.e.development:
                restored=not active or subprocess.run(['/usr/bin/systemctl','is-active','--quiet','vectorcp-php@'+slot],timeout=10,check=False).returncode==0
                if restored:self.journal(ident,lambda j:j.pop('pause',None))

    def import_account(self,ident,owner,manifest,archive,actor):
        slot=self.e.hosting.slot(owner)
        with self.paused(ident,slot):
            with self.e.lock,self.e.db() as db:
                report=self.preflight(db,actor,owner,manifest)
                if report['conflicts']:raise Fault(report['conflicts'][0],409)
                entries=[];now=int(time.time())
                for source in manifest['sites']:
                    cur=db.execute("INSERT INTO sites(domain,user_id,status,created,runtime,wordpress_version,admin_hold) VALUES(?,?,'suspended',?,?,?,?)",(source['domain'],owner['id'],now,source['runtime'],source['wordpress_version'],int(actor['role']=='admin')))
                    entries.append({'id':cur.lastrowid,'domain':source['domain'],'created':now})
                journal=json.loads(db.execute('SELECT journal FROM transfers WHERE id=?',(ident,)).fetchone()[0])
                journal.update(sites=entries,files=[],databases=[],configs=[])
                db.execute('UPDATE transfers SET journal=? WHERE id=?',(json.dumps(journal),ident))
            for index,(entry,source) in enumerate(zip(entries,manifest['sites'])):
                site=dict(entry,user_id=owner['id'],runtime=source['runtime'],status='suspended',tls=0,database_name=None)
                root=self.e.site_root(site)
                if root.parent.exists() or root.parent.is_symlink():raise Fault('A reserved website folder already exists. It was preserved.',409)
                self.journal(ident,lambda j:j['files'].append(site['id']))
                root.mkdir(parents=True,mode=0o700)
                for directory in source['directories']:(root/directory).mkdir(parents=True,exist_ok=True,mode=0o700)
                for name in source['files']:
                    target=root/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with archive.extractfile('account/sites/%d/public/%s'%(index,name)) as incoming,target.open('xb') as outgoing:
                        shutil.copyfileobj(incoming,outgoing,262144)
                        outgoing.flush();os.fsync(outgoing.fileno())
                    if fmt.checksum(target)!=source['files'][name]['sha256']:raise Fault('A restored file failed verification.',409)
                if source['database']:
                    name='site_%d'%site['id'];credentials_path=self.e.state/('hosting/database-%d.json'%site['id'])
                    if credentials_path.exists() or credentials_path.is_symlink():raise Fault('Private database credentials already exist for a reserved allocation.',409)
                    self.e.hosting.start_db(slot)
                    exists=self.e.hosting.sql(slot,"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='%s'; SELECT User FROM mysql.user WHERE User='%s';"%(name,name))
                    if exists.strip():raise Fault('A reserved database identity already exists. It was preserved.',409)
                    self.journal(ident,lambda j:j['databases'].append(site['id']))
                    credentials=self.e.hosting.create_database(site,owner)
                    with archive.extractfile('account/sites/%d/database.sql'%index) as source_sql:payload=source_sql.read(fmt.SQL_LIMIT+1)
                    # External SQL always runs as its newly scoped application
                    # account. Never call the privileged rollback SQL importer.
                    try:self.e.databases.client(slot,credentials,payload,maximum=fmt.MIB)
                    finally:
                        self.e.databases.disconnect(slot,name)
                        self.e.hosting.sql(slot,"ALTER USER '%s'@'localhost' IDENTIFIED BY '%s';"%(name,credentials['password']))
                    site['database_name']=name
                    if source['runtime']=='wordpress':self.remap_wordpress(root/'wp-config.php',credentials)
                if not self.e.development:
                    self.e.hosting.own_tree(slot,root)
                    import pwd
                    identity=self.e.hosting.identity(slot);os.chown(root.parent,0,identity.pw_gid);root.parent.chmod(0o750)
                    from .hosting import command
                    command(['/usr/sbin/restorecon','-R',str(root.parent)])
                with self.e.db() as db:
                    db.execute('UPDATE sites SET database_name=? WHERE id=?',(site['database_name'],site['id']))
                    route=source['routing']
                    db.execute('INSERT INTO site_routing VALUES(?,1,0,?,?)',(site['id'],json.dumps(route['redirects']),json.dumps(route['error_pages'])))
                    if source['dns'] is not None:self.e.dns.recovery.snapshot(db,site,None,'account transfer',json.dumps(source['dns']))
                    if source['schedule']:
                        from .backup_policy import next_run
                        p=source['schedule'];due=next_run(int(time.time()),p['frequency'],p['hour'],p['weekday'],p['monthday'])
                        db.execute('INSERT INTO backup_schedules(site_id,user_id,frequency,hour,weekday,keep,enabled,next_run,monthday) VALUES(?,?,?,?,?,?,0,?,?)',(site['id'],owner['id'],p['frequency'],p['hour'],p['weekday'],p['keep'],due,p['monthday']))
                if self.e.nginx:
                    config=self.e.nginx/('vectorcp-site-%d.conf'%site['id'])
                    if config.exists() or config.is_symlink():raise Fault('A reserved web configuration already exists. It was preserved.',409)
                self.journal(ident,lambda j:j['configs'].append(site['id']))
                self.e.publish_config(site,'suspended')
                # Publish directory entries before clearing the recovery journal.
                for folder,dirs,files in os.walk(root,topdown=False):
                    descriptor=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:os.fsync(descriptor)
                    finally:os.close(descriptor)
                for parent in (root.parent,root.parent.parent):
                    descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:os.fsync(descriptor)
                    finally:os.close(descriptor)
            if any(s['runtime']!='static' for s in manifest['sites']) and not self.e.development:self.e.hosting.start_php(slot)
        self.update(ident,status='complete',journal='{}',message='Imported and verified. Websites are suspended, schedules paused and DNS records saved as recovery copies. Review before activation.')

    @staticmethod
    def remap_wordpress(path,credentials):
        content=path.read_text()
        replacements={'DB_NAME':credentials['name'],'DB_USER':credentials['username'],'DB_PASSWORD':credentials['password'],'DB_HOST':'localhost:'+credentials['socket']}
        for key,value in replacements.items():
            pattern=r"(?m)^define\('"+key+r"', '[^'\r\n]*'\);$"
            if len(re.findall(pattern,content))!=1:raise Fault('WordPress has a custom connection configuration. Use the documented managed format before transferring it.',409)
            content=re.sub(pattern,lambda m:"define('%s', '%s');"%(key,value),content)
        with path.open('w') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())

    def rollback(self,ident,owner):
        with self.e.db() as db:journal=json.loads(db.execute('SELECT journal FROM transfers WHERE id=?',(ident,)).fetchone()[0])
        slot=self.e.hosting.slot(owner)
        with self.e.hosting.paused(slot):
            for entry in journal.get('sites',[]):
                with self.e.db() as db:
                    site=db.execute('SELECT * FROM sites WHERE id=?',(entry['id'],)).fetchone()
                    if not site or site['user_id']!=owner['id'] or site['domain']!=entry['domain'] or site['created']!=entry['created'] or site['status']!='suspended':
                        raise Fault('The reserved website allocation changed. Owner inspection is required.',409)
                site=dict(site)
                if site['id'] in journal['configs'] and not self.e.development:
                    config=self.e.nginx/('vectorcp-site-%d.conf'%site['id'])
                    if config.is_symlink():raise Fault('Inspect an unexpected web configuration link.',409)
                    config.unlink(missing_ok=True)
                if site['id'] in journal['databases']:
                    name='site_%d'%site['id']
                    self.e.hosting.start_db(slot)
                    self.e.hosting.sql(slot,"DROP DATABASE IF EXISTS `%s`; DROP USER IF EXISTS '%s'@'localhost';"%(name,name))
                    (self.e.state/('hosting/database-%d.json'%site['id'])).unlink(missing_ok=True)
                if site['id'] in journal['files']:
                    root=self.e.site_root(site)
                    if root.parent.is_symlink():raise Fault('Inspect an unexpected website folder link.',409)
                    shutil.rmtree(root.parent,ignore_errors=False) if root.parent.exists() else None
            if journal.get('configs') and not self.e.development:
                from .hosting import command
                command(['/usr/sbin/nginx','-t']);command(['/usr/bin/systemctl','reload','nginx'])
            pause=journal.get('pause')
            if pause and pause.get('restore') and not self.e.development:
                if pause.get('slot')!=slot:raise Fault('The paused PHP allocation changed. Owner inspection is required.',409)
                from .hosting import command
                command(['/usr/bin/systemctl','reset-failed','vectorcp-php@'+slot])
                self.e.hosting.start_php(slot)
        # Files/services first, then rows atomically. A failed cleanup keeps
        # all allocation claims and the customer hold for owner recovery.
        with self.e.db() as db:
            for entry in journal.get('sites',[]):
                sid=entry['id']
                for table in ('backup_schedules','dns_snapshots','site_routing'):db.execute('DELETE FROM '+table+' WHERE site_id=?',(sid,))
                db.execute('DELETE FROM sites WHERE id=?',(sid,))
            db.execute("UPDATE transfers SET journal='{}',status='rolled_back',message='New allocations were removed and any recorded PHP maintenance stop restored. Accounts and unrelated data are preserved.',updated=? WHERE id=?",(int(time.time()),ident))
