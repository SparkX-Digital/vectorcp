"""Opt-in additive mail recovery QA on the marked loopback-only native guest.

Retains all synthetic mail, snapshots and interruption evidence. No Internet mail.
"""
import argparse
from contextlib import closing
import hashlib
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
from unittest.mock import patch

from vectorcp.agent import rpc
from vectorcp.core import Fault
from vectorcp.mail_recovery import Recovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    state = Path('/var/lib/vectorcp')
    if not args.apply or os.geteuid() != 0 or not (state / 'acceptance-context.json').is_file():
        raise SystemExit('Requires --apply as root on the marked disposable acceptance guest.')
    os.umask(0o077)
    installed = json.loads(Path('/etc/vectorcp/mail/installed.json').read_text())
    assert installed['listen'] == ['127.0.0.1'] and installed['hostname'] == 'mail.example.test'
    assert subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing'
    fixture = json.loads((state / 'mail-acceptance/fixture.json').read_text())
    login = json.loads((state / 'acceptance-context.json').read_text())['owner_login']
    session = rpc('/run/vectorcp/agent.sock', {'method': 'login', 'data': login})
    def call(method, data=None):
        return rpc('/run/vectorcp/agent.sock', {'method': method, 'data': data or {}, 'token': session['token'], 'csrf': session['csrf']})
    unique = 'VectorCP-recovery-' + secrets.token_hex(5)
    # Each run has a dedicated retained mailbox, so repeated QA does not keep
    # nesting previous recovery trees or consume another fixture's quota.
    secret = secrets.token_urlsafe(24)
    local = unique.lower()
    call('mail.create', {'site_id': fixture['sites'][0][0], 'local': local, 'quota_mb': 16, 'password': secret})
    domain = next(d for d in call('mail.list')['domains'] if d['site_id'] == fixture['sites'][0][0])
    box = next(b for b in domain['mailboxes'] if b['address'].split('@')[0] == local)
    fixture['addresses'][0], fixture['passwords'][0], fixture['ids'][0] = box['address'], secret, box['id']
    context = ssl.create_default_context(cafile='/root/vectorcp-mail-test-tls/cert.pem')
    class IMAP(imaplib.IMAP4_SSL):
        def _create_socket(self, timeout):
            return context.wrap_socket(socket.create_connection(('127.0.0.1', 993), timeout), server_hostname='mail.example.test')
    def mailbox():
        client = IMAP('mail.example.test', 993, timeout=20)
        client.login(fixture['addresses'][0], fixture['passwords'][0])
        return client
    def cli(action, *arguments, apply=False, success=True):
        result = subprocess.run(['python3', '-m', 'vectorcp.mail_recovery', action, *arguments] + (['--apply'] if apply else []), capture_output=True, text=True, timeout=150, cwd='/opt/vectorcp')
        if success:
            assert result.returncode == 0, result.stderr[-2000:]
            return json.loads(result.stdout)
        assert result.returncode != 0, 'Unsafe mail recovery input was accepted'
        return result
    checks = []
    def passed(value):
        checks.append(value); print('PASS ' + value, flush=True)
    def records():
        with closing(sqlite3.connect(state / 'control.sqlite3')) as db:
            return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall() for table in ('mail_domains', 'mailboxes', 'mail_aliases')}
    def message(subject):
        return ('From: synthetic@sender.example.test\r\nTo: ' + fixture['addresses'][0] + '\r\nSubject: ' + subject + '\r\n\r\nRetained synthetic recovery fixture.\r\n').encode()
    folder = unique + '/Archive'
    client = mailbox()
    assert client.create(folder)[0] == 'OK'
    assert client.append('INBOX', '(\\Seen qaSaved)', imaplib.Time2Internaldate(1700000000), message(unique + '-inbox'))[0] == 'OK'
    assert client.append(folder, '(\\Flagged)', imaplib.Time2Internaldate(1700000000), message(unique + '-folder'))[0] == 'OK'
    client.logout()
    before_records = records()
    control_hash = hashlib.sha256((state / 'control.sqlite3').read_bytes()).hexdigest()
    services = {u: subprocess.check_output(['systemctl', 'show', '-p', 'MainPID', '--value', u], text=True).strip() for u in ('postfix', 'dovecot', 'vectorcp-agent')}
    preflight = cli('backup', '--mailbox', fixture['addresses'][0])
    assert preflight['check_only']
    assert hashlib.sha256((state / 'control.sqlite3').read_bytes()).hexdigest() == control_hash
    assert services == {u: subprocess.check_output(['systemctl', 'show', '-p', 'MainPID', '--value', u], text=True).strip() for u in services}
    passed('native check-only snapshot leaves control bytes, jobs and service PIDs unchanged')
    snap = cli('backup', '--mailbox', fixture['addresses'][0], apply=True)
    ident = snap['id']
    recovery = Recovery()
    data = recovery.read_snapshot(ident)
    assert data['messages'] and all('password' not in key for key in data)
    assert records() == before_records
    slot = fixture['sites'][0][2]
    with closing(sqlite3.connect(state / 'control.sqlite3')) as db:
        slot = db.execute('SELECT hosting_slot FROM users WHERE id=?', (slot,)).fetchone()[0]
    assert subprocess.run(['runuser', '-u', 'vectorcp-c%02d' % slot, '--', 'test', '-r', str(recovery.root / ident / 'manifest.json')], capture_output=True).returncode != 0
    passed('quiesced root-only snapshot verifies delivered messages, folders and keyword maps without credentials; website UID is denied')
    newer = unique + '-newer'
    with smtplib.SMTP('127.0.0.1', 25, timeout=20) as client:
        client.ehlo('qa.example.test')
        assert not client.sendmail('outside@sender.example.test', [fixture['addresses'][0]], message(newer))
    for _ in range(40):
        client = mailbox(); client.select('INBOX')
        found = bool(client.search(None, 'HEADER', 'Subject', newer)[1][0]); client.logout()
        if found: break
        time.sleep(0.25)
    assert found
    cli('restore', '--mailbox', fixture['addresses'][1], '--snapshot', ident, apply=True, success=False)
    assert not recovery.mail.pending.exists()
    cli('restore', '--mailbox', fixture['addresses'][0], '--snapshot', ident)
    result = cli('restore', '--mailbox', fixture['addresses'][0], '--snapshot', ident, apply=True)
    destination = result['folder']
    client = mailbox(); client.select('INBOX')
    assert client.search(None, 'HEADER', 'Subject', newer)[1][0]
    assert client.select(destination)[0] == 'OK'
    ids = client.search(None, 'HEADER', 'Subject', unique + '-inbox')[1][0]
    assert ids
    status, rows = client.fetch(ids.split()[-1], '(FLAGS INTERNALDATE BODY.PEEK[])')
    assert status == 'OK'
    metadata = b' '.join(row[0] if isinstance(row, tuple) else row for row in rows)
    assert b'\\Seen' in metadata and b'qaSaved' in metadata and b'14-Nov-2023' in metadata
    assert client.select(destination + '/' + folder)[0] == 'OK'
    assert client.search(None, 'HEADER', 'Subject', unique + '-folder')[1][0]
    client.logout()
    assert records() == before_records
    cli('restore', '--mailbox', fixture['addresses'][0], '--snapshot', ident, apply=True, success=False)
    passed('IMAPS reads additive recovery folders with flags, keyword and internal date; newer inbox mail, records and duplicate-restore boundary are preserved')
    # A second snapshot supplies new recovery names. Inject failure after one
    # folder is published, then prove the persistent startup fence and owner abort.
    interrupted = cli('backup', '--mailbox', fixture['addresses'][0], apply=True)['id']
    recovery = Recovery(); rename = os.rename; published = []
    def interrupted_rename(source, target):
        if Path(source).parent.name.startswith('.vectorcp-recovery-') and Path(target).name.startswith('.Recovered-'):
            if published:
                raise OSError('Synthetic native second-folder interruption')
            published.append(str(target))
        return rename(source, target)
    with patch('vectorcp.mail_recovery.os.rename', side_effect=interrupted_rename):
        try:
            recovery.restore(interrupted, fixture['addresses'][0], apply=True)
            raise AssertionError('The synthetic interruption was not triggered')
        except OSError:
            pass
    assert len(published) == 1 and recovery.mail.pending.exists()
    for unit in ('postfix', 'dovecot'):
        assert subprocess.run(['systemctl', 'start', unit], capture_output=True).returncode != 0
    try:
        call('mail.recover', {'confirm': 'RECOVER MAIL'})
        raise AssertionError('Ordinary publication recovery cleared a message checkpoint')
    except Fault:
        pass
    cli('recover')
    cli('recover', apply=True)
    assert not recovery.mail.pending.exists() and not Path(published[0]).exists()
    client = mailbox(); client.select('INBOX')
    assert client.search(None, 'HEADER', 'Subject', newer)[1][0]
    assert client.select(destination)[0] == 'OK'
    assert client.search(None, 'HEADER', 'Subject', unique + '-inbox')[1][0]
    client.logout()
    assert records() == before_records
    passed('interrupted publication blocks native restart and generic recovery; explicit owner recovery retains staged data and restores prior mailbox access')
    assert subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing'
    for unit in ('postfix', 'dovecot', 'vectorcp-agent'):
        assert subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0
    call('logout')
    (state / 'mail-acceptance' / ('message-recovery-result-' + unique.rsplit('-', 1)[1] + '.json')).write_text(json.dumps({'checks': checks, 'selinux': 'Enforcing', 'snapshots': [ident, interrupted]}, indent=2) + '\n')
    print('Completed ' + str(len(checks)) + ' native message recovery groups.', flush=True)


if __name__ == '__main__':
    main()
