"""Portable account v1: bounded USTAR, checksummed files and untrusted SQL.

No archive member is extracted by tarfile. Extended headers and links are
rejected before the standard parser sees them, including compressed bombs.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tempfile
import zlib

from .core import DOMAIN, Fault, integer, text

MIB = 1024 ** 2
MAX_ARCHIVE = 350 * MIB
MAX_FILES = 12000
MAX_SITES = 10
MAX_MANIFEST = 2 * MIB
FILE_LIMIT = 16 * MIB
FILES_LIMIT = 200 * MIB
SQL_LIMIT = 64 * MIB
SQL_TOTAL = 128 * MIB
HEX = re.compile(r'[0-9a-f]{64}')


def checksum(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(262144), b''):
            result.update(block)
    return result.hexdigest()


def path_name(value):
    if (not isinstance(value,str) or not value or len(value.encode())>240 or
            value.startswith('/') or '\\' in value or
            any(ord(c)<32 or ord(c)==127 for c in value) or
            any(part in ('','.','..') for part in value.split('/'))):
        raise Fault('The transfer contains an unsafe or unsupported path.')
    return value


def metadata(value):
    """Validate only a documented format, never serialize account internals."""
    from .dns_recovery import parse as dns_records
    from .routing import validate_rules, ERROR_CODES
    if (not isinstance(value,dict) or set(value)!={'format','version','account','sites'} or value.get('format')!='vectorcp-account' or
            type(value.get('version')) is not int or value['version']!=1):
        raise Fault('Choose a portable VectorCP account v1 archive.')
    account=value.get('account')
    if not isinstance(account,dict) or set(account)!={'username','name'}:
        raise Fault('The account description is invalid.')
    text(account['username'],'source username',32);text(account['name'],'source name',80)
    sites=value.get('sites')
    if not isinstance(sites,list) or not 1<=len(sites)<=MAX_SITES:
        raise Fault('A transfer supports 1–10 websites.')
    domains=set();files_total=sql_total=entries=0
    for site in sites:
        if not isinstance(site,dict) or set(site)!={'domain','runtime','wordpress_version','files','directories','database','dns','routing','schedule'}:
            raise Fault('A transferred website has invalid metadata.')
        domain=site['domain']
        if not isinstance(domain,str) or len(domain)>253 or not DOMAIN.fullmatch(domain) or domain.endswith(('.local','.localhost')) or domain!=domain.lower() or domain in domains:
            raise Fault('The transfer contains an invalid or repeated domain.')
        domains.add(domain)
        if site['runtime'] not in ('static','php','wordpress') or (site['wordpress_version'] is not None and (not isinstance(site['wordpress_version'],str) or not re.fullmatch(r'[0-9.]{1,30}',site['wordpress_version']))):
            raise Fault('The website runtime is unsupported.')
        files,dirs=site['files'],site['directories']
        if not isinstance(files,dict) or not isinstance(dirs,list) or len(files)+len(dirs)>MAX_FILES:
            raise Fault('The website entry inventory is invalid.')
        entries+=len(files)+len(dirs)
        if entries>MAX_FILES:raise Fault('The transfer entry limit is exceeded.')
        paths=set()
        for path,record in files.items():
            path_name(path)
            if not isinstance(record,dict) or set(record)!={'bytes','sha256'} or not isinstance(record['sha256'],str) or not HEX.fullmatch(record['sha256']):
                raise Fault('A file checksum is invalid.')
            files_total+=integer(record['bytes'],'file bytes',0,FILE_LIMIT)
            paths.add(path)
        for path in dirs:
            path_name(path)
            if path in paths:raise Fault('The transfer repeats a file or folder.')
            paths.add(path)
        for path in paths:
            if any(str(parent) in files for parent in PurePosixPath(path).parents if str(parent)!='.'):
                raise Fault('A file conflicts with a transferred folder.')
        database=site['database']
        if database is not None:
            if not isinstance(database,dict) or set(database)!={'bytes','sha256'} or not isinstance(database['sha256'],str) or not HEX.fullmatch(database['sha256']):
                raise Fault('The SQL inventory is invalid.')
            sql_total+=integer(database['bytes'],'SQL bytes',1,SQL_LIMIT)
        if site['runtime']=='wordpress' and (database is None or 'wp-config.php' not in files):
            raise Fault('A WordPress transfer requires its configuration and database.')
        if site['dns'] is not None:
            dns_records(json.dumps(site['dns']),domain)
        routing=site['routing']
        if not isinstance(routing,dict) or set(routing)!={'redirects','error_pages'}:
            raise Fault('The routing description is invalid.')
        validate_rules(routing['redirects'],domain)
        pages=routing['error_pages']
        if not isinstance(pages,dict) or any(k not in {str(c) for c in ERROR_CODES} for k in pages):
            raise Fault('The error-page inventory is invalid.')
        for path in pages.values():
            path_name(path)
            if not re.fullmatch(r'[A-Za-z0-9_/-]+\.html',path) or path not in files or files[path]['bytes']>2*MIB:
                raise Fault('Transferred error pages must be existing plain HTML files.')
        schedule=site['schedule']
        if schedule is not None:
            if not isinstance(schedule,dict) or set(schedule)!={'frequency','hour','weekday','monthday','keep'} or schedule['frequency'] not in ('daily','weekly','monthly'):
                raise Fault('The backup schedule is invalid.')
            for key,low,high in [('hour',0,23),('weekday',0,6),('monthday',1,31),('keep',1,4)]:integer(schedule[key],key,low,high)
    if files_total>FILES_LIMIT or sql_total>SQL_TOTAL:
        raise Fault('Transfer limit: 200 MB of website files and 128 MB of SQL in total.')
    return value


def add_bytes(archive,name,payload):
    path_name(name)
    info=tarfile.TarInfo(name);info.size=len(payload);info.mode=0o600
    archive.addfile(info,io.BytesIO(payload))


def snapshot_files(engine,root,archive,prefix,budget):
    files,folders={},[]
    def walk(fd,relative):
        names=[]
        with os.scandir(fd) as iterator:
            for item in iterator:
                names.append(item.name)
                if len(names)+budget['entries']>MAX_FILES:raise Fault('The transfer entry limit is exceeded.')
        for name in sorted(names):
            path='/'.join(p for p in (relative,name) if p)
            path_name(prefix+'/'+path)
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            budget['entries']+=1
            if budget['entries']>MAX_FILES:raise Fault('A transfer supports up to 12,000 file and folder entries.')
            if stat.S_ISDIR(info.st_mode):
                folders.append(path)
                member=tarfile.TarInfo(prefix+'/'+path);member.type=tarfile.DIRTYPE;member.mode=0o700
                archive.addfile(member)
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:walk(child,path)
                finally:os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:
                with os.fdopen(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd),'rb') as source:
                    before=os.fstat(source.fileno())
                    payload=source.read(FILE_LIMIT+1)
                    after=os.fstat(source.fileno())
                budget['bytes']+=len(payload)
                if (before.st_ino!=info.st_ino or before.st_dev!=info.st_dev or before.st_nlink!=1 or
                        before.st_size!=len(payload) or after.st_nlink!=1 or after.st_mtime_ns!=before.st_mtime_ns or after.st_size!=before.st_size):
                    raise Fault('Website files changed during export. Stop external writers and retry.',409)
                if len(payload)>FILE_LIMIT or budget['bytes']>FILES_LIMIT:
                    raise Fault('Transfer files support 16 MB each and 200 MB in total.',409)
                add_bytes(archive,prefix+'/'+path,payload)
                files[path]={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
            else:
                raise Fault('Remove symbolic/hard links and special files before exporting this account.',409)
    with engine.directory(root) as descriptor:walk(descriptor,'')
    return files,folders


def scan_headers(stream):
    """Refuse extension blocks and oversized headers before tarfile allocation."""
    count=0
    def number(raw):
        raw=raw.strip(b'\0 ')
        if not raw or not re.fullmatch(b'[0-7]{1,12}',raw):raise Fault('Invalid transfer TAR header.')
        return int(raw,8)
    while True:
        header=stream.read(512)
        if len(header)!=512:raise Fault('The transfer TAR is incomplete.')
        if header==b'\0'*512:
            if stream.read(512)!=b'\0'*512:raise Fault('The transfer TAR terminator is invalid.')
            while True:
                block=stream.read(262144)
                if not block:break
                if block.strip(b'\0'):raise Fault('Unexpected content after the transfer TAR.')
            break
        count+=1
        if count>MAX_FILES+MAX_SITES+1:raise Fault('The transfer entry limit is exceeded.')
        if header[257:263]!=b'ustar\0' or header[156:157] not in (b'0',b'\0',b'5'):
            raise Fault('Use plain USTAR files and folders, without links or extended headers.')
        if number(header[148:156])!=sum(header[:148])+256+sum(header[156:]):
            raise Fault('A transfer TAR header checksum does not match.')
        size=number(header[124:136])
        if size>SQL_LIMIT or (header[156:157]==b'5' and size):raise Fault('A transfer entry exceeds its limit.')
        stream.seek((size+511)//512*512,1)
    stream.seek(0)


@contextlib.contextmanager
def opened(path,staging):
    try:
        with tempfile.TemporaryFile(dir=staging) as raw:
            # Bound both input and output without the unbounded Python gzip
            # filename-header reader. Exactly one gzip member is supported.
            decoder=zlib.decompressobj(31)
            with Path(path).open('rb') as source:
                total=0
                while True:
                    chunk=source.read(262144)
                    if not chunk:break
                    while chunk:
                        block=decoder.decompress(chunk,262144)
                        chunk=decoder.unconsumed_tail
                        total+=len(block)
                        if total>MAX_ARCHIVE:raise Fault('The expanded transfer exceeds 350 MB.')
                        raw.write(block)
                        if decoder.eof:
                            if decoder.unused_data or source.read(1):raise Fault('Use a single gzip member without trailing content.')
                            break
                    if decoder.eof:break
                if not decoder.eof:raise Fault('The compressed transfer is incomplete.')
            raw.seek(0);scan_headers(raw)
            with tarfile.open(fileobj=raw,mode='r:',encoding='utf8',errors='strict') as archive:
                members={}
                for member in archive:
                    name=member.name.rstrip('/') if member.isdir() else member.name
                    path_name(name)
                    if name in members:raise Fault('The transfer repeats an archive entry.')
                    members[name]=member
                item=members.get('account/manifest.json')
                if not item or not item.isfile() or item.size>MAX_MANIFEST:raise Fault('A bounded transfer manifest is required.')
                def unique(pairs):
                    result={}
                    for key,value in pairs:
                        if key in result:raise Fault('The transfer manifest repeats a JSON key.')
                        result[key]=value
                    return result
                value=metadata(json.load(archive.extractfile(item),object_pairs_hook=unique))
                expected={'account/manifest.json'}
                for index,site in enumerate(value['sites']):
                    prefix='account/sites/%d/'%index
                    for path in site['directories']:
                        name=prefix+'public/'+path;expected.add(name)
                        if name not in members or not members[name].isdir():raise Fault('A transferred folder is missing.')
                    inventory={prefix+'public/'+p:r for p,r in site['files'].items()}
                    if site['database'] is not None:inventory[prefix+'database.sql']=site['database']
                    for name,record in inventory.items():
                        expected.add(name);item=members.get(name)
                        if not item or not item.isfile() or item.size!=record['bytes']:raise Fault('A transferred file is missing or has changed size.')
                        result=hashlib.sha256()
                        with archive.extractfile(item) as source:
                            for block in iter(lambda:source.read(262144),b''):result.update(block)
                        if result.hexdigest()!=record['sha256']:raise Fault('A transferred file checksum does not match.')
                if set(members)!=expected:raise Fault('The transfer contains files outside its declared inventory.')
                yield archive,value
    except (OSError,EOFError,zlib.error,tarfile.TarError,ValueError,KeyError,TypeError,UnicodeError,RecursionError):
        raise Fault('The transfer archive is invalid, corrupt or unsupported.')
