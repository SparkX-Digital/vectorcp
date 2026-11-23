"""Explicit owner installation of the optional AlmaLinux 9 mail profile."""
import argparse
import fcntl
import grp
import ipaddress
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import smtplib
import socket
import sqlite3
import ssl
import subprocess
import time

from .core import DOMAIN, Engine, Fault

CONFIG = Path('/etc/vectorcp/mail')
BASE = Path('/var/lib/vectorcp-mail')
STATE = Path('/var/lib/vectorcp')
LOG = None


def run(args, input=None, timeout=60):
    p = subprocess.run(args, input=input, capture_output=True, text=True, timeout=timeout)
    if LOG:
        with LOG.open('a') as log:
            log.write(json.dumps({'command': args, 'exit': p.returncode, 'stderr': p.stderr[-16000:]}) + '\n')
    if p.returncode:
        raise Fault('Mail installation command failed: ' + Path(args[0]).name + '. Inspect the private installation log.', 503)
    return p.stdout


def write(path, value, mode=0o640, group=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.install-' + secrets.token_hex(8))
    payload = value.encode() if isinstance(value, str) else value
    try:
        fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fchown(stream.fileno(), 0, group)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync(path.parent)
        sync(path.parent.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mount_image(path, size, target, backup=None):
    if path.exists() or os.path.ismount(target):
        raise Fault('A mail image or mount already exists. Inspect the previous installation first.')
    run(['/usr/bin/fallocate', '-l', str(size * 1048576), str(path)])
    path.chmod(0o600)
    run(['/usr/sbin/mkfs.ext4', '-q', '-m', '0', str(path)])
    sync(path)
    sync(path.parent)
    unit = run(['/usr/bin/systemd-escape', '-p', '--suffix=mount', str(target)]).strip()
    write(Path('/etc/systemd/system') / unit, '''[Unit]
Description=VectorCP bounded mail storage
Before=postfix.service dovecot.service
[Mount]
What=%s
Where=%s
Type=ext4
Options=loop,nosuid,nodev,noexec
TimeoutSec=45
[Install]
WantedBy=multi-user.target
''' % (path, target), 0o644)
    target.mkdir(parents=True, exist_ok=True)
    run(['/usr/bin/systemctl', 'daemon-reload'])
    run(['/usr/bin/systemctl', 'enable', '--now', unit])
    if not os.path.ismount(target):
        raise Fault('The bounded mail storage did not mount.')
    if backup:
        shutil.copytree(backup, target, dirs_exist_ok=True, copy_function=shutil.copy2)
        # Preserve ownership and modes of the distribution's queue subdirectories.
        for source in [backup] + list(backup.rglob('*')):
            destination = target / source.relative_to(backup)
            st = source.lstat()
            os.chown(destination, st.st_uid, st.st_gid)
            os.chmod(destination, st.st_mode & 0o7777)


def postfix_config(hostname, listen):
    return '''# Managed by the optional VectorCP mail profile.
compatibility_level = 2
myhostname = %s
myorigin = $myhostname
inet_interfaces = %s
inet_protocols = ipv4
mydestination =
relay_domains =
mynetworks =
virtual_alias_domains =
virtual_alias_maps =
virtual_mailbox_domains = sqlite:/etc/postfix/vectorcp-domains.cf
virtual_mailbox_maps = sqlite:/etc/postfix/vectorcp-boxes.cf
virtual_transport = lmtp:unix:private/vectorcp-lmtp
recipient_delimiter =
local_recipient_maps =
local_transport = error:Local system delivery is disabled
authorized_submit_users = root
disable_vrfy_command = yes
smtputf8_enable = no
message_size_limit = 16777216
mailbox_size_limit = 0
queue_minfree = 67108864
maximal_queue_lifetime = 1d
bounce_queue_lifetime = 1d
default_process_limit = 25
smtpd_client_connection_count_limit = 10
smtpd_client_connection_rate_limit = 30
smtpd_client_message_rate_limit = 60
smtpd_recipient_limit = 20
smtpd_helo_required = yes
smtpd_relay_restrictions = permit_sasl_authenticated, reject_unauth_destination
smtpd_recipient_restrictions = reject_non_fqdn_recipient, reject_unlisted_recipient
smtpd_sasl_type = dovecot
smtpd_sasl_path = private/vectorcp-auth
smtpd_sasl_auth_enable = no
smtpd_sasl_security_options = noanonymous
smtpd_tls_security_level = may
smtpd_tls_auth_only = yes
smtpd_tls_cert_file = /etc/pki/vectorcp-mail/fullchain.pem
smtpd_tls_key_file = /etc/pki/vectorcp-mail/key.pem
smtpd_tls_mandatory_protocols = !SSLv2,!SSLv3,!TLSv1,!TLSv1.1
smtpd_tls_protocols = !SSLv2,!SSLv3,!TLSv1,!TLSv1.1
smtp_tls_security_level = may
smtp_tls_CAfile = /etc/pki/tls/certs/ca-bundle.crt
smtpd_sender_login_maps = sqlite:/etc/postfix/vectorcp-senders.cf
smtpd_data_restrictions = reject_unauth_pipelining
smtpd_delay_reject = yes
''' % (hostname, ', '.join(listen))


def dovecot_config(listen, uid, gid):
    return '''# Managed by the optional VectorCP mail profile. Dovecot 2.3 only.
protocols = imap lmtp
listen = %s
ssl = required
ssl_min_protocol = TLSv1.2
ssl_cert = </etc/pki/vectorcp-mail/fullchain.pem
ssl_key = </etc/pki/vectorcp-mail/key.pem
disable_plaintext_auth = yes
auth_mechanisms = plain login
auth_username_format = %%Lu
auth_cache_size = 0
auth_verbose = no
auth_debug_passwords = no
auth_failure_delay = 2 secs
mail_location = maildir:~/Maildir
mail_full_filesystem_access = no
mail_uid = %d
mail_gid = %d
first_valid_uid = %d
last_valid_uid = %d
mail_plugins = quota
mail_max_userip_connections = 8
default_process_limit = 25
default_client_limit = 100
passdb {
  driver = sql
  args = /etc/dovecot/vectorcp-sql.conf.ext
}
userdb {
  driver = sql
  args = /etc/dovecot/vectorcp-sql.conf.ext
}
namespace inbox {
  inbox = yes
  separator = /
}
protocol imap {
  mail_plugins = $mail_plugins imap_quota
}
plugin {
  quota = count:Mailbox quota
  quota_rule = *:storage=1M
  quota_vsizes = yes
  quota_grace = 0
  quota_max_mail_size = 16M
}
service imap-login {
  inet_listener imap {
    port = 0
  }
  inet_listener imaps {
    port = 993
    ssl = yes
  }
  process_min_avail = 1
}
service auth {
  unix_listener /var/spool/postfix/private/vectorcp-auth {
    mode = 0660
    user = postfix
    group = postfix
  }
}
service auth-worker {
  user = dovecot
  group = postfix
}
service lmtp {
  unix_listener /var/spool/postfix/private/vectorcp-lmtp {
    mode = 0600
    user = postfix
    group = postfix
  }
}
''' % (', '.join(listen), uid, gid, uid, uid)


def lookup_policy(directory):
    """Share only the dedicated mail lookup, never the panel DB or other config."""
    source = directory / 'vectorcp_mail.te'
    write(source, '''module vectorcp_mail 1.0;
require {
  attribute file_type;
  type dovecot_t;
  type dovecot_auth_t;
  type postfix_smtpd_t;
  type postfix_cleanup_t;
  type postfix_master_t;
  type init_t;
  class dir { getattr search open read };
  class file { getattr open read lock map ioctl };
}
type vectorcp_mail_lookup_t;
typeattribute vectorcp_mail_lookup_t file_type;
allow { dovecot_t dovecot_auth_t postfix_smtpd_t postfix_cleanup_t postfix_master_t } vectorcp_mail_lookup_t:dir { getattr search open read };
allow { dovecot_t dovecot_auth_t postfix_smtpd_t postfix_cleanup_t postfix_master_t } vectorcp_mail_lookup_t:file { getattr open read lock map ioctl };
allow init_t vectorcp_mail_lookup_t:file getattr;
''', 0o600)
    binary = directory / 'vectorcp_mail.mod'
    package = directory / 'vectorcp_mail.pp'
    run(['/usr/bin/checkmodule', '-M', '-m', '-o', str(binary), str(source)])
    run(['/usr/bin/semodule_package', '-o', str(package), '-m', str(binary)])
    run(['/usr/sbin/semodule', '-i', str(package)], timeout=120)


def readiness(hostname, address, certificate):
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(certificate))
    with socket.create_connection((address, 993), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=hostname) as secured:
            if not secured.recv(4096).startswith(b'* OK'):
                raise Fault('The encrypted IMAP listener did not become ready.')
    with smtplib.SMTP(address, 587, timeout=10) as submission:
        submission.ehlo(hostname)
        if 'auth' in submission.esmtp_features:
            raise Fault('Submission advertised authentication before TLS.')
        submission._host = hostname  # Logical certificate name with explicit IP routing.
        submission.starttls(context=context)
        submission.ehlo(hostname)
        if 'auth' not in submission.esmtp_features:
            raise Fault('Encrypted submission authentication is unavailable.')
    with smtplib.SMTP(address, 25, timeout=10) as inbound:
        inbound.ehlo(hostname)
        inbound.mail('probe@' + secrets.token_hex(16) + '.invalid')
        if inbound.rcpt('probe@' + secrets.token_hex(16) + '.invalid')[0] < 500:
            raise Fault('Anonymous external relay was not rejected.')


def install(args):
    global LOG
    if os.geteuid() != 0 or not Path('/etc/almalinux-release').exists() or not Path('/opt/vectorcp/vectorcp/mail.py').exists():
        raise Fault('Run as root after upgrading VectorCP on AlmaLinux 9.')
    if 'release 9.' not in Path('/etc/almalinux-release').read_text():
        raise Fault('This profile supports AlmaLinux 9 and Dovecot 2.3 only.')
    if not (STATE / 'hosting/enabled').is_file() or not (STATE / 'disks').is_dir():
        raise Fault('Install the isolated hosting profile before the optional mail profile.')
    if not DOMAIN.fullmatch(args.hostname) or not 128 <= args.storage_mb <= 8192:
        raise Fault('Use a full mail hostname and a storage volume between 128 and 8192 MB.')
    if shutil.disk_usage(STATE / 'disks').free < (args.storage_mb + 256 + 1024) * 1048576:
        raise Fault('Reserve space for both mail volumes plus at least 1 GB of free host-disk headroom.')
    listen = sorted(set(args.listen or ['127.0.0.1']))
    for value in listen:
        ip = ipaddress.IPv4Address(value)
        if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
            raise Fault('Use explicit assigned IPv4 listening addresses.')
    assigned = {i['local'] for link in json.loads(run(['/usr/sbin/ip', '-j', 'address', 'show'])) for i in link.get('addr_info', [])}
    if not set(listen) <= assigned:
        raise Fault('Every mail listening address must be assigned to this server.')
    for file in (args.cert, args.key):
        st = file.lstat()
        if not file.is_file() or file.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
            raise Fault('Certificate and key must be regular root-owned files without group/world write access.')
    if args.key.stat().st_mode & 0o077:
        raise Fault('The private key must only be accessible to root.')
    if 'does match certificate' not in run(['/usr/bin/openssl', 'x509', '-in', str(args.cert), '-noout', '-checkhost', args.hostname]):
        raise Fault('The TLS certificate does not cover the mail hostname.')
    run(['/usr/bin/openssl', 'x509', '-in', str(args.cert), '-noout', '-checkend', '86400'])
    cert_key = run(['/usr/bin/openssl', 'x509', '-in', str(args.cert), '-pubkey', '-noout'])
    actual_key = run(['/usr/bin/openssl', 'pkey', '-in', str(args.key), '-pubout'])
    if cert_key != actual_key:
        raise Fault('The TLS certificate and private key do not match.')
    if CONFIG.exists() or BASE.exists():
        raise Fault('An existing or interrupted mail profile was found. Inspect it instead of reinstalling.')
    for unit in ('postfix', 'dovecot', 'sendmail', 'exim'):
        result = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit])
        if result.returncode == 0:
            raise Fault('An existing mail service is active. This installer will not replace it.')
    for name in ('active', 'incoming', 'deferred', 'maildrop', 'hold'):
        folder = Path('/var/spool/postfix') / name
        if folder.is_dir() and next(folder.iterdir(), None) is not None:
            raise Fault('An existing mail queue contains messages. Refusing to adopt or deliver them.')
    for line in run(['/usr/sbin/ss', '-H', '-ltn']).splitlines():
        if line.split()[3].rsplit(':', 1)[-1] in ('25', '465', '587', '993', '143', '110', '995'):
            raise Fault('A mail port is occupied. Existing services were preserved.')
    for path in (STATE / 'dns-pending.json', Path('/run/vectorcp-profile-maintenance')):
        if path.exists() or path.is_symlink():
            raise Fault('Recover the previous profile or DNS maintenance operation first.')
    with sqlite3.connect(str(STATE / 'control.sqlite3')) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise Fault('Wait for hosting jobs before installing the mail profile.')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mailboxes'").fetchone() and db.execute('SELECT 1 FROM mailboxes LIMIT 1').fetchone():
            raise Fault('Mail records already exist. Restore their profile and storage instead of installing empty volumes.')
    # Detect customized inactive installations as well as running services.
    for package in ('postfix', 'dovecot'):
        exists = subprocess.run(['/usr/bin/rpm', '-q', package], capture_output=True).returncode == 0
        if exists and subprocess.run(['/usr/bin/rpm', '-V', package], capture_output=True).stdout:
            raise Fault('An existing mail package has modified files. Refusing to replace its configuration.')
    if not args.apply:
        print('Mail preflight passed. Check only; no changes made.')
        return
    maintenance = Path('/run/vectorcp-profile-maintenance')
    write(maintenance, 'mail-install\n', 0o600)
    backup = STATE / 'install-backups' / ('mail-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    backup.mkdir(mode=0o700, parents=True)
    LOG = backup / 'commands.jsonl'
    write(LOG, '', 0o600)
    frontends = ['vectorcp-web'] + (['vectorcp-web-public'] if Path('/etc/systemd/system/vectorcp-web-public.service').exists() else [])
    try:
        run(['/usr/bin/systemctl', 'stop'] + frontends)
        with sqlite3.connect(str(STATE / 'control.sqlite3')) as db:
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                raise Fault('A hosting job started during preflight. The agent and its worker were preserved.')
        run(['/usr/bin/systemctl', 'stop', 'vectorcp-agent'])
        run(['/usr/bin/dnf', '-y', 'install', 'postfix', 'postfix-sqlite', 'dovecot', 'checkpolicy', 'policycoreutils-python-utils', 'policycoreutils-devel'], timeout=600)
        if not run(['/usr/sbin/dovecot', '--version']).startswith('2.3.'):
            raise Fault('This profile requires Dovecot 2.3.')
        with sqlite3.connect(str(STATE / 'control.sqlite3')) as db:
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                raise Fault('A hosting job started during preflight. Retry when it has finished.')
            with sqlite3.connect(str(backup / 'control.sqlite3')) as destination:
                db.backup(destination)
        for folder, name in (('/etc/postfix', 'etc-postfix'), ('/etc/dovecot', 'etc-dovecot'), ('/var/spool/postfix', 'queue')):
            run(['/usr/bin/cp', '-a', folder, str(backup / name)])
        CONFIG.mkdir(parents=True, mode=0o700)
        BASE.mkdir(mode=0o751)
        lookup_gid = grp.getgrnam('postfix').gr_gid
        os.chown(BASE, 0, lookup_gid)
        run(['/usr/sbin/useradd', '--system', '--no-create-home', '--home-dir', str(BASE / 'store'), '--shell', '/sbin/nologin', 'vectorcp-vmail'])
        vmail = pwd.getpwnam('vectorcp-vmail')
        mount_image(STATE / 'disks/mail-store.img', args.storage_mb, BASE / 'store')
        os.chown(BASE / 'store', vmail.pw_uid, vmail.pw_gid)
        (BASE / 'store').chmod(0o700)
        mount_image(STATE / 'disks/mail-queue.img', 256, Path('/var/spool/postfix'), backup / 'queue')
        certs = Path('/etc/pki/vectorcp-mail')
        certs.mkdir(mode=0o700)
        write(certs / 'fullchain.pem', args.cert.read_bytes(), 0o644)
        write(certs / 'key.pem', args.key.read_bytes(), 0o600)
        write(Path('/etc/postfix/main.cf'), postfix_config(args.hostname, listen), 0o644)
        master = (backup / 'etc-postfix/master.cf').read_text().splitlines()
        # Disable local pickup and replace network services, retaining the
        # distribution's internal queue/delivery service definitions.
        master = [line for line in master if not line.startswith(('smtp ', 'submission ', 'smtps ', 'pickup '))]
        master += ['smtp inet n - n - 25 smtpd',
                   'submission inet n - n - 20 smtpd',
                   '  -o smtpd_tls_security_level=encrypt',
                   '  -o smtpd_sasl_auth_enable=yes',
                   '  -o smtpd_relay_restrictions=permit_sasl_authenticated,reject',
                   '  -o smtpd_sender_restrictions=check_sender_access,regexp:/etc/postfix/vectorcp-null-sender,reject_authenticated_sender_login_mismatch',
                   '  -o smtpd_recipient_restrictions=permit_sasl_authenticated,reject']
        write(Path('/etc/postfix/master.cf'), '\n'.join(master) + '\n', 0o644)
        write(Path('/etc/postfix/vectorcp-null-sender'), '/^<>$/ REJECT Empty submission senders are disabled\n', 0o644)
        for name, query in {
            'domains': "SELECT domain FROM domains WHERE domain='%s' AND active=1",
            'boxes': "SELECT address FROM boxes WHERE address='%s' AND active=1",
            'senders': "SELECT address FROM boxes WHERE address='%s' AND active=1",
        }.items():
            write(Path('/etc/postfix/vectorcp-' + name + '.cf'), 'dbpath = /var/lib/vectorcp-mail/lookup.sqlite3\nquery = ' + query + '\n', 0o644)
        write(Path('/etc/dovecot/dovecot.conf'), dovecot_config(listen, vmail.pw_uid, vmail.pw_gid), 0o644)
        sql = '''driver = sqlite
connect = /var/lib/vectorcp-mail/lookup.sqlite3
default_pass_scheme = BLF-CRYPT
password_query = SELECT address AS user,password FROM boxes WHERE address='%u' AND active=1
user_query = SELECT home,'*:storage=' || quota_mb || 'M' AS quota_rule FROM boxes WHERE address='%u' AND active=1
iterate_query = SELECT address AS user FROM boxes WHERE active=1
'''
        write(Path('/etc/dovecot/vectorcp-sql.conf.ext'), sql, 0o640, grp.getgrnam('dovecot').gr_gid)
        lookup_policy(CONFIG)
        for expression, typ in [('/var/lib/vectorcp-mail', 'var_lib_t'),
                                ('/var/lib/vectorcp-mail/lookup.*', 'vectorcp_mail_lookup_t'),
                                ('/var/lib/vectorcp-mail/pending.*', 'vectorcp_mail_lookup_t'),
                                ('/var/lib/vectorcp-mail/store(/.*)?', 'mail_spool_t'),
                                ('/etc/pki/vectorcp-mail(/.*)?', 'cert_t')]:
            run(['/usr/sbin/semanage', 'fcontext', '-a', '-t', typ, expression])
        run(['/usr/sbin/restorecon', '-RF', str(BASE), str(certs), '/var/spool/postfix', '/etc/postfix', '/etc/dovecot'])
        start_check = Path('/usr/libexec/vectorcp-mail-start-check')
        write(start_check, Path(__file__).with_name('mail_start_check.py').read_bytes(), 0o755)
        run(['/usr/sbin/restorecon', str(start_check)])
        for unit in ('postfix', 'dovecot'):
            write(Path('/etc/systemd/system/' + unit + '.service.d/vectorcp.conf'), '''[Unit]
RequiresMountsFor=/var/lib/vectorcp-mail/store /var/spool/postfix
[Service]
ExecStartPre=/usr/libexec/vectorcp-mail-start-check
MemoryMax=192M
TasksMax=64
''' , 0o644)
        write(Path('/etc/systemd/system/vectorcp-agent.service.d/mail.conf'), '''[Service]
ReadWritePaths=/var/lib/vectorcp-mail
''', 0o644)
        run(['/usr/bin/doveconf', '-n'])
        run(['/usr/sbin/postfix', 'check'])
        write(CONFIG / 'installed.json', json.dumps({'version': 1, 'hostname': args.hostname,
              'listen': listen, 'storage_mb': args.storage_mb, 'control_db': str(STATE / 'control.sqlite3'),
              'backup': str(backup)}) + '\n', 0o600)
        run(['/usr/bin/systemctl', 'daemon-reload'])
        engine = Engine(STATE, '/srv/vectorcp/sites', '/etc/nginx/conf.d')
        with engine.db() as db:
            engine.mail.checkpoint()
            engine.mail.stop()
            engine.mail.complete(engine.mail.snapshot(db))
        readiness(args.hostname, listen[0], args.cert)
        run(['/usr/bin/systemctl', 'enable', 'postfix', 'dovecot'])
        run(['/usr/bin/systemctl', 'start', 'vectorcp-agent'] + frontends)
        from .agent import rpc
        for attempt in range(100):
            try:
                if rpc('/run/vectorcp/agent.sock', {'method': 'health'}).get('ok'):
                    break
            except OSError:
                pass
            time.sleep(0.2)
        else:
            raise Fault('Mail is configured but the panel agent did not become ready. Inspect its journal.', 503)
        run(['/usr/bin/curl', '--fail', '--silent', '--max-time', '15', 'http://127.0.0.1:8765/healthz'])
        maintenance.unlink()
        print('Optional mail installed. TLS submission 587 and IMAPS 993; SMTP 25. No firewall or DNS changes made.')
        print('Private configuration and queue backup: ' + str(backup))
    except Exception:
        subprocess.run(['/usr/bin/systemctl', 'stop', 'postfix', 'dovecot'], capture_output=True)
        if CONFIG.exists() and not (BASE / 'pending.json').exists():
            write(BASE / 'pending.json', '{"installation_incomplete":true}\n', 0o600)
        # Restore panel access, leaving mail stopped for deliberate inspection.
        subprocess.run(['/usr/bin/systemctl', 'start', 'vectorcp-agent'] + frontends, capture_output=True)
        print('Mail installation is incomplete. Mail remains stopped. Inspect ' + str(backup) + ' and /run/vectorcp-profile-maintenance.')
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--hostname', required=True)
    p.add_argument('--listen', action='append')
    p.add_argument('--storage-mb', type=int, default=512)
    p.add_argument('--cert', type=Path, required=True)
    p.add_argument('--key', type=Path, required=True)
    args = p.parse_args()
    with (STATE / 'profile-maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            install(args)
        except (Fault, ValueError, OSError, subprocess.TimeoutExpired) as error:
            raise SystemExit(str(error))


if __name__ == '__main__':
    main()
