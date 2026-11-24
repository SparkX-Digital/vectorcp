"""Destructive mail QA only on the marked disposable Linux acceptance guest.

No external messages or public DNS changes. Retains its private synthetic
mailboxes for inspection; repeat runs use the same private fixture.
"""
import argparse
import imaplib
import json
import os
from pathlib import Path
import secrets
import smtplib
import socket
import sqlite3
import ssl
import subprocess
import time

from vectorcp.agent import rpc

ROOT = Path('/var/lib/vectorcp/mail-acceptance')
FIXTURE = ROOT / 'fixture.json'
PROFILE = Path('/etc/vectorcp/mail/installed.json')
CERT = Path('/root/vectorcp-mail-test-tls/cert.pem')
CONTEXT = Path('/var/lib/vectorcp/acceptance-context.json')
HOST = 'mail.example.test'


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=45).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply or os.geteuid() != 0 or not CONTEXT.exists():
        raise SystemExit('Requires --apply as root on the marked disposable acceptance guest.')
    os.umask(0o077)
    profile = json.loads(PROFILE.read_text())
    assert profile['hostname'] == HOST and profile['listen'] == ['127.0.0.1']
    assert run(['getenforce']).strip() == 'Enforcing'
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if not FIXTURE.exists():
        fixture = {'prefix': 'qa' + secrets.token_hex(3), 'passwords': [secrets.token_urlsafe(24) for _ in range(3)]}
        FIXTURE.write_text(json.dumps(fixture))
    fixture = json.loads(FIXTURE.read_text())
    login = json.loads(CONTEXT.read_text())['owner_login']
    session = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': login})

    def call(method, data=None):
        return rpc('/run/vectorcp/agent.sock', {'method': method, 'data': data or {}, 'token': session['token'], 'csrf': session['csrf']})

    fixture.setdefault('customers', [])
    fixture.setdefault('sites', [])
    for index in range(2):
        if len(fixture['customers']) <= index:
            username = fixture['prefix'] + 'c' + str(index)
            account = call('accounts.create', {'username': username, 'name': 'Mail acceptance ' + str(index),
                           'password': secrets.token_urlsafe(24), 'site_limit': 2, 'storage_mb': 512})
            fixture['customers'].append(account['id'])
            FIXTURE.write_text(json.dumps(fixture))
        uid = fixture['customers'][index]
        account = next(a for a in call('accounts.list')['accounts'] if a['id'] == uid)
        if not account['hosting_slot']:
            job = call('hosting.enable', {'id': uid})
            for attempt in range(180):
                current = next(j for j in call('jobs.list')['jobs'] if j['id'] == job['job_id'])
                if current['status'] not in ('queued', 'running'):
                    assert current['status'] == 'complete', current['message']
                    break
                time.sleep(0.5)
            else:
                raise AssertionError('The isolated mail QA customer did not become ready')
        if len(fixture['sites']) <= index:
            domain = fixture['prefix'] + str(index) + '.mail.acceptance.test'
            site = call('sites.create', {'user_id': uid, 'domain': domain})
            fixture['sites'].append([site['id'], domain, uid])
            FIXTURE.write_text(json.dumps(fixture))
    first, second = fixture['sites']
    selected = [first, second, first]
    addresses = []
    ids = []
    for i, site in enumerate(selected):
        call('mail.domain', {'site_id': site[0], 'enabled': True, 'confirm_domain': site[1]})
        local = fixture['prefix'] + str(i)
        domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == site[0])
        existing = next((b for b in domain['mailboxes'] if b['local'] == local), None)
        if not existing:
            call('mail.create', {'site_id': site[0], 'local': local, 'quota_mb': 1 if i == 2 else 16, 'password': fixture['passwords'][i]})
            domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == site[0])
            existing = next(b for b in domain['mailboxes'] if b['local'] == local)
        ids.append(existing['id']); addresses.append(existing['address'])
    fixture.update({'ids': ids, 'addresses': addresses})
    FIXTURE.write_text(json.dumps(fixture))
    context = ssl.create_default_context(cafile=str(CERT))
    checks = []

    def passed(name):
        checks.append(name)
        print('PASS ' + name, flush=True)

    class IMAP(imaplib.IMAP4_SSL):
        def _create_socket(self, timeout):
            return context.wrap_socket(socket.create_connection(('127.0.0.1', 993), timeout), server_hostname=HOST)

    def imap(index, password=None):
        client = IMAP(HOST, 993, timeout=15)
        client.login(addresses[index], password or fixture['passwords'][index])
        return client

    def smtp(auth=False):
        client = smtplib.SMTP('127.0.0.1', 587 if auth else 25, timeout=20)
        client.ehlo('qa.example.test')
        if auth:
            assert 'auth' not in client.esmtp_features
            client._host = HOST  # Logical TLS hostname with explicit loopback routing.
            client.starttls(context=context)
            client.ehlo('qa.example.test')
            assert client.sock.version() in ('TLSv1.2', 'TLSv1.3')
            client.login(addresses[0], fixture['passwords'][0])
        return client

    a = imap(0); a.logout()
    with smtp(True) as s:
        assert s.sock.getpeercert()
    with smtplib.SMTP('127.0.0.1', 587, timeout=15) as s:
        s.ehlo('qa.example.test')
        assert 'auth' not in s.esmtp_features
        assert s.docmd('AUTH', 'PLAIN AHJvb3QAcm9vdA==')[0] >= 500
    for port in (110, 143, 465, 995):
        with socket.socket() as s:
            s.settimeout(1)
            assert s.connect_ex(('127.0.0.1', port)) != 0
    passed('verified TLS IMAPS and STARTTLS submission; plaintext authentication and unused ports disabled')

    with smtp() as s:
        s.mail('outside@sender.example.test')
        assert s.rcpt('nobody@example.invalid')[0] >= 500
        s.rset(); s.mail('outside@sender.example.test')
        assert s.rcpt('missing-' + addresses[0])[0] >= 500
    for sender in (addresses[1], ''):
        with smtp(True) as s:
            s.mail(sender)
            assert s.rcpt(addresses[1])[0] >= 500
    passed('anonymous relay, unknown recipient, cross-mailbox envelope spoofing and null submission sender rejected')

    marker = ('VectorCP mail acceptance ' + secrets.token_hex(8)).encode()
    message = b'From: ' + addresses[0].encode() + b'\r\nTo: ' + addresses[1].encode() + b'\r\nSubject: private delivery acceptance\r\n\r\n' + marker + b'\r\n'
    with smtp(True) as s:
        assert not s.sendmail(addresses[0], [addresses[1]], message)
    b = imap(1)
    found = False
    for attempt in range(30):
        b.select('INBOX')
        _, result = b.search(None, 'ALL')
        for ident in result[0].split()[-10:]:
            _, payload = b.fetch(ident, '(BODY.PEEK[])')
            if any(isinstance(part, tuple) and marker in part[1] for part in payload):
                found = True
        if found:
            break
        time.sleep(0.3)
    assert found, 'SMTP to LMTP to IMAP delivery did not arrive'
    b.logout()
    passed('authenticated SMTP delivery through the native queue and LMTP is readable only in the destination mailbox')

    a = imap(0)
    assert a.select('/var/lib/vectorcp-mail/store/' + ids[1] + '/Maildir')[0] == 'NO'
    a.select('INBOX')
    _, result = a.search(None, 'ALL')
    for ident in result[0].split():
        _, payload = a.fetch(ident, '(BODY.PEEK[])')
        assert not any(isinstance(part, tuple) and marker in part[1] for part in payload)
    a.logout()
    bad = IMAP(HOST, 993, timeout=15)
    try:
        bad.login(addresses[1], fixture['passwords'][0])
        raise AssertionError('Cross-mailbox password accepted')
    except imaplib.IMAP4.error:
        pass
    finally:
        bad.shutdown()
    passed('different-customer password and filesystem-style IMAP traversal cannot expose the other mailbox')

    tiny = imap(2)
    assert tiny.getquotaroot('INBOX')[0] == 'OK'
    oversized = b'Subject: over quota\r\n\r\n' + b'x' * (2 * 1048576)
    assert tiny.append('INBOX', None, None, oversized)[0] == 'NO'
    tiny.logout()
    with smtplib.LMTP('/var/spool/postfix/private/vectorcp-lmtp', timeout=20) as lmtp:
        try:
            lmtp.sendmail(addresses[0], [addresses[2]], oversized)
            raise AssertionError('Over-quota LMTP delivery accepted')
        except smtplib.SMTPDataError as error:
            assert error.smtp_code >= 500
    passed('IMAP quota extension and native APPEND/LMTP enforcement reject over-quota messages')

    a = imap(0); s = smtp(True)
    changed = secrets.token_urlsafe(24)
    call('mail.password', {'id': ids[0], 'password': changed})
    for connection in (a, s):
        try:
            connection.noop()
            raise AssertionError('An authenticated session survived password revocation')
        except (imaplib.IMAP4.abort, smtplib.SMTPServerDisconnected, OSError):
            pass
    old = fixture['passwords'][0]
    fixture['passwords'][0] = changed; FIXTURE.write_text(json.dumps(fixture))
    bad = IMAP(HOST, 993, timeout=15)
    try:
        bad.login(addresses[0], old)
        raise AssertionError('Old password remained valid')
    except imaplib.IMAP4.error:
        pass
    finally:
        bad.shutdown()
    a = imap(0); a.logout()
    call('accounts.active', {'id': first[2], 'active': False})
    try:
        bad = IMAP(HOST, 993, timeout=15)
        try:
            bad.login(addresses[0], changed)
            raise AssertionError('Suspended customer authenticated')
        except imaplib.IMAP4.error:
            pass
        finally:
            bad.shutdown()
    finally:
        call('accounts.active', {'id': first[2], 'active': True})
    a = imap(0); a.logout()
    passed('password change disconnects existing IMAP/SMTP sessions; account suspension and restoration reach native authentication')

    pending = Path('/var/lib/vectorcp-mail/pending.json')
    assert not pending.exists()
    pending.write_text('{"version":1,"acceptance_checkpoint":true}\n')
    pending.chmod(0o600)
    run(['systemctl', 'stop', 'postfix', 'dovecot'])
    assert subprocess.run(['systemctl', 'start', 'dovecot'], capture_output=True).returncode != 0
    run(['systemctl', 'restart', 'vectorcp-agent'])
    for _ in range(40):
        try:
            assert call('mail.list')['recovery_required']
            break
        except (OSError, RuntimeError):
            time.sleep(0.2)
    call('mail.recover', {'confirm': 'RECOVER MAIL'})
    assert not call('mail.list')['recovery_required']
    a = imap(1); a.select('INBOX'); assert a.search(None, 'ALL')[1][0]; a.logout()
    passed('persisted interruption prevents service startup; explicit owner recovery restores retained mailbox data')

    assert os.path.ismount('/var/lib/vectorcp-mail/store') and os.path.ismount('/var/spool/postfix')
    with sqlite3.connect('/var/lib/vectorcp/control.sqlite3') as db:
        slot = db.execute('SELECT hosting_slot FROM users WHERE id=?', (first[2],)).fetchone()[0]
    assert subprocess.run(['runuser', '-u', 'vectorcp-c%02d' % slot, '--', 'test', '-r', '/var/lib/vectorcp-mail/store/' + ids[1] + '/Maildir'], capture_output=True).returncode != 0
    assert subprocess.run(['runuser', '-u', 'postfix', '--', 'test', '-r', '/var/lib/vectorcp/control.sqlite3'], capture_output=True).returncode != 0
    assert Path('/var/lib/vectorcp-mail/lookup.sqlite3').stat().st_mode & 0o777 == 0o640
    with sqlite3.connect('/var/lib/vectorcp-mail/lookup.sqlite3') as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'domains', 'boxes', 'metadata', 'aliases'}
        assert all(r[0].startswith('{BLF-CRYPT}$2') for r in db.execute('SELECT password FROM boxes'))
    for unit in ('postfix', 'dovecot', 'vectorcp-agent', 'vectorcp-web', 'vectorcp-dns'):
        assert run(['systemctl', 'is-active', unit]).strip() == 'active'
    assert run(['getenforce']).strip() == 'Enforcing'
    passed('bounded mounts, website UID mail denial, restricted lookup/control DB separation, native hashes and healthy services with SELinux enforcing')
    (ROOT / 'result.json').write_text(json.dumps({'checks': checks, 'at': int(time.time()), 'network': 'loopback only', 'selinux': 'Enforcing'}, indent=2) + '\n')
    print('Completed ' + str(len(checks)) + ' native mail acceptance groups.', flush=True)


if __name__ == '__main__':
    main()
