"""Bounded DNS zone editing with private authoritative BIND validation.

This release listens only on loopback. Exported zones can be used at the
customer's existing DNS provider; editing here does not change public DNS.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
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
            raise Fault('The private preview nameserver record is managed by VectorCP.')
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


class DNS:
    def __init__(self, engine):
        self.e = engine
        self.config = engine.state/'dns-preview' if engine.development else Path('/etc/veyrapanel/dns')
        self.zones = engine.state/'dns-zones' if engine.development else Path('/var/named/veyrapanel')
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

    @property
    def enabled(self):
        return self.e.development or (self.config/'installed.json').exists()

    def render(self, db, site_id):
        zone = db.execute('SELECT z.*,s.domain FROM dns_zones z JOIN sites s ON s.id=z.site_id WHERE site_id=?', (site_id,)).fetchone()
        domain = zone['domain'] + '.'
        result = ['$ORIGIN ' + domain, '$TTL 3600', '@ IN SOA ns1.' + domain + ' hostmaster.' + domain + ' ( ' + str(zone['serial']) + ' 3600 900 1209600 300 )',
                  '@ IN NS ns1.' + domain, 'ns1 IN A ' + self.e.public_ipv4]
        for r in db.execute('SELECT * FROM dns_records WHERE site_id=? ORDER BY name,type,id', (site_id,)):
            result.append('%s %d IN %s %s' % (r['name'], r['ttl'], r['type'], r['value']))
        return '\n'.join(result) + '\n'

    def run(self, args):
        p = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        if p.returncode:
            raise Fault('DNS validation or reload failed. The previous configuration was retained.', 503)
        return p.stdout

    def write(self, path, payload):
        tmp = path.with_suffix(path.suffix + '.new')
        tmp.write_text(payload)
        tmp.chmod(0o640)
        if not self.e.development:
            import grp
            os.chown(tmp, 0, grp.getgrnam('named').gr_gid)
        os.replace(tmp, path)
        if not self.e.development:
            self.run(['/usr/sbin/restorecon', str(path)])

    def publish(self, db, site):
        self.config.mkdir(parents=True, exist_ok=True)
        self.zones.mkdir(parents=True, exist_ok=True)
        target = self.zones/('site-%d.zone' % site['id'])
        config = self.config/'zones.conf'
        old = {p: p.read_text() if p.exists() else None for p in (target, config)}
        try:
            self.write(target, self.render(db, site['id']))
            entries = []
            for z in db.execute('SELECT s.id,s.domain FROM dns_zones z JOIN sites s ON s.id=z.site_id ORDER BY s.id'):
                entries.append('zone "%s" { type master; file "%s"; allow-transfer { none; }; allow-update { none; }; };' % (z['domain'], self.zones/('site-%d.zone' % z['id'])))
            self.write(config, '\n'.join(entries) + '\n')
            if not self.e.development:
                self.run(['/usr/sbin/named-checkzone', site['domain'], str(target)])
                self.run(['/usr/sbin/named-checkconf', '-z', str(self.config/'named.conf')])
                self.run(['/usr/bin/systemctl', 'reload', 'veyra-dns'])
                serial = db.execute('SELECT serial FROM dns_zones WHERE site_id=?', (site['id'],)).fetchone()[0]
                for _ in range(20):
                    answer = self.run(['/usr/bin/dig', '@127.0.0.1', site['domain'], 'SOA', '+short', '+time=1', '+tries=1']).split()
                    if len(answer) > 2 and answer[2] == str(serial):
                        break
                    time.sleep(0.1)
                else:
                    raise Fault('The DNS service did not confirm the new zone serial.', 503)
        except Exception:
            for p, content in old.items():
                if content is None:
                    p.unlink(missing_ok=True)
                else:
                    self.write(p, content)
            if not self.e.development:
                subprocess.run(['/usr/bin/systemctl','reload','veyra-dns'], capture_output=True, timeout=15, check=False)
            raise

    def dispatch(self, db, actor, method, data):
        site = self.e.owned_site(db, actor, data.get('site_id'))
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        zone = db.execute('SELECT * FROM dns_zones WHERE site_id=?', (site['id'],)).fetchone()
        if method == 'dns.list':
            records = [dict(r) for r in db.execute('SELECT * FROM dns_records WHERE site_id=? ORDER BY name,type,id', (site['id'],))]
            return {'enabled':self.enabled, 'can_edit':self.e.distribution.features(db, owner)['dns'], 'mode':'private', 'zone':dict(zone) if zone else None, 'domain':site['domain'], 'records':records}
        if method == 'dns.export':
            if not zone:
                raise Fault('Create this DNS zone first.', 409)
            return {'filename':site['domain']+'.zone', 'content':self.render(db, site['id'])}
        self.e.distribution.require_feature(db, owner, 'dns')
        if not self.enabled:
            raise Fault('The private DNS service is not installed.', 409)
        if not self.e.public_ipv4:
            raise Fault('Configure the server’s public IP before creating DNS zones.', 409)
        if method == 'dns.create':
            if zone:
                raise Fault('This DNS zone already exists.', 409)
            if db.execute('SELECT COUNT(*) FROM dns_zones').fetchone()[0] >= 256:
                raise Fault('This server has reached its 256-zone limit.', 409)
            db.execute('INSERT INTO dns_zones(site_id,serial,challenge,created) VALUES(?,?,?,?)', (site['id'], int(time.time()), 'veyra-'+secrets.token_urlsafe(24), int(time.time())))
            db.execute("INSERT INTO dns_records(site_id,name,type,ttl,value) VALUES(?,'@','A',3600,?)", (site['id'],self.e.public_ipv4))
        elif not zone:
            raise Fault('Create this DNS zone first.', 409)
        elif method == 'dns.verify':
            if self.e.development:
                raise Fault('Public ownership checks are unavailable locally.', 409)
            # Ask an independent resolver, never our own un-delegated preview.
            answer = self.run(['/usr/bin/dig', '@1.1.1.1', '_veyra.'+site['domain'], 'TXT', '+short', '+time=2', '+tries=1'])
            valid = any(line.strip() == json.dumps(zone['challenge']) for line in answer.splitlines())
            db.execute('UPDATE dns_zones SET verified=?,checked=? WHERE site_id=?', (int(valid),int(time.time()),site['id']))
            self.e.log(db, actor, 'dns.ownership_checked', site['domain'])
            return {'ok':True, 'verified':valid}
        elif method == 'dns.save':
            if db.execute('SELECT COUNT(*) FROM dns_records WHERE site_id=?', (site['id'],)).fetchone()[0] >= 100:
                raise Fault('This zone has reached its 100-record limit.', 409)
            record = validate(data)
            if record['name'] == 'ns1':
                raise Fault('The private preview nameserver address is managed by VectorCP.')
            conflicting = db.execute('SELECT type FROM dns_records WHERE site_id=? AND name=?', (site['id'],record['name'])).fetchall()
            if conflicting and (record['type'] == 'CNAME' or any(r[0]=='CNAME' for r in conflicting)):
                raise Fault('A CNAME must be the only record at its name.', 409)
            try:
                db.execute('INSERT INTO dns_records(site_id,name,type,ttl,value) VALUES(?,?,?,?,?)', (site['id'],record['name'],record['type'],record['ttl'],record['value']))
            except Exception as error:
                import sqlite3
                if isinstance(error, sqlite3.IntegrityError):
                    raise Fault('This DNS record already exists.', 409)
                raise
            db.execute('UPDATE dns_zones SET serial=serial+1 WHERE site_id=?', (site['id'],))
        elif method == 'dns.delete':
            record = db.execute('SELECT * FROM dns_records WHERE id=? AND site_id=?', (integer(data.get('id'),'DNS record',1,2147483647),site['id'])).fetchone()
            if not record:
                raise Fault('DNS record not found.',404)
            db.execute('DELETE FROM dns_records WHERE id=?',(record['id'],))
            db.execute('UPDATE dns_zones SET serial=serial+1 WHERE site_id=?',(site['id'],))
        else:
            raise Fault('Unknown DNS operation.',404)
        self.publish(db, site)
        self.e.log(db, actor, method, site['domain'])
        return {'ok':True}
