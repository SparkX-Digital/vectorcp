"""Opt-in account/file workflow checks on the disposable Linux acceptance guest.

Requires the private fixtures produced by acceptance_linux.py. Run with
--before-upgrade before applying the new source, then without it afterwards.
Never run on a server containing real customers. Credentials are read privately
from generated test state and never printed. Verification accounts remain locked.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, '/opt/vectorcp')
from vectorcp.agent import rpc
from vectorcp.core import Fault

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--allow-disposable-host', action='store_true', required=True)
parser.add_argument('--before-upgrade', action='store_true')
parser.add_argument('--candidate-archive', type=Path, help='Optional reviewed source archive whose checksum should be recorded')
args = parser.parse_args()
if not sys.platform.startswith('linux') or os.geteuid() != 0:
    raise SystemExit('Run only as root on the disposable Linux acceptance guest.')

STATE = Path('/var/lib/vectorcp')
context = json.loads((STATE/'acceptance-context.json').read_text())
results = []

def record(name):
    results.append({'check': name, 'passed': True})
    print('PASS:', name, flush=True)

def call(who, method, data=None):
    return rpc('/run/vectorcp/agent.sock', {'method': method, 'data': data or {},
        'token': who['token'], 'csrf': who['csrf']})

def denied(status, who, method, data=None):
    try:
        call(who, method, data)
    except Fault as error:
        assert error.status == status, (method, error.status)
    else:
        raise AssertionError('Operation should have been refused: '+method)

def entry(who, site, path, hidden=False):
    folder, _, name = path.rpartition('/')
    return next(x for x in call(who, 'files.list', {'site_id': site, 'path': folder, 'show_hidden': hidden})['files'] if x['name']==name)

if args.before_upgrade:
    owner = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': context['owner_login']})
    saved = {'owner': owner, 'sites': call(owner, 'sites.list')['sites']}
    p = STATE/'security-pre-upgrade.json'
    p.write_text(json.dumps(saved)); p.chmod(0o600)
    print('Saved fresh owner session and website inventory privately.')
    raise SystemExit(0)

saved = json.loads((STATE/'security-pre-upgrade.json').read_text())
from vectorcp.security import totp
owner = saved['owner']
assert call(owner, 'sites.list')['sites'] == saved['sites']
record('Upgrade preserves existing authenticated owner session and website inventory')
assert len(call(owner, 'security.sessions')['sessions']) >= 1
record('Migrated sessions have a private device inventory')

username, password = 'qa_security_'+secrets.token_hex(4), secrets.token_urlsafe(24)
uid = call(owner, 'accounts.create', {'username': username, 'name': 'Native security fixture', 'password': password})['id']
user = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': password}})
other = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': password}})
call(user, 'security.revoke', {'id': 'others'})
denied(401, other, 'overview')
record('Remote session revocation works through the installed Linux agent')

factor = call(user, 'security.enroll', {'password': password})
step = int(time.time())//30
enrollment = call(user, 'security.confirm', {'password': password, 'verification_code': totp(factor['secret'], step)})
codes = enrollment['recovery_codes']
assert rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': password}}) == {'mfa_required': True}
signed = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': password, 'code': codes[0]}})
try:
    rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': password, 'code': codes[0]}})
except Fault as error:
    assert error.status == 401
else:
    raise AssertionError('Replayed recovery code was accepted')
record('Authenticator enrollment and one-use recovery sign-in work on Linux')

temporary, final = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
call(owner, 'accounts.password', {'id': uid, 'password': context['owner_login']['password'], 'new_password': temporary})
denied(401, signed, 'overview')
rotating = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': temporary, 'code': codes[1]}})
denied(403, rotating, 'sites.list')
assert call(rotating, 'overview')['user']['password_change_required']
call(rotating, 'security.password', {'password': temporary, 'new_password': final, 'code': codes[2]})
denied(401, rotating, 'overview')
user = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': {'username': username, 'password': final, 'code': codes[3]}})
assert not call(user, 'overview')['user']['password_change_required']
record('Temporary passwords restrict tools; password change revokes all sessions and preserves MFA')

call(user, 'profile.update', {'name': 'Verified native fixture', 'contact_email': 'native@example.com', 'password': final, 'code': codes[4]})
search = call(owner, 'accounts.list', {'query': 'native@example.com'})
assert any(x['id']==uid for x in search['accounts'])
details = call(owner, 'accounts.inspect', {'id': uid})
assert details['account']['name'] == 'Verified native fixture'
record('Account contact editing, scoped search and details work on the installed agent')

connection = http.client.HTTPConnection('127.0.0.1', 8765, timeout=15)
headers = {'Origin': 'http://127.0.0.1:8765', 'Content-Type': 'application/json', 'User-Agent': 'Native workflow acceptance'}
connection.request('POST', '/api', json.dumps({'method': 'login', 'data': {'username': username, 'password': final}}), headers)
response = connection.getresponse(); pending = json.loads(response.read())
assert response.status == 200 and pending == {'mfa_required': True}
assert response.getheader('Set-Cookie') is None
connection.close()
connection = http.client.HTTPConnection('127.0.0.1', 8765, timeout=15)
connection.request('POST', '/api', json.dumps({'method': 'login', 'data': {'username': username, 'password': final, 'code': codes[5]}}), headers)
response = connection.getresponse(); authenticated = json.loads(response.read())
assert response.status == 200 and 'token' not in authenticated
cookie = response.getheader('Set-Cookie')
assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
connection.close()
record('Installed HTTP frontend issues a private session cookie only after two-factor sign-in')

site = next(s for s in saved['sites'] if s['user_id'] == context['customers'][0]['user']['id'])
sid = site['id']
prefix = 'qa-files-'+secrets.token_hex(4)
call(owner, 'files.mkdir', {'site_id': sid, 'path': prefix})
call(owner, 'files.write', {'site_id': sid, 'path': prefix+'/index.html', 'content': 'VectorCP native file acceptance', 'revision': 'new'})
call(owner, 'files.write', {'site_id': sid, 'path': prefix+'/.settings', 'content': 'hidden fixture', 'revision': 'new', 'show_hidden': True})
copy = prefix+'-copy'
item = entry(owner, sid, prefix)
call(owner, 'files.copy', {'site_id': sid, 'path': prefix, 'destination': copy, 'revision': item['revision']})
assert call(owner, 'files.read', {'site_id': sid, 'path': copy+'/.settings', 'show_hidden': True})['content'] == 'hidden fixture'

connection = http.client.HTTPConnection('127.0.0.1', 80, timeout=10)
connection.request('GET', '/'+copy+'/index.html', headers={'Host': site['domain']})
response = connection.getresponse(); body = response.read(); connection.close()
assert response.status == 200, response.status
assert body == b'VectorCP native file acceptance'
record('Recursive copy preserves hidden content and Nginx serves copied files from isolated storage')

item = entry(owner, sid, prefix)
call(owner, 'files.archive.create', {'site_id': sid, 'path': prefix, 'revision': item['revision'], 'destination': prefix+'.zip'})
item = entry(owner, sid, prefix+'.zip')
call(owner, 'files.archive.extract', {'site_id': sid, 'path': prefix+'.zip', 'revision': item['revision'], 'destination': prefix+'-unpacked'})
assert call(owner, 'files.read', {'site_id': sid, 'path': prefix+'-unpacked/'+prefix+'/.settings', 'show_hidden': True})['content'] == 'hidden fixture'
denied(404, user, 'files.archive.extract', {'site_id': sid, 'path': prefix+'.zip', 'revision': item['revision'], 'destination': 'forged'})
record('ZIP creation/extraction preserves hidden contents and refuses unrelated customer access')

mode = call(owner, 'files.permissions', {'site_id': sid, 'path': copy+'/index.html'})
changed = call(owner, 'files.chmod', {'site_id': sid, 'path': copy+'/index.html', 'revision': mode['revision'], 'mode': '640'})
assert changed['mode'] == '640' and changed['isolated']
with sqlite3.connect(str(STATE/'control.sqlite3')) as db:
    slot = db.execute('SELECT hosting_slot FROM users WHERE id=?', (site['user_id'],)).fetchone()[0]
path = Path('/srv/vectorcp/accounts')/('%02d' % slot)/'sites'/str(sid)/'public'/copy/'index.html'
import pwd
assert path.stat().st_uid == pwd.getpwnam('vectorcp-c%02d' % slot).pw_uid
record('Permission editing retains the correct customer Unix identity')

item = entry(owner, sid, copy)
trash = call(owner, 'files.trash', {'site_id': sid, 'path': copy, 'revision': item['revision']})['id']
assert not path.parent.exists()
assert any(x['id']==trash for x in call(owner, 'files.trash.list', {'site_id': sid})['entries'])
subprocess.run(['/usr/bin/systemctl', 'restart', 'vectorcp-agent'], check=True)
for _ in range(30):
    try:
        rpc('/run/vectorcp/agent.sock', {'method': 'health'})
        break
    except (Fault, OSError):
        time.sleep(0.2)
call(owner, 'files.trash.restore', {'site_id': sid, 'id': trash})
assert path.read_bytes() == b'VectorCP native file acceptance'
record('Trash and undo survive an actual agent restart on customer storage')

for folder in (prefix, copy, prefix+'-unpacked', prefix+'.zip'):
    item = entry(owner, sid, folder)
    trash = call(owner, 'files.trash', {'site_id': sid, 'path': folder, 'revision': item['revision']})['id']
    call(owner, 'files.trash.purge', {'site_id': sid, 'id': trash})
call(owner, 'accounts.active', {'id': uid, 'active': False})
denied(401, user, 'overview')
record('Only newly created verification files were purged; verification account is locked')

assert subprocess.check_output(['/usr/sbin/getenforce'], text=True).strip() == 'Enforcing'
record('SELinux remains Enforcing')
output = {'candidate': 'Unreleased account/security/file workflows', 'results': results,
          'checks': len(results), 'python': sys.version.split()[0],
          'version': rpc('/run/vectorcp/agent.sock', {'method': 'health'})['version'],
          'runtime_files': {name: hashlib.sha256((Path('/opt/vectorcp/vectorcp')/name).read_bytes()).hexdigest()
                            for name in ('__init__.py', 'core.py', 'distribution.py', 'security.py', 'filetools.py', 'trash.py', 'archives.py', 'web.py', 'static/app.js', 'static/style.css')}}
if args.candidate_archive:
    output['candidate_sha256'] = hashlib.sha256(args.candidate_archive.read_bytes()).hexdigest()
(STATE/'security-acceptance-results.json').write_text(json.dumps(output, indent=2)+'\n')
print('All',len(results),'installed-service acceptance checks passed.')
