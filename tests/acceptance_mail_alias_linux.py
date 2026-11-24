"""Opt-in alias QA on the existing marked loopback-only mail acceptance guest.

Retains synthetic messages/aliases and never sends external mail.
"""
import argparse
import imaplib
import json
import os
from pathlib import Path
import secrets
import smtplib
import socket
import ssl
import subprocess
import time

from vectorcp.agent import rpc
from vectorcp.core import Fault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path('/var/lib/vectorcp/mail-acceptance')
    if not args.apply or os.geteuid() != 0 or not Path('/var/lib/vectorcp/acceptance-context.json').is_file():
        raise SystemExit('Requires --apply as root on the marked disposable acceptance guest.')
    os.umask(0o077)
    fixture = json.loads((root / 'fixture.json').read_text())
    login = json.loads(Path('/var/lib/vectorcp/acceptance-context.json').read_text())['owner_login']
    profile = json.loads(Path('/etc/vectorcp/mail/installed.json').read_text())
    assert profile['aliases'] is True and profile['listen'] == ['127.0.0.1']
    assert subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing'
    session = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': login})

    def call(method, data=None):
        return rpc('/run/vectorcp/agent.sock', {'method': method, 'data': data or {}, 'token': session['token'], 'csrf': session['csrf']})

    site = fixture['sites'][0]
    destination = fixture['addresses'][0]
    local = fixture['prefix'] + '-alias'
    alias_address = local + '@' + site[1]
    domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == site[0])
    alias = next((a for a in domain['aliases'] if a['local'] == local), None)
    if alias is None:
        call('mail.alias-create', {'site_id': site[0], 'mailbox_id': fixture['ids'][0], 'local': local})
        domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == site[0])
        alias = next(a for a in domain['aliases'] if a['local'] == local)
    call('mail.alias-active', {'id': alias['id'], 'active': True})
    checks = []

    def passed(value):
        checks.append(value)
        print('PASS ' + value, flush=True)

    for target in (fixture['ids'][1], alias['id'], 'external@example.invalid'):
        try:
            call('mail.alias-create', {'site_id': site[0], 'mailbox_id': target, 'local': 'denied-' + secrets.token_hex(2)})
            raise AssertionError('An invalid alias destination was accepted')
        except Fault as error:
            assert error.status == 404
    passed('alias targets cannot cross domains, chain to aliases or route to external addresses')

    context = ssl.create_default_context(cafile='/root/vectorcp-mail-test-tls/cert.pem')
    host = 'mail.example.test'

    class IMAP(imaplib.IMAP4_SSL):
        def _create_socket(self, timeout):
            return context.wrap_socket(socket.create_connection(('127.0.0.1', 993), timeout), server_hostname=host)

    def mailbox():
        client = IMAP(host, 993, timeout=20)
        client.login(destination, fixture['passwords'][0])
        client.select('INBOX')
        return client

    subject = 'VectorCP-alias-' + secrets.token_hex(8)
    with smtplib.SMTP('127.0.0.1', 25, timeout=20) as client:
        client.ehlo('qa.example.test')
        client.sendmail('outside@sender.example.test', [alias_address], 'From: outside@sender.example.test\r\nTo: ' + alias_address + '\r\nSubject: ' + subject + '\r\n\r\nSynthetic same-domain alias delivery.\r\n')
    delivered = False
    for _ in range(30):
        client = mailbox()
        delivered = bool(client.search(None, 'HEADER', 'Subject', subject)[1][0])
        client.logout()
        if delivered:
            break
        time.sleep(0.5)
    assert delivered
    passed('real SMTP alias lookup reaches the destination inbox through Postfix queue and LMTP')

    client = IMAP(host, 993, timeout=20)
    try:
        client.login(alias_address, fixture['passwords'][0])
        raise AssertionError('An alias was accepted as an IMAP login')
    except imaplib.IMAP4.error:
        client.shutdown()
    with smtplib.SMTP('127.0.0.1', 587, timeout=20) as client:
        client.ehlo('qa.example.test'); client._host = host
        client.starttls(context=context); client.ehlo('qa.example.test')
        try:
            client.login(alias_address, fixture['passwords'][0])
            raise AssertionError('An alias was accepted as an SMTP login')
        except smtplib.SMTPAuthenticationError:
            pass
        client.login(destination, fixture['passwords'][0])
        client.mail(alias_address)
        assert client.rcpt(destination)[0] >= 500
    passed('aliases cannot authenticate or be used as an authenticated envelope sender')

    for method, ident in [('mail.alias-active', alias['id']), ('mail.active', fixture['ids'][0])]:
        call(method, {'id': ident, 'active': False})
        with smtplib.SMTP('127.0.0.1', 25, timeout=20) as client:
            client.ehlo('qa.example.test'); client.mail('outside@sender.example.test')
            assert client.rcpt(alias_address)[0] >= 500
        call(method, {'id': ident, 'active': True})
    with smtplib.SMTP('127.0.0.1', 25, timeout=20) as client:
        client.ehlo('qa.example.test'); client.mail('outside@sender.example.test')
        assert client.rcpt(alias_address)[0] == 250
    passed('alias and destination suspension reject new SMTP recipients; restoration resumes lookup')

    # Simulate an interrupted publication after committed alias state, no data deletion.
    subprocess.run(['/usr/bin/systemctl', 'stop', 'postfix', 'dovecot'], check=True)
    from vectorcp.core import Engine
    engine = Engine('/var/lib/vectorcp', '/srv/vectorcp/sites', '/etc/nginx/conf.d')
    engine.mail.checkpoint()
    failed = subprocess.run(['/usr/bin/systemctl', 'start', 'postfix', 'dovecot'], capture_output=True)
    assert failed.returncode != 0
    assert call('mail.list')['recovery_required']
    call('mail.recover', {'confirm': 'RECOVER MAIL'})
    domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == site[0])
    assert next(a for a in domain['aliases'] if a['id'] == alias['id'])['effective']
    client = mailbox(); assert client.search(None, 'HEADER', 'Subject', subject)[1][0]; client.logout()
    passed('pending checkpoint blocks native startup and owner recovery retains aliases and delivered messages')
    call('logout')
    (root / 'alias-result.json').write_text(json.dumps({'checks': checks, 'at': int(time.time()), 'network': 'loopback only', 'selinux': 'Enforcing'}, indent=2) + '\n')
    print('Completed ' + str(len(checks)) + ' native alias acceptance groups.', flush=True)


if __name__ == '__main__':
    main()
