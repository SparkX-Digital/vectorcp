"""Owner-configured authoritative DNS profiles; no browser configuration input."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import time

from .core import DOMAIN, Fault


class RecoveryRequired(Fault):
    """Keep the maintenance marker when automatic profile recovery is incomplete."""


def profile(data):
    if not isinstance(data, dict) or data.get('mode', 'private') not in ('private', 'public'):
        raise Fault('Invalid DNS service profile.', 503)
    if data.get('mode', 'private') == 'private':
        return {'mode': 'private', 'nameservers': [], 'ipv4': ['127.0.0.1'], 'ipv6': []}
    names = data.get('nameservers')
    addresses = data.get('listen')
    if not isinstance(names, list) or not 2 <= len(names) <= 4:
        raise Fault('Configure two to four distinct full nameserver names.')
    normalized = []
    for name in names:
        if not isinstance(name, str) or not DOMAIN.fullmatch(name.lower().rstrip('.')):
            raise Fault('Use full nameserver names without spaces or configuration syntax.')
        normalized.append(name.lower().rstrip('.'))
    if len(set(normalized)) != len(normalized):
        raise Fault('Nameserver names must be distinct.')
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= 8:
        raise Fault('Configure one to eight explicit listening IP addresses.')
    ipv4, ipv6 = ['127.0.0.1'], []
    has_external = False
    for value in addresses:
        try:
            if not isinstance(value, str) or '%' in value:
                raise ValueError()
            address = ipaddress.ip_address(value)
            if address.is_unspecified or address.is_multicast or address.is_link_local:
                raise ValueError()
        except ValueError:
            raise Fault('Use explicit unicast listening addresses, without interface suffixes.')
        target = ipv4 if address.version == 4 else ipv6
        if str(address) not in target:
            target.append(str(address))
        has_external = has_external or not address.is_loopback
    if not has_external:
        raise Fault('A public DNS profile needs a listening address outside loopback.')
    return {'mode': 'public', 'nameservers': normalized, 'ipv4': ipv4, 'ipv6': ipv6}


def stored(p):
    return {'mode': p['mode'], 'nameservers': p['nameservers'],
            'listen': p['ipv4'] + p['ipv6']}


def load(path, development=False):
    if not path.exists():
        return profile({'mode': 'private'})
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise ValueError()
        if not development and (info.st_uid != 0 or info.st_mode & 0o022):
            raise ValueError()
        return profile(json.loads(path.read_text()))
    except (OSError, ValueError):
        raise Fault('The owner DNS profile is invalid; contact the server administrator.', 503)


def configuration(p, include='/etc/vectorcp/dns/zones.conf'):
    def acl(values):
        return ' '.join(v + ';' for v in values) or 'none;'
    return '''options {
  directory "/var/named/data/vectorcp";
  listen-on port 53 { %s };
  listen-on-v6 port 53 { %s };
  recursion no;
  allow-recursion { none; };
  allow-query-cache { none; };
  allow-query { %s };
  allow-transfer { none; };
  allow-update { none; };
  dnssec-validation no;
  notify no;
  minimal-responses yes;
  version "%s";
  pid-file "/run/vectorcp-dns/named.pid";
  session-keyfile "/run/vectorcp-dns/session.key";
  rate-limit { responses-per-second 10; exempt-clients { 127.0.0.1; }; };
};
controls { };
include "%s";
''' % (acl(p['ipv4']), acl(p['ipv6']), 'any;' if p['mode'] == 'public' else '127.0.0.1;',
       'vectorcp-authoritative' if p['mode'] == 'public' else 'private-authoritative', include)


def apply(p):
    """Called by the locked maintenance wrapper, only for an installed service."""
    if os.geteuid() != 0 or not Path('/etc/almalinux-release').exists():
        raise Fault('DNS profile changes require root on the supported AlmaLinux host.')
    directory = Path('/etc/vectorcp/dns')
    marker = directory / 'installed.json'
    if not marker.exists() or directory.is_symlink():
        raise Fault('Install the private DNS profile first.')
    old_profile = load(marker)
    if old_profile == p:
        print('DNS profile already matches; no service changes made.')
        return
    interfaces = subprocess.run(['/usr/sbin/ip', '-j', 'address', 'show'], capture_output=True, text=True, timeout=15, check=True)
    available = {str(ipaddress.ip_address(a['local'])) for interface in json.loads(interfaces.stdout)
                 if 'UP' in interface.get('flags', []) for a in interface.get('addr_info', []) if 'local' in a}
    if not set(p['ipv4'] + p['ipv6']) <= available:
        raise Fault('Every listening address must be assigned to an active server interface.')
    db = sqlite3.connect('/var/lib/vectorcp/control.sqlite3', timeout=20)
    db.row_factory = sqlite3.Row
    zone_payloads = {}
    try:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise Fault('Wait for hosting jobs to finish before changing DNS profiles.', 409)
        columns = {r[1] for r in db.execute('PRAGMA table_info(dns_zones)')}
        if 'published' not in columns:
            raise Fault('Restart the updated agent to apply its DNS schema before changing profiles.')
        if db.execute('SELECT 1 FROM dns_zones WHERE published=1').fetchone():
            raise Fault('Stop public hosting for active zones before changing the DNS profile.', 409)
        include = '\n'.join('zone "%s" { type master; file "/var/named/vectorcp/site-%d.zone"; allow-transfer { none; }; allow-update { none; }; };' % (domain, ident)
                            for ident, domain in db.execute('SELECT s.id,s.domain FROM dns_zones z JOIN sites s ON s.id=z.site_id ORDER BY s.id')) + '\n'
        if p['mode'] == 'public':
            include = '// No zones are public until their customers verify and activate them.\n'
        else:
            from .dns import render_zone
            prepared = Path('/var/lib/vectorcp/public-https-prepared')
            match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', prepared.read_text()) if prepared.exists() else None
            address = ipaddress.ip_address(match[0]) if match else None
            zones = db.execute('SELECT site_id FROM dns_zones').fetchall()
            if zones and (address is None or address.version != 4 or not address.is_global):
                raise Fault('Configure the server public IPv4 before rebuilding private previews.')
            zone_payloads = {Path('/var/named/vectorcp/site-%d.zone' % row[0]):
                             render_zone(db, row[0], p, str(address)).encode() for row in zones}
    finally:
        db.close()
    active = [directory / 'named.conf', directory / 'zones.conf', marker] + list(zone_payloads)
    previous = {}
    for path in active:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise Fault('DNS configuration files must be regular root-owned files.')
        previous[path] = (path.read_bytes(), stat.S_IMODE(st.st_mode), st.st_gid)

    def run(args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise Fault('DNS profile validation or service change failed; previous files were retained.', 503)
        return result.stdout

    def write(path, value, mode=0o640, gid=None):
        temporary = path.with_name(path.name + '.profile-' + secrets.token_hex(8))
        try:
            with temporary.open('xb') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(mode)
            os.chown(temporary, 0, previous[active[0]][2] if gid is None else gid)
            os.replace(temporary, path)
            run(['/usr/sbin/restorecon', str(path)])
        finally:
            temporary.unlink(missing_ok=True)

    recovery = Path('/var/lib/vectorcp/dns-profile-recovery') / (str(int(time.time())) + '-' + secrets.token_hex(4))
    recovery.mkdir(parents=True, mode=0o700)
    recovery.parent.chmod(0o700)
    manifest = []
    for number, (path, (payload, mode, gid)) in enumerate(previous.items()):
        saved = recovery / ('%d.original' % number)
        saved.write_bytes(payload)
        saved.chmod(0o600)
        manifest.append({'path': str(path), 'backup': saved.name, 'mode': mode, 'gid': gid})
    (recovery / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (recovery / 'manifest.json').chmod(0o600)

    changed = False
    try:
        run(['/usr/bin/systemctl', 'is-active', 'vectorcp-dns'])
        # The wrapper blocks agent mutations throughout the transition.
        changed = True
        for path, payload in zone_payloads.items():
            write(path, payload)
        write(active[1], include.encode())
        write(active[0], configuration(p).encode())
        run(['/usr/sbin/named-checkconf', '-z', str(active[0])])
        run(['/usr/bin/systemctl', 'restart', 'vectorcp-dns'])
        expected = 'vectorcp-authoritative' if p['mode'] == 'public' else 'private-authoritative'
        for attempt in range(10):
            try:
                answer = run(['/usr/bin/dig', '@127.0.0.1', 'version.bind', 'TXT', 'CH', '+short', '+time=1', '+tries=1'])
                if answer.strip() == json.dumps(expected):
                    break
            except Fault:
                pass
            time.sleep(0.1)
        else:
            raise Fault('The DNS service did not confirm the selected profile.', 503)
        for address in p['ipv4'] + p['ipv6']:
            for tcp in (False, True):
                answer = run(['/usr/bin/dig', '@' + address, 'version.bind', 'TXT', 'CH',
                              '+short', '+time=1', '+tries=1'] + (['+tcp'] if tcp else []))
                if answer.strip() != json.dumps(expected):
                    raise Fault('The DNS service did not answer on every configured interface over UDP and TCP.', 503)
        write(marker, (json.dumps(stored(p)) + '\n').encode(), mode=0o600, gid=0)
    except Exception:
        if changed:
            failures = []
            for path, (payload, mode, gid) in previous.items():
                try:
                    write(path, payload, mode, gid)
                except Exception:
                    failures.append(str(path))
            try:
                run(['/usr/bin/systemctl', 'restart', 'vectorcp-dns'])
            except Exception:
                failures.append('service restart')
            if failures:
                raise RecoveryRequired('DNS rollback needs administrator recovery. Original files are in ' + str(recovery), 503)
        raise
    print('DNS profile: ' + p['mode'] + '. Host and provider firewalls are unchanged.')
    if p['mode'] == 'public':
        print('Allow inbound UDP and TCP port 53 before delegating domains. Verify every nameserver independently.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', action='store_true')
    parser.add_argument('--private', action='store_true')
    parser.add_argument('--nameserver', action='append', default=[])
    parser.add_argument('--listen-ip', action='append', default=[])
    args = parser.parse_args()
    if args.public == args.private or (args.private and (args.nameserver or args.listen_ip)):
        parser.error('Choose --private or --public with --nameserver and --listen-ip.')
    try:
        p = profile({'mode': 'public' if args.public else 'private', 'nameservers': args.nameserver, 'listen': args.listen_ip})
        apply(p)
    except RecoveryRequired as error:
        parser.exit(75, str(error) + '\n')
    except Fault as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
