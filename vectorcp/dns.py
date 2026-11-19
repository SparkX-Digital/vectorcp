"""Scoped DNS editing with private preview or explicitly activated public zones."""
import ipaddress
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time
from .core import DOMAIN, Fault, integer, text

TYPES = ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'CAA', 'SRV')
LABEL = re.compile(r'(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?)\Z')


def fqdn(value):
    val = text(value, 'DNS target', 254).lower().rstrip('.')
    if not DOMAIN.fullmatch(val):
        raise Fault('Use a full DNS target name, such as mail.example.com.')
    return val + '.'


def validate(data):
    name = text(data.get('name', '@'), 'record name', 253).lower().rstrip('.')
    if name not in ('@','*') and (not name or any(not LABEL.fullmatch(l) for l in name.removeprefix('*.').split('.'))):
        raise Fault('Use @ for the zone root or a relative record name.')
    if name == '*' or name.startswith('*.'):
        if name != '*' and any(not LABEL.fullmatch(l) for l in name[2:].split('.')):
            raise Fault('Invalid wildcard record.')
    # A bare * needs a special case because it is not an ordinary label.
    typ = data.get('type')
    if typ not in TYPES:
        raise Fault('Unsupported DNS record type.')
    ttl = integer(data.get('ttl', 3600), 'record TTL', 300, 86400)
    value = text(data.get('value'), 'record value', 512)
    if typ in ('A', 'AAAA'):
        try:
            addr = ipaddress.ip_address(value)
        except ValueError:
            raise Fault('Use a valid IP address.')
        if addr.version != (4 if typ == 'A' else 6):
            raise Fault('The IP address does not match the record type.')
        value = str(addr)
    elif typ in ('CNAME', 'NS'):
        value = fqdn(value)
        if typ == 'CNAME' and name == '@':
            raise Fault('A zone root cannot be a CNAME.')
        if typ == 'NS' and name == '@':
            raise Fault('The zone root nameservers are managed by the server owner.')
    elif typ == 'MX':
        parts = value.split()
        if len(parts) != 2 or not parts[0].isdigit() or not 0 <= int(parts[0]) <= 65535:
            raise Fault('Use an MX priority and hostname, for example 10 mail.example.com.')
        value = str(int(parts[0])) + ' ' + fqdn(parts[1])
    elif typ == 'SRV':
        parts = value.split()
        if len(parts) != 4 or any(not x.isdigit() or not 0 <= int(x) <= 65535 for x in parts[:3]):
            raise Fault('Use priority, weight, port and hostname for an SRV record.')
        value = ' '.join(str(int(x)) for x in parts[:3]) + ' ' + fqdn(parts[3])
    elif typ == 'CAA':
        parts = value.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit() or not 0 <= int(parts[0]) <= 255 or parts[1] not in ('issue', 'issuewild', 'iodef'):
            raise Fault('Use CAA flags, tag and value, for example 0 issue letsencrypt.org.')
        payload = parts[2].strip('"')
        if not payload or any(ord(c) < 32 or ord(c) > 126 for c in payload):
            raise Fault('Invalid CAA value.')
        value = str(int(parts[0])) + ' ' + parts[1] + ' ' + json.dumps(payload)
    else:
        if len(value.encode()) > 255 or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise Fault('Use printable text up to 255 bytes for TXT records.')
        value = json.dumps(value)
    return {'name': name, 'type': typ, 'ttl': ttl, 'value': value}


OPERATIONS = {'dns.list', 'dns.export', 'dns.create', 'dns.save', 'dns.update',
              'dns.delete', 'dns.verify', 'dns.activate', 'dns.deactivate',
              'dns.diagnostics', 'dns.rebuild'}
READ_ONLY = {'dns.list', 'dns.export'}
RESOLVERS = ('1.1.1.1', '8.8.8.8')


