"""Opt-in DNS checks on the disposable acceptance guest, never a production host.

Requires the installed current source, private DNS profile and baseline fixtures.
--prepare leaves one .test zone active for an off-guest UDP/TCP query. --finish
stops that zone and returns the DNS service to private preview. Positive ownership
is a test fixture; real external ownership and registrar delegation are not proved.
"""
import argparse
import json
import ipaddress
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vectorcp.core import Engine, Fault
from vectorcp.dns_profile import apply as apply_profile, profile


def command(argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60, **kw).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-disposable-host', required=True, action='store_true')
    parser.add_argument('--public-ip', required=True, help='The operator-owned routed public IPv4 for this disposable fixture')
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument('--prepare', action='store_true')
    phase.add_argument('--finish', action='store_true')
    args = parser.parse_args()
    address = ipaddress.IPv4Address(args.public_ip)
    assert address.is_global, 'Use the operator-owned routed public IPv4'
    state = Path('/var/lib/vectorcp')
    context_path = state / 'acceptance-context.json'
    saved = state / 'dns-acceptance-context.json'
    assert os.geteuid() == 0 and sys.platform.startswith('linux') and context_path.is_file()
    os.umask(0o077)
    web_was_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'vectorcp-web']).returncode == 0
    command(['systemctl', 'stop', 'vectorcp-agent'])
    try:
        engine = Engine(state, '/srv/vectorcp/sites', '/etc/nginx/conf.d')
        if engine.public_ipv4 is None:
            # Fixture configuration only: this does not issue a TLS certificate.
            configured_ip = state / 'public-https-prepared'
            assert not configured_ip.exists(), 'Inspect an existing invalid IP marker rather than overwriting it'
            configured_ip.write_text(str(address) + '\n')
            configured_ip.chmod(0o600)
        assert engine.public_ipv4 == str(address), 'The supplied public IP must match the fixture configuration'
        owner = engine.login(json.loads(context_path.read_text())['owner_login'])

        def call(method, data=None, who=None):
            session = who or owner
            return engine.dispatch({'method': method, 'data': data or {}, 'token': session['token'], 'csrf': session['csrf']})

        def zone(site): return call('dns.list', {'site_id': site})

        def change(site, method, **data):
            return call(method, dict(site_id=site, serial=zone(site)['zone']['serial'], **data))

        def denied(fn):
            try: fn()
            except Fault: return
            raise AssertionError('Forbidden DNS operation accepted')

        def passed(message): print('PASS:', message, flush=True)

        script = str(Path(__file__).resolve().parents[1] / 'deploy/dns-public.sh')
        marker = Path('/etc/vectorcp/dns/installed.json')
        if args.finish:
            ctx = json.loads(saved.read_text())
            if zone(ctx['site'])['zone']['published']:
                change(ctx['site'], 'dns.deactivate', confirm_domain=ctx['domain'])
            command(['bash', script, '--apply', '--private'])
            assert json.loads(marker.read_text())['mode'] == 'private'
            for tcp in (False, True):
                probe = engine.dns.probe(ctx['domain'], tcp)
                assert probe['authoritative'] and probe['serial'] == zone(ctx['site'])['zone']['serial']
            saved.unlink()
            passed('public hosting stopped, records retained, private preview rebuilt over UDP and TCP')
            return

        assert not saved.exists(), 'Finish the previous acceptance run first'
        assert engine.dns.profile['mode'] == 'private', 'Start with the private DNS profile'
        interfaces = json.loads(command(['/usr/sbin/ip', '-j', 'address', 'show']))
        address = next(a['local'] for interface in interfaces if interface['ifname'] != 'lo'
                       for a in interface['addr_info'] if a['family'] == 'inet')
        public_args = ['bash', script, '--apply', '--public', '--nameserver', 'ns1.vectorcp-acceptance.test',
                       '--nameserver', 'ns2.vectorcp-acceptance.test', '--listen-ip', address]
        ipv6 = next((a['local'] for interface in interfaces if interface['ifname'] != 'lo'
                     for a in interface['addr_info'] if a['family'] == 'inet6' and not ipaddress.ip_address(a['local']).is_link_local), None)
        if ipv6:
            public_args += ['--listen-ip', ipv6]
        previous_marker = marker.read_bytes()
        bad = subprocess.run(public_args[:-1] + ['192.0.2.254'], capture_output=True, text=True)
        assert bad.returncode and marker.read_bytes() == previous_marker
        command(public_args)
        assert engine.dns.profile['mode'] == 'public'
        passed('explicit public profile installed with UDP/TCP interface checks; unassigned interface refused')

        domain = 'dns-' + secrets.token_hex(4) + '.acceptance.test'
        site = call('sites.create', {'domain': domain})['id']
        call('dns.create', {'site_id': site})
        assert not zone(site)['zone']['published']
        for tcp in (False, True): assert engine.dns.probe(domain, tcp)['serial'] is None
        denied(lambda: change(site, 'dns.activate', confirm_domain=domain))
        assert not zone(site)['zone']['published']
        passed('draft zone absent from native UDP/TCP service; real public-resolver ownership failure refused')

        with patch.object(engine.dns, 'ownership', return_value=True):
            change(site, 'dns.activate', confirm_domain=domain)
        for tcp in (False, True):
            probe = engine.dns.probe(domain, tcp)
            assert probe['authoritative'] and probe['serial'] == zone(site)['zone']['serial']
        assert set(command(['/usr/bin/dig', '@' + address, domain, 'NS', '+short', '+time=1', '+tries=1']).splitlines()) == {'ns1.vectorcp-acceptance.test.', 'ns2.vectorcp-acceptance.test.'}
        denied(lambda: change(site, 'dns.activate', confirm_domain=domain))
        change(site, 'dns.save', name='www', type='A', value='192.0.2.11')
        row = next(r for r in zone(site)['records'] if r['name'] == 'www')
        change(site, 'dns.update', id=row['id'], name='www', type='A', value='192.0.2.12', ttl=600)
        assert command(['/usr/bin/dig', '@127.0.0.1', 'www.' + domain, 'A', '+short']).strip() == '192.0.2.12'
        previous = zone(site)
        files = {p: p.read_bytes() for p in (engine.dns.zones / ('site-%d.zone' % site), engine.dns.config / 'zones.conf')}
        original_run = engine.dns.run
        def fail_reload(argv):
            if argv[:3] == ['/usr/bin/systemctl', 'reload', 'vectorcp-dns']:
                raise Fault('Injected reload failure', 503)
            return original_run(argv)
        with patch.object(engine.dns, 'run', side_effect=fail_reload):
            denied(lambda: change(site, 'dns.update', id=row['id'], name='www', type='A', value='192.0.2.13', ttl=600))
        assert zone(site) == previous and all(p.read_bytes() == payload for p, payload in files.items())
        assert command(['/usr/bin/dig', '@127.0.0.1', 'www.' + domain, 'A', '+short']).strip() == '192.0.2.12'
        passed('fixture-authorized native activation, record editing and failed-reload rollback preserve correct answers')

        transfer = subprocess.run(['/usr/bin/dig', '@' + address, domain, 'AXFR', '+time=1', '+tries=1'], capture_output=True, text=True)
        assert 'Transfer failed' in transfer.stdout or transfer.returncode
        recursive = command(['/usr/bin/dig', '@' + address, 'www.example.org', 'A', '+noall', '+comments', '+answer', '+time=1', '+tries=1'])
        assert 'status: REFUSED' in recursive and ' ra;' not in recursive and ' ra ' not in recursive
        blocked = subprocess.run(['bash', script, '--apply', '--private'], capture_output=True, text=True)
        assert blocked.returncode and engine.dns.profile['mode'] == 'public'
        passed('off-loopback AXFR and recursive resolution denied; profile changes refuse active zones')

        change(site, 'dns.deactivate', confirm_domain=domain)
        for tcp in (False, True): assert engine.dns.probe(domain, tcp)['serial'] is None
        import fcntl
        with open('/var/lib/vectorcp/profile-maintenance.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('vectorcp.dns_profile.configuration', return_value='invalid configuration;'):
                denied(lambda: apply_profile(profile({'mode': 'private'})))
        assert engine.dns.profile['mode'] == 'public'
        assert command(['systemctl', 'is-active', 'vectorcp-dns']).strip() == 'active'
        passed('deactivation removes authority; invalid profile rolls back files and the real service')
        maintenance = Path('/run/vectorcp-profile-maintenance')
        assert not maintenance.exists()
        # Stub only the reviewed wrapper's Python child. No profile files change.
        result = subprocess.run(['bash', '-c', 'python3() { return 75; }; export -f python3; bash "$1" --apply --private',
                                 'dns-recovery-fixture', script], capture_output=True, text=True)
        try:
            assert result.returncode == 75 and maintenance.is_file()
            denied(lambda: change(site, 'dns.rebuild'))
        finally:
            # This marker belongs to the deliberately non-mutating fixture above.
            maintenance.unlink(missing_ok=True)
        passed('incomplete-recovery wrapper retains maintenance marker and blocks DNS mutations')
        with patch.object(engine.dns, 'ownership', return_value=True):
            change(site, 'dns.activate', confirm_domain=domain)
        assert command(['getenforce']).strip() == 'Enforcing'
        saved.write_text(json.dumps({'site': site, 'domain': domain, 'serial': zone(site)['zone']['serial']}))
        saved.chmod(0o600)
        passed('SELinux remains enforcing; fixture ready for off-guest checks')
        print(json.dumps({'domain': domain, 'serial': zone(site)['zone']['serial']}), flush=True)
    except Exception:
        if args.prepare:
            try:
                if 'site' in locals() and zone(site)['zone'] and zone(site)['zone']['published']:
                    change(site, 'dns.deactivate', confirm_domain=domain)
                if 'engine' in locals() and engine.dns.profile['mode'] == 'public':
                    command(['bash', script, '--apply', '--private'])
            except Exception:
                print('Acceptance cleanup needs administrator inspection inside this disposable guest.', file=sys.stderr)
        raise
    finally:
        command(['systemctl', 'start', 'vectorcp-agent'])
        if web_was_active:
            command(['systemctl', 'start', 'vectorcp-web'])


if __name__ == '__main__': main()
