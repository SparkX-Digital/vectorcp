"""Allowlisted hosting operations. Never execute customer PHP as root.

One non-login UID, bounded ext4 volume, mount namespace and cgroup per customer.
All long operations run as durable jobs; the web frontend holds no job secrets.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import secrets
import shutil
import socket
import stat
import subprocess
import tarfile
import threading
import tempfile
import time
import urllib.request

from .core import Fault, integer, text

MAX_ARCHIVE = 200 * 1024 * 1024
MAX_FILES = 12000


def command(argv, input=None, timeout=90):
    """Argument arrays only; deliberately never surface subprocess output/secrets."""
    result = subprocess.run(argv, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        with contextlib.suppress(OSError):
            log = Path('/var/lib/vectorcp/hosting/last-error.log')
            diagnostic = (result.stderr + result.stdout)[-6000:].decode('utf-8', 'replace')
            diagnostic = re.sub(r'[A-Za-z0-9_-]{24,}', '[redacted]', diagnostic)
            log.write_text(diagnostic)
            log.chmod(0o600)
        raise Fault('The hosting operation failed. Its previous working state was preserved where possible; inspect the server job log.', 503)
    return result.stdout


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise Fault('The upstream metadata exceeds the limit.', 503)
    return json.loads(raw)


def safe_members(archive, prefix='public', maximum=MAX_ARCHIVE, allow_hidden=False):
    """Validate the entire archive before writing anything; no links or devices."""
    members, seen, total = [], set(), 0
    for member in archive:
        parts = PurePosixPath(member.name).parts
        if (not parts or parts[0] != prefix or member.name.startswith('/') or
                any(p in ('.', '..', '') or '\\' in p for p in parts) or
                not (member.isfile() or member.isdir()) or member.name in seen):
            raise Fault('The archive contains unsafe or duplicate entries.')
        if not allow_hidden and any(p.startswith('.') for p in parts):
            raise Fault('Hidden paths are not supported in this backup format.')
        seen.add(member.name)
        total += member.size
        if total > maximum or len(seen) > MAX_FILES:
            raise Fault('The archive exceeds the restore limit.')
        members.append(member)
    if not members:
        raise Fault('The archive is empty.')
    return members, total


class Hosting:
    def __init__(self, engine):
        self.engine = engine
        self.enabled = not engine.development and (engine.state / 'hosting/enabled').exists()
        self.base = Path('/srv/vectorcp/accounts')
        self.config = Path('/etc/vectorcp/hosting')
        self.worker_lock = threading.Lock()

    def slot(self, owner):
        slot = owner['hosting_slot']
        if not self.enabled or not isinstance(slot, int) or not 1 <= slot <= 16:
            raise Fault('Enable isolated hosting for this customer first.', 409)
        return '%02d' % slot

    def root(self, slot):
        if not re.fullmatch(r'(0[1-9]|1[0-6])', slot):
            raise Fault('Invalid hosting allocation.', 500)
        return self.base / slot

    def identity(self, slot):
        return pwd.getpwnam('vectorcp-c' + slot)

    def mounted(self, slot):
        root = self.root(slot)
        if not os.path.ismount(root):
            raise Fault('Customer storage is not mounted. No files were written.', 503)
        return root

    def user_command(self, slot, argv, input=None, timeout=120):
        root = self.mounted(slot)
        if argv[0] == '/usr/bin/mariadb-install-db':
            request = {'action': 'initialize_database'}
        elif argv[:2] == ['/usr/bin/php', '/opt/vectorcp/vectorcp/wp-install.php']:
            site_id = int(Path(argv[2]).parent.name)
            request = {'action': 'install_wordpress', 'site_id': site_id, 'input': json.loads(input)}
        else:
            raise Fault('Unknown customer task.', 500)
        return self.task(slot, request, timeout=timeout)

    def task(self, slot, request, timeout=150):
        self.mounted(slot)
        command(['/usr/bin/systemctl', 'start', 'vectorcp-task' + slot + '.socket'])
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout + 30)
            client.connect('/run/vectorcp-hosting-tasks/' + slot + '.sock')
            client.sendall(json.dumps(request).encode() + b'\n')
            with client.makefile('rb') as stream:
                raw = stream.readline(8193)
        if len(raw) > 8192 or not raw.endswith(b'\n'):
            raise Fault('The customer task returned an invalid response.', 503)
        result = json.loads(raw)
        if not result.get('ok'):
            log = self.engine.state / 'hosting/last-error.log'
            log.write_text(result.get('diagnostic', '')[:4000])
            log.chmod(0o600)
            raise Fault('The customer task failed. Inspect the private hosting log.', 503)
        return b''

    def provision(self, owner):
        slot = self.slot(owner)
        image = self.engine.state / ('disks/' + slot + '.img')
        if image.exists():
            raise Fault('This storage allocation already exists; administrator review is required.', 409)
        size = integer(owner['storage_mb'], 'hosting storage', 512, 4096)
        assigned = sum(p.stat().st_size for p in image.parent.glob('*.img'))
        if assigned + size * 1024 ** 2 > 16 * 1024 ** 3 or shutil.disk_usage(image.parent).free < (size + 2048) * 1024 ** 2:
            raise Fault('Insufficient reserved host capacity for this customer.', 409)
        try:
            with image.open('xb') as stream:
                stream.truncate(size * 1024 ** 2)
            image.chmod(0o600)
            command(['/usr/sbin/mkfs.ext4', '-q', '-F', '-m', '0', str(image)])
            command(['/usr/bin/systemctl', 'start', 'srv-vectorcp-accounts-' + slot + '.mount'])
            root = self.mounted(slot)
            ident = self.identity(slot)
            os.chown(root, 0, ident.pw_gid)
            root.chmod(0o750)
            for name, mode in [('sites', 0o750), ('private', 0o700), ('tmp', 0o700), ('private/run', 0o700)]:
                p = root / name
                p.mkdir(mode=mode)
                os.chown(p, 0 if name == 'sites' else ident.pw_uid, ident.pw_gid)
                p.chmod(mode)
            command(['/usr/sbin/restorecon', '-R', str(root)])
            self.write_php(slot)
        except Exception:
            # Leave a mounted allocation for inspection instead of risking deletion.
            raise
        return slot

    def write_php(self, slot):
        root = self.mounted(slot)
        content = '''[global]
error_log = %s/private/php-error.log
daemonize = no
[customer]
listen = /run/vectorcp-hosting/%s/php.sock
listen.mode = 0660
pm = ondemand
pm.max_children = 2
pm.process_idle_timeout = 15s
pm.max_requests = 250
clear_env = yes
catch_workers_output = yes
request_terminate_timeout = 60s
security.limit_extensions = .php
php_admin_value[memory_limit] = 96M
php_admin_value[max_execution_time] = 45
php_admin_value[upload_max_filesize] = 8M
php_admin_value[post_max_size] = 10M
php_admin_value[session.save_path] = %s/tmp
php_admin_value[upload_tmp_dir] = %s/tmp
php_admin_value[sys_temp_dir] = %s/tmp
php_admin_flag[log_errors] = on
php_admin_flag[display_errors] = off
php_admin_flag[expose_php] = off
php_admin_flag[allow_url_include] = off
php_admin_value[cgi.fix_pathinfo] = 0
php_admin_value[disable_functions] = exec,passthru,shell_exec,system,proc_open,popen,pcntl_exec,dl
''' % (root, slot, root, root, root)
        path = self.config / (slot + '.conf')
        path.write_text(content)
        path.chmod(0o644)

    def own_tree(self, slot, root):
        ident = self.identity(slot)
        for folder, dirs, names in os.walk(root, followlinks=False):
            for name in dirs + names:
                p = Path(folder) / name
                if p.is_symlink():
                    raise Fault('Links cannot be installed into a hosted website.')
                os.chown(p, ident.pw_uid, ident.pw_gid, follow_symlinks=False)
                p.chmod(0o750 if p.is_dir() else 0o640)
        os.chown(root, ident.pw_uid, ident.pw_gid)
        root.chmod(0o750)

    def start_php(self, slot):
        self.mounted(slot)
        command(['/usr/bin/systemctl', 'start', 'vectorcp-php@' + slot])
        for _ in range(40):
            path = '/run/vectorcp-hosting/' + slot + '/php.sock'
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(1)
                    probe.connect(path)
                return
            except OSError:
                time.sleep(0.125)
        raise Fault('PHP did not become ready. Inspect the customer PHP log.', 503)

    def db_socket(self, slot):
        return str(self.root(slot) / 'private/run/mysql.sock')

    def start_db(self, slot):
        root = self.mounted(slot)
        data = root / 'private/mysql'
        if not (data / 'mysql').is_dir():
            self.user_command(slot, ['/usr/bin/mariadb-install-db', '--no-defaults', '--datadir=' + str(data),
                                     '--auth-root-authentication-method=socket', '--auth-root-socket-user=root', '--skip-test-db'])
            command(['/usr/sbin/restorecon', '-R', str(data)])
        command(['/usr/bin/systemctl', 'start', 'vectorcp-db@' + slot])
        for _ in range(60):
            if Path(self.db_socket(slot)).exists():
                try:
                    self.sql(slot, 'SELECT 1;')
                    return
                except Fault:
                    pass
            time.sleep(0.25)
        raise Fault('The customer database did not become ready.', 503)

    def sql(self, slot, statement):
        return command(['/usr/bin/mariadb', '--no-defaults', '--protocol=socket', '--socket=' + self.db_socket(slot),
                        '--user=root', '--batch', '--skip-column-names'], input=statement.encode(), timeout=60)

    def create_database(self, site, owner):
        slot = self.slot(owner)
        name = 'site_%d' % site['id']
        password = secrets.token_urlsafe(32)
        self.start_db(slot)
        # All SQL identifiers are generated integer IDs, all secrets URL-safe.
        self.sql(slot, "CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER '%s'@'localhost' IDENTIFIED BY '%s'; GRANT ALL ON `%s`.* TO '%s'@'localhost';" % (name, name, password, name, name))
        credentials = {'name': name, 'username': name, 'password': password, 'socket': self.db_socket(slot)}
        path = self.engine.state / ('hosting/database-%d.json' % site['id'])
        path.write_text(json.dumps(credentials))
        path.chmod(0o600)
        return credentials

    def wordpress(self, site, owner, data):
        slot = self.slot(owner)
        root = self.engine.site_root(site)
        if set(p.name for p in root.iterdir()) - {'index.html'}:
            raise Fault('WordPress requires an empty website containing only its welcome page.', 409)
        title = text(data.get('title'), 'site title', 120)
        admin = text(data.get('admin'), 'WordPress username', 40)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,39}', admin):
            raise Fault('Choose a WordPress username of 3–40 letters, numbers, dashes or underscores.')
        email = text(data.get('email'), 'administrator email', 160)
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,63}', email):
            raise Fault('Enter a valid administrator email.')
        password = data.get('password')
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise Fault('Use a WordPress password between 12 and 128 characters.')
        meta = fetch_json('https://api.wordpress.org/core/version-check/1.7/')
        offer = next((x for x in meta['offers'] if x.get('response') == 'upgrade'), meta['offers'][0])
        version = offer['version']
        if not re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', version):
            raise Fault('Unsupported WordPress release metadata.', 503)
        checksums = fetch_json('https://api.wordpress.org/core/checksums/1.0/?version=' + version + '&locale=en_US')['checksums']
        stage = root.parent / ('install-' + secrets.token_hex(8))
        tar_path = self.engine.state / ('hosting/wp-' + secrets.token_hex(8) + '.tar.gz')
        stage.mkdir(mode=0o700)
        database = None
        old = root.parent / 'before-wordpress'
        switched = False
        try:
            with urllib.request.urlopen('https://wordpress.org/wordpress-' + version + '.tar.gz', timeout=40) as stream, tar_path.open('xb') as out:
                copied = 0
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > 40 * 1024 * 1024:
                        raise Fault('The WordPress package exceeds the download limit.')
                    out.write(chunk)
            with tarfile.open(str(tar_path), 'r:gz') as archive:
                members, total = safe_members(archive, 'wordpress', allow_hidden=True)
                if shutil.disk_usage(root).free < total * 2 + 128 * 1024 ** 2:
                    raise Fault('Choose a larger hosting allowance before installing WordPress.', 409)
                extracted = set()
                for member in members:
                    relative = PurePosixPath(member.name).relative_to('wordpress')
                    dest = stage.joinpath(*relative.parts)
                    if member.isdir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        payload = archive.extractfile(member).read(MAX_ARCHIVE + 1)
                        key = str(relative)
                        if key not in checksums or hashlib.md5(payload).hexdigest() != checksums[key]:
                            raise Fault('WordPress package verification failed.', 503)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(payload)
                        extracted.add(key)
                if not {'wp-load.php', 'wp-admin/includes/upgrade.php', 'wp-settings.php'} <= extracted:
                    raise Fault('The WordPress package is incomplete.', 503)
            database = self.create_database(site, owner)
            values = {'DB_NAME': database['name'], 'DB_USER': database['username'], 'DB_PASSWORD': database['password'],
                      'DB_HOST': 'localhost:' + database['socket'], 'DB_CHARSET': 'utf8mb4', 'DB_COLLATE': ''}
            for key in ['AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT']:
                values[key] = secrets.token_urlsafe(48)
            config = '<?php\n' + ''.join("define('%s', '%s');\n" % (k, v) for k, v in values.items())
            config += "$table_prefix = 'wp_';\ndefine('DISALLOW_FILE_EDIT', true);\ndefine('WP_AUTO_UPDATE_CORE', 'minor');\n"
            config += "if (!defined('ABSPATH')) define('ABSPATH', __DIR__ . '/');\nrequire_once ABSPATH . 'wp-settings.php';\n"
            (stage / 'wp-config.php').write_text(config)
            self.own_tree(slot, stage)
            os.replace(root, old)
            os.replace(stage, root)
            switched = True
            scheme = 'https' if site['tls'] else 'http'
            install_data = json.dumps({'title': title, 'admin': admin, 'email': email, 'password': password}).encode()
            # Set the canonical URL in wp-config during installation; WordPress records it.
            p = root / 'wp-config.php'
            cfg = p.read_text().replace("$table_prefix", "define('WP_SITEURL', '%s://%s');\ndefine('WP_HOME', '%s://%s');\n$table_prefix" % (scheme, site['domain'], scheme, site['domain']))
            p.write_text(cfg)
            self.user_command(slot, ['/usr/bin/php', '/opt/vectorcp/vectorcp/wp-install.php', str(root)], input=install_data, timeout=150)
            command(['/usr/sbin/restorecon', '-R', str(root)])
            self.start_php(slot)
            self.engine.publish_config(dict(site, runtime='wordpress'), site['status'])
            shutil.rmtree(old)
            return {'runtime': 'wordpress', 'wordpress_version': version, 'database_name': database['name'], 'url': scheme + '://' + site['domain'] + '/wp-admin/'}
        except Exception:
            with contextlib.suppress(Exception):
                command(['/usr/bin/systemctl', 'stop', 'vectorcp-php@' + slot])
            if switched:
                shutil.rmtree(root, ignore_errors=True)
                os.replace(old, root)
            if database:
                with contextlib.suppress(Exception):
                    self.sql(slot, "DROP DATABASE `%s`; DROP USER '%s'@'localhost';" % (database['name'], database['name']))
            raise
        finally:
            tar_path.unlink(missing_ok=True)
            shutil.rmtree(stage, ignore_errors=True)

    def slot_for_site(self, site):
        with self.engine.db() as db:
            owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        return self.slot(owner)

    def tls(self, site):
        records = {r[4][0] for r in socket.getaddrinfo(site['domain'], 80, type=socket.SOCK_STREAM)}
        expected = self.engine.public_ipv4
        if not expected:
            raise Fault('Configure the panel public IP before issuing customer certificates.', 503)
        if records != {expected}:
            raise Fault('Point the domain A record to ' + expected + ' and remove other A/AAAA records before requesting HTTPS.', 409)
        name = 'vectorcp-site-%d' % site['id']
        command(['/opt/vectorcp-certbot/bin/certbot', 'certonly', '--non-interactive', '--agree-tos', '--register-unsafely-without-email',
                 '--webroot', '--webroot-path=/srv/vectorcp/acme', '--cert-name=' + name, '-d', site['domain']], timeout=150)
        if site['runtime'] == 'wordpress':
            with self.paused(self.slot_for_site(site)):
                self.task(self.slot_for_site(site), {'action': 'wordpress_https', 'site_id': site['id'], 'domain': site['domain']})
        self.engine.publish_config(dict(site, tls=1), site['status'])
        return {'tls': 1, 'url': 'https://' + site['domain']}

    @contextlib.contextmanager
    def paused(self, slot):
        was_active = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', 'vectorcp-php@' + slot], check=False).returncode == 0
        if was_active:
            command(['/usr/bin/systemctl', 'stop', 'vectorcp-php@' + slot])
        try:
            yield
        finally:
            if was_active:
                self.start_php(slot)

    def dump_database(self, slot, name):
        if not re.fullmatch(r'site_[1-9][0-9]*', name):
            raise Fault('Invalid database allocation.', 500)
        self.start_db(slot)
        args = ['/usr/bin/prlimit', '--fsize=67108864', '--', '/usr/bin/mariadb-dump', '--no-defaults', '--protocol=socket',
                '--socket=' + self.db_socket(slot), '--user=root', '--single-transaction', '--quick', '--hex-blob',
                '--skip-comments', '--skip-dump-date', name]
        with tempfile.TemporaryFile(dir=str(self.engine.state / 'hosting')) as output:
            result = subprocess.run(args, stdout=output, stderr=subprocess.PIPE, timeout=90)
            if result.returncode:
                raise Fault('Database backup failed or exceeds its 64 MB limit.', 409)
            output.seek(0)
            return output.read(64 * 1024 * 1024)

    def replace_database(self, slot, name, payload):
        if not re.fullmatch(r'site_[1-9][0-9]*', name):
            raise Fault('Invalid database allocation.', 500)
        self.sql(slot, 'DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' % (name, name))
        command(['/usr/bin/mariadb', '--no-defaults', '--protocol=socket', '--socket=' + self.db_socket(slot),
                 '--user=root', '--binary-mode=1', '--local-infile=0', name], input=payload)

    def full_backup(self, site, owner):
        import io
        slot = self.slot(owner)
        with self.engine.db() as db:
            usage = db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM backups WHERE user_id=?', (owner['id'],)).fetchone()
            global_size = db.execute('SELECT COALESCE(SUM(bytes),0) FROM backups').fetchone()[0]
        if usage[0] >= 5 or usage[1] >= 512 * 1024 ** 2 or global_size >= 2 * 1024 ** 3:
            raise Fault('Backup retention is full. Download and delete an older backup first.', 409)
        root = self.engine.site_root(site)
        backup_id = secrets.token_hex(12)
        target = self.engine.backups / (backup_id + '.tar.gz')
        total, count = 0, 0
        manifest = {'format': 1, 'domain': site['domain'], 'site_id': site['id'], 'runtime': site['runtime'],
                    'database_name': site['database_name'], 'wordpress_version': site['wordpress_version'], 'files': {}}
        try:
            with self.paused(slot), tarfile.open(str(target), 'w:gz') as archive:
                # PHP's entire customer cgroup is stopped while the snapshot is made.
                # Walk with open directory FDs: no symlink or hard-link expansion.
                def add_folder(fd, relative):
                    nonlocal total, count
                    for name in sorted(os.listdir(fd)):
                        if '\\' in name:
                            raise Fault('A file name is not supported by the backup format.')
                        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        rel = '/'.join(x for x in (relative, name) if x)
                        if stat.S_ISDIR(st.st_mode):
                            count += 1
                            if count > MAX_FILES:
                                raise Fault('The backup exceeds 12,000 entries.', 409)
                            info = tarfile.TarInfo('bundle/public/' + rel)
                            info.type = tarfile.DIRTYPE
                            info.mode = 0o750
                            archive.addfile(info)
                            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                            try:
                                add_folder(child, rel)
                            finally:
                                os.close(child)
                        elif stat.S_ISREG(st.st_mode):
                            count += 1
                            total += st.st_size
                            if count > MAX_FILES or total > MAX_ARCHIVE or st.st_size > 16 * 1024 ** 2:
                                raise Fault('Backup supports 200 MB total, 16 MB per file and 12,000 files.', 409)
                            f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                            with os.fdopen(f, 'rb') as stream:
                                payload = stream.read(16 * 1024 ** 2 + 1)
                            info = tarfile.TarInfo('bundle/public/' + rel)
                            info.size = len(payload)
                            info.mode = 0o640
                            archive.addfile(info, io.BytesIO(payload))
                            manifest['files'][rel] = hashlib.sha256(payload).hexdigest()
                with self.engine.directory(root) as fd:
                    add_folder(fd, '')
                if site['database_name']:
                    payload = self.dump_database(slot, site['database_name'])
                    info = tarfile.TarInfo('bundle/database.sql')
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
                    manifest['database_sha256'] = hashlib.sha256(payload).hexdigest()
                payload = json.dumps(manifest).encode()
                info = tarfile.TarInfo('bundle/manifest.json')
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            if target.stat().st_size + usage[1] > 512 * 1024 ** 2:
                raise Fault('This backup exceeds the customer backup retention allowance.', 409)
            with self.engine.db() as db:
                db.execute("INSERT INTO backups(id,user_id,site_id,domain,bytes,created,kind) VALUES(?,?,?,?,?,?,'full')",
                           (backup_id, owner['id'], site['id'], site['domain'], target.stat().st_size, int(time.time())))
            return {'id': backup_id}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def restore(self, site, owner, backup_id):
        slot = self.slot(owner)
        with self.engine.db() as db:
            row = db.execute("SELECT * FROM backups WHERE id=? AND site_id=? AND kind='full'", (backup_id, site['id'])).fetchone()
        if not row:
            raise Fault('Choose a full backup belonging to this website.', 404)
        root = self.engine.site_root(site)
        stage = root.parent / ('restore-' + secrets.token_hex(8))
        old = root.parent / ('rollback-' + secrets.token_hex(8))
        stage.mkdir(mode=0o700)
        switched = False
        before_sql = None
        try:
            with tarfile.open(str(self.engine.backups / (backup_id + '.tar.gz')), 'r:gz') as archive:
                members, total = safe_members(archive, 'bundle', MAX_ARCHIVE + 65 * 1024 ** 2, allow_hidden=True)
                if shutil.disk_usage(root).free < total + 16 * 1024 ** 2:
                    raise Fault('Restore needs free customer storage for a temporary second copy.', 409)
                member_map = {m.name: m for m in members}
                meta_member = member_map.get('bundle/manifest.json')
                if not meta_member or meta_member.size > 2 * 1024 * 1024:
                    raise Fault('The backup manifest is missing or invalid.')
                manifest = json.load(archive.extractfile(meta_member))
                if manifest.get('site_id') != site['id'] or manifest.get('database_name') != site['database_name'] or manifest.get('format') != 1:
                    raise Fault('This backup does not match the current website allocation.')
                with self.engine.db() as policy_db:
                    current_owner = policy_db.execute('SELECT * FROM users WHERE id=?', (owner['id'],)).fetchone()
                    required = ['php'] if manifest.get('runtime') in ('php', 'wordpress') else []
                    if manifest.get('runtime') == 'wordpress':
                        required += ['wordpress', 'databases']
                    for feature in required:
                        self.engine.distribution.require_feature(policy_db, current_owner, feature)
                restored = set()
                for member in members:
                    if member.name.startswith('bundle/public/') and member.isdir():
                        relative = PurePosixPath(member.name).relative_to('bundle/public')
                        stage.joinpath(*relative.parts).mkdir(parents=True, exist_ok=True)
                    if not member.name.startswith('bundle/public/') or not member.isfile():
                        continue
                    relative = PurePosixPath(member.name).relative_to('bundle/public')
                    if member.size > 16 * 1024 ** 2:
                        raise Fault('A restored file exceeds the 16 MB limit.')
                    payload = archive.extractfile(member).read(16 * 1024 ** 2 + 1)
                    if hashlib.sha256(payload).hexdigest() != manifest['files'].get(str(relative)):
                        raise Fault('Backup file integrity verification failed.')
                    dest = stage.joinpath(*relative.parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(payload)
                    restored.add(str(relative))
                if restored != set(manifest['files']):
                    raise Fault('The backup is incomplete.')
                sql = None
                if site['database_name']:
                    member = member_map.get('bundle/database.sql')
                    if not member or member.size > 64 * 1024 ** 2:
                        raise Fault('The backup database is missing or exceeds the limit.')
                    sql = archive.extractfile(member).read()
                    if hashlib.sha256(sql).hexdigest() != manifest.get('database_sha256'):
                        raise Fault('Backup database integrity verification failed.')
            with self.paused(slot):
                self.own_tree(slot, stage)
                command(['/usr/sbin/restorecon', '-R', str(stage)])
                if sql is not None:
                    before_sql = self.dump_database(slot, site['database_name'])
                    self.replace_database(slot, site['database_name'], sql)
                os.replace(root, old)
                os.replace(stage, root)
                switched = True
                self.engine.publish_config(dict(site, runtime=manifest['runtime']), site['status'])
                shutil.rmtree(old)
            return {'runtime': manifest['runtime'], 'wordpress_version': manifest.get('wordpress_version')}
        except Exception:
            if switched:
                shutil.rmtree(root, ignore_errors=True)
                os.replace(old, root)
            if before_sql is not None:
                self.replace_database(slot, site['database_name'], before_sql)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)