def render_zone(db, site_id, service, public_ipv4):
    zone = db.execute('SELECT z.*,s.domain FROM dns_zones z JOIN sites s ON s.id=z.site_id WHERE site_id=?', (site_id,)).fetchone()
    domain = zone['domain'] + '.'
    names = service['nameservers'] if service['mode'] == 'public' else ['ns1.' + zone['domain']]
    result = ['$ORIGIN ' + domain, '$TTL 3600',
              '@ IN SOA %s. hostmaster.%s ( %d 3600 900 1209600 300 )' % (names[0], domain, zone['serial'])]
    result.extend('@ IN NS ' + ns + '.' for ns in names)
    if service['mode'] == 'private':
        if not public_ipv4:
            raise Fault('Configure the server public IPv4 before rebuilding or exporting private previews.', 409)
        result.append('ns1 IN A ' + public_ipv4)
    elif zone['published']:
        result.append('_vectorcp 300 IN TXT ' + json.dumps(zone['challenge']))
    for record in db.execute('SELECT * FROM dns_records WHERE site_id=? ORDER BY name,type,id', (site_id,)):
        result.append('%s %d IN %s %s' % (record['name'], record['ttl'], record['type'], record['value']))
    return '\n'.join(result) + '\n'


class DNS:
    def __init__(self, engine):
        self.e = engine
        self.config = engine.state / 'dns-preview' if engine.development else Path('/etc/vectorcp/dns')
        self.zones = engine.state / 'dns-zones' if engine.development else Path('/var/named/vectorcp')
        with engine.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS dns_zones (
              site_id INTEGER PRIMARY KEY REFERENCES sites(id), serial INTEGER NOT NULL,
              challenge TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, checked INTEGER, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS dns_records (
              id INTEGER PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES dns_zones(site_id),
              name TEXT NOT NULL,type TEXT NOT NULL,ttl INTEGER NOT NULL,value TEXT NOT NULL,
              UNIQUE(site_id,name,type,value));
            ''')
            if 'published' not in {r[1] for r in db.execute('PRAGMA table_info(dns_zones)')}:
                db.execute('ALTER TABLE dns_zones ADD COLUMN published INTEGER NOT NULL DEFAULT 0')

    @property
    def enabled(self):
        return self.e.development or (self.config / 'installed.json').exists()

    @property
    def profile(self):
        from .dns_profile import load
        return load(self.config / 'installed.json', self.e.development)

    def render(self, db, site_id):
        return render_zone(db, site_id, self.profile, self.e.public_ipv4)

    def run(self, args):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise Fault('The DNS service command did not finish. Contact the server administrator.', 503)
        if result.returncode:
            raise Fault('DNS validation or reload failed. The previous configuration was retained.', 503)
        return result.stdout

    def ownership(self, domain, challenge):
        if self.e.development:
            raise Fault('Public ownership checks are unavailable locally.', 409)
        matches = []
        for resolver in RESOLVERS:
            try:
                answer = self.run(['/usr/bin/dig', '@' + resolver, '_vectorcp.' + domain,
                                   'TXT', '+short', '+time=1', '+tries=1'])
            except Fault:
                matches.append(False)
            else:
                matches.append(any(line.strip() == json.dumps(challenge) for line in answer.splitlines()))
        return all(matches)

    def probe(self, domain, tcp=False):
        answer = self.run(['/usr/bin/dig', '@127.0.0.1', domain, 'SOA', '+norecurse',
                           '+noall', '+comments', '+answer', '+time=1', '+tries=1'] + (['+tcp'] if tcp else []))
        header = re.search(r'status: ([A-Z]+)', answer)
        flags = re.search(r';; flags: ([^;]*);', answer)
        serial = None
        for line in answer.splitlines():
            parts = line.split()
            if len(parts) >= 7 and parts[0].lower() == domain.lower() + '.' and parts[3] == 'SOA' and parts[6].isdigit():
                serial = int(parts[6])
        return {'transport': 'TCP' if tcp else 'UDP', 'status': header[1] if header else 'UNKNOWN',
                'authoritative': bool(flags and 'aa' in flags[1].split()), 'serial': serial}

    def diagnostics(self, site, zone):
        if self.e.development:
            return {'local': [], 'resolvers': [], 'note': 'Network diagnostics require the installed Linux service.'}
        local, recursive = [], []
        service = self.profile
        for tcp in (False, True):
            try:
                local.append(self.probe(site['domain'], tcp))
            except Fault:
                local.append({'transport': 'TCP' if tcp else 'UDP', 'error': 'The local DNS service did not answer.'})
        for resolver in RESOLVERS:
            try:
                answer = self.run(['/usr/bin/dig', '@' + resolver, site['domain'], 'NS', '+short', '+time=1', '+tries=1'])
                names = sorted({line.lower().rstrip('.') for line in answer.splitlines() if DOMAIN.fullmatch(line.lower().rstrip('.'))})
                recursive.append({'resolver': resolver, 'nameservers': names,
                                  'matches': names == sorted(service['nameservers']) if service['mode'] == 'public' else False})
            except Fault:
                recursive.append({'resolver': resolver, 'error': 'This resolver did not answer.'})
        return {'local': local, 'resolvers': recursive, 'expected_serial': zone['serial'],
                'nameservers': service['nameservers'],
                'note': 'Recursive answers may be cached. These checks do not prove parent delegation or external port reachability.'}

    def write(self, path, payload):
        temporary = path.with_suffix(path.suffix + '.new')
        temporary.write_text(payload)
        temporary.chmod(0o640)
        if not self.e.development:
            import grp
            os.chown(temporary, 0, grp.getgrnam('named').gr_gid)
        os.replace(temporary, path)
        if not self.e.development:
            self.run(['/usr/sbin/restorecon', str(path)])

    def publish(self, db, site):
        self.check_nameservers(db, site)
        self.config.mkdir(parents=True, exist_ok=True)
        self.zones.mkdir(parents=True, exist_ok=True)
        target = self.zones / ('site-%d.zone' % site['id'])
        config = self.config / 'zones.conf'
        old = {p: p.read_text() if p.exists() else None for p in (target, config)}
        try:
            self.write(target, self.render(db, site['id']))
            query = 'SELECT s.id,s.domain FROM dns_zones z JOIN sites s ON s.id=z.site_id'
            if self.profile['mode'] == 'public':
                query += ' WHERE z.published=1'
            entries = ['zone "%s" { type master; file "%s"; allow-transfer { none; }; allow-update { none; }; };' %
                       (z['domain'], self.zones / ('site-%d.zone' % z['id']))
                       for z in db.execute(query + ' ORDER BY s.id')]
            self.write(config, '\n'.join(entries) + '\n')
            if not self.e.development:
                self.run(['/usr/sbin/named-checkzone', site['domain'], str(target)])
                self.run(['/usr/sbin/named-checkconf', '-z', str(self.config / 'named.conf')])
                self.run(['/usr/bin/systemctl', 'reload', 'vectorcp-dns'])
                zone = db.execute('SELECT * FROM dns_zones WHERE site_id=?', (site['id'],)).fetchone()
                active = self.profile['mode'] == 'private' or zone['published']
                for tcp in (False, True):
                    for attempt in range(5):
                        answer = self.probe(site['domain'], tcp)
                        matches = answer['authoritative'] and answer['serial'] == zone['serial'] if active else answer['serial'] is None
                        if matches:
                            break
                        time.sleep(0.1)
                    else:
                        raise Fault('The DNS service did not confirm the zone state over UDP and TCP.', 503)
        except Exception:
            for path, content in old.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    self.write(path, content)
            if not self.e.development:
                with contextlib.suppress(Exception):
                    subprocess.run(['/usr/bin/systemctl', 'reload', 'vectorcp-dns'], capture_output=True, timeout=15, check=False)
            raise

    @staticmethod
    def check_serial(zone, data):
        serial = integer(data.get('serial'), 'zone serial', 0, 4294967295)
        if serial != zone['serial']:
            raise Fault('This DNS zone changed. Refresh before saving.', 409)

    def check_nameservers(self, db, site):
        zone = db.execute('SELECT published FROM dns_zones WHERE site_id=?', (site['id'],)).fetchone()
        if self.profile['mode'] != 'public' or not zone or not zone['published']:
            return
        for ns in self.profile['nameservers']:
            relative = '@' if ns == site['domain'] else ns[:-(len(site['domain']) + 1)] if ns.endswith('.' + site['domain']) else None
            if relative is not None and not db.execute("SELECT 1 FROM dns_records WHERE site_id=? AND name=? AND type IN ('A','AAAA')", (site['id'], relative)).fetchone():
                raise Fault('Keep an A or AAAA address for each nameserver inside an active zone.', 409)

    def dispatch(self, db, actor, method, data):
        if self.e.development or method in READ_ONLY:
            return self.operation(db, actor, method, data)
        import fcntl
        with open('/var/lib/vectorcp/profile-maintenance.lock', 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Fault('The DNS service profile is being maintained. Try again when it finishes.', 409)
            return self.operation(db, actor, method, data)

    def operation(self, db, actor, method, data):
        site = self.e.owned_site(db, actor, data.get('site_id'))
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        zone = db.execute('SELECT * FROM dns_zones WHERE site_id=?', (site['id'],)).fetchone()
        service = self.profile
        if method == 'dns.list':
            records = [dict(r) for r in db.execute('SELECT * FROM dns_records WHERE site_id=? ORDER BY name,type,id', (site['id'],))]
            return {'enabled': self.enabled, 'can_edit': self.e.distribution.features(db, owner)['dns'],
                    'mode': service['mode'], 'nameservers': service['nameservers'],
                    'zone': dict(zone) if zone else None, 'domain': site['domain'], 'records': records}
        if method == 'dns.export':
            if not zone:
                raise Fault('Create this DNS zone first.', 409)
            return {'filename': site['domain'] + '.zone', 'content': self.render(db, site['id'])}
        self.e.distribution.require_feature(db, owner, 'dns')
        from .distribution import available
        if not available(db, owner):
            raise Fault('This customer or its reseller is locked.', 409)
        self.e.site_idle(db, site)
        if not self.e.development and Path('/run/vectorcp-profile-maintenance').exists():
            raise Fault('The DNS service profile is being maintained. Try again when it finishes.', 409)
        if not self.enabled:
            raise Fault('The DNS service is not installed.', 409)
        if method == 'dns.create':
            if not self.e.public_ipv4:
                raise Fault('Configure the server public IP before creating DNS zones.', 409)
            if zone:
                raise Fault('This DNS zone already exists.', 409)
            if db.execute('SELECT COUNT(*) FROM dns_zones').fetchone()[0] >= 256:
                raise Fault('This server has reached its 256-zone limit.', 409)
            db.execute('INSERT INTO dns_zones(site_id,serial,challenge,created) VALUES(?,?,?,?)',
                       (site['id'], int(time.time()), 'vectorcp-' + secrets.token_urlsafe(24), int(time.time())))
            db.execute("INSERT INTO dns_records(site_id,name,type,ttl,value) VALUES(?,'@','A',3600,?)", (site['id'], self.e.public_ipv4))
        elif not zone:
            raise Fault('Create this DNS zone first.', 409)
        elif method == 'dns.verify':
            valid = self.ownership(site['domain'], zone['challenge'])
            db.execute('UPDATE dns_zones SET verified=?,checked=? WHERE site_id=?', (int(valid), int(time.time()), site['id']))
            self.e.log(db, actor, 'dns.ownership_checked', site['domain'])
            return {'ok': True, 'verified': valid}
        elif method == 'dns.diagnostics':
            result = self.diagnostics(site, zone)
            self.e.log(db, actor, 'dns.diagnostics', site['domain'])
            return result
        elif method in ('dns.activate', 'dns.deactivate'):
            if service['mode'] != 'public':
                raise Fault('The server owner must configure the public DNS profile first.', 409)
            if data.get('confirm_domain') != site['domain']:
                raise Fault('Type the exact domain to confirm the public DNS change.', 409)
            self.check_serial(zone, data)
            activating = method == 'dns.activate'
            if bool(zone['published']) == activating:
                raise Fault('The public zone state already changed. Refresh before continuing.', 409)
            if activating:
                if not self.ownership(site['domain'], zone['challenge']):
                    raise Fault('Both public resolvers must return the current ownership TXT record before activation.', 409)
                db.execute('UPDATE dns_zones SET verified=1,checked=? WHERE site_id=?', (int(time.time()), site['id']))
            db.execute('UPDATE dns_zones SET published=?,serial=(serial+1)%4294967296 WHERE site_id=?', (int(activating), site['id']))
        elif method in ('dns.save', 'dns.update'):
            if method == 'dns.save' and db.execute('SELECT COUNT(*) FROM dns_records WHERE site_id=?', (site['id'],)).fetchone()[0] >= 100:
                raise Fault('This zone has reached its 100-record limit.', 409)
            if 'serial' in data or method == 'dns.update':
                self.check_serial(zone, data)
            record = validate(data)
            if service['mode'] == 'private' and record['name'] == 'ns1':
                raise Fault('The private preview nameserver address is managed by VectorCP.')
            if record['name'] == '_vectorcp':
                raise Fault('The ownership TXT record is generated for active public zones. Before activation, add it at your current DNS provider.')
            record_id = None
            if method == 'dns.update':
                record_id = integer(data.get('id'), 'DNS record', 1, 2147483647)
                if not db.execute('SELECT 1 FROM dns_records WHERE id=? AND site_id=?', (record_id, site['id'])).fetchone():
                    raise Fault('DNS record not found.', 404)
            conflicting = db.execute('SELECT type FROM dns_records WHERE site_id=? AND name=? AND id!=?', (site['id'], record['name'], record_id or -1)).fetchall()
            if conflicting and (record['type'] == 'CNAME' or any(r[0] == 'CNAME' for r in conflicting)):
                raise Fault('A CNAME must be the only record at its name.', 409)
            try:
                if record_id:
                    db.execute('UPDATE dns_records SET name=?,type=?,ttl=?,value=? WHERE id=?', (record['name'], record['type'], record['ttl'], record['value'], record_id))
                else:
                    db.execute('INSERT INTO dns_records(site_id,name,type,ttl,value) VALUES(?,?,?,?,?)', (site['id'], record['name'], record['type'], record['ttl'], record['value']))
            except sqlite3.IntegrityError:
                raise Fault('This DNS record already exists.', 409)
            db.execute('UPDATE dns_zones SET serial=(serial+1)%4294967296 WHERE site_id=?', (site['id'],))
        elif method == 'dns.delete':
            if 'serial' in data:
                self.check_serial(zone, data)
            record = db.execute('SELECT * FROM dns_records WHERE id=? AND site_id=?', (integer(data.get('id'), 'DNS record', 1, 2147483647), site['id'])).fetchone()
            if not record:
                raise Fault('DNS record not found.', 404)
            db.execute('DELETE FROM dns_records WHERE id=?', (record['id'],))
            db.execute('UPDATE dns_zones SET serial=(serial+1)%4294967296 WHERE site_id=?', (site['id'],))
        elif method == 'dns.rebuild':
            self.check_serial(zone, data)
            db.execute('UPDATE dns_zones SET serial=(serial+1)%4294967296 WHERE site_id=?', (site['id'],))
        else:
            raise Fault('Unknown DNS operation.', 404)
        self.publish(db, site)
        self.e.log(db, actor, method, site['domain'])
        return {'ok': True}
