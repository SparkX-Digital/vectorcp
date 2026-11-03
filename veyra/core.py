"""Authentication, ownership checks and durable state, owned by the agent.

The HTTP service never opens this database. The agent authenticates each request
itself; it does not accept a user ID, role or shell command from the web process.
"""
import base64
import contextlib
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import threading
import time

from . import __version__ as VERSION

SESSION_SECONDS = 8 * 3600
FILE_MAX = 256 * 1024
USERNAME = re.compile(r"[a-z][a-z0-9_-]{2,31}\Z")
DOMAIN = re.compile(r"(?=.{4,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")


class Fault(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise Fault("Use a password between 12 and 256 characters.")
    salt = secrets.token_bytes(24)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return "pbkdf2_sha256$600000$%s$%s" % (salt.hex(), key.hex())


def password_matches(password, stored):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def text(value, label, maximum=160):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Fault("Invalid %s." % label)
    return value.strip()


def integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Fault("Invalid %s." % label)
    return value


def run_fixed(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise Fault("System operation failed; inspect the agent log. No successful result was recorded.", 503)
    return result.stdout


class Engine:
    def __init__(self, state, sites, nginx=None, development=False):
        self.state = Path(state).absolute()
        self.sites = Path(sites).absolute()
        self.nginx = Path(nginx).absolute() if nginx else None
        self.development = development
        self.lock = threading.RLock()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state, 0o700)
        self.sites.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.backups = self.state / "backups"
        self.backups.mkdir(exist_ok=True, mode=0o700)
        self.db_path = self.state / "control.sqlite3"
        self.dummy_password = password_hash(secrets.token_urlsafe(30))
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL, password TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('admin','customer')),
              active INTEGER NOT NULL DEFAULT 1,
              site_limit INTEGER NOT NULL DEFAULT 5,
              storage_mb INTEGER NOT NULL DEFAULT 100,
              created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
              csrf TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS failures (
              username TEXT PRIMARY KEY, count INTEGER NOT NULL,
              window INTEGER NOT NULL, blocked_until INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS setup (
              id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sites (
              id INTEGER PRIMARY KEY, domain TEXT NOT NULL UNIQUE,
              user_id INTEGER NOT NULL REFERENCES users(id),
              status TEXT NOT NULL CHECK(status IN ('active','suspended')),
              created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS backups (
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
              site_id INTEGER NOT NULL REFERENCES sites(id),
              domain TEXT NOT NULL, bytes INTEGER NOT NULL, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY, user_id INTEGER, actor TEXT NOT NULL,
              action TEXT NOT NULL, target TEXT NOT NULL, created INTEGER NOT NULL);
            """)
            # Additive migration preserves existing customers, sites and sessions.
            for table, definitions in {
                'users': [('hosting_slot', 'INTEGER UNIQUE')],
                'sites': [('runtime', "TEXT NOT NULL DEFAULT 'static'"), ('tls', 'INTEGER NOT NULL DEFAULT 0'), ('wordpress_version', 'TEXT'), ('database_name', 'TEXT')],
                'backups': [('kind', "TEXT NOT NULL DEFAULT 'export'")],
            }.items():
                columns = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
                for name, definition in definitions:
                    if name not in columns:
                        # SQLite ALTER cannot add UNIQUE; the index is created below.
                        db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + name + ' ' + definition.replace(' UNIQUE', ''))
            db.executescript("""
            CREATE UNIQUE INDEX IF NOT EXISTS hosting_slots ON users(hosting_slot) WHERE hosting_slot IS NOT NULL;
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
              site_id INTEGER REFERENCES sites(id), action TEXT NOT NULL, status TEXT NOT NULL,
              message TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL);
            UPDATE jobs SET status='failed', message='The server restarted during this operation. Inspect its current state before retrying.' WHERE status IN ('queued','running');
            """)
        from .distribution import Distribution, migrate
        with self.db() as db:
            migrate(db)
        self.distribution = Distribution(self)
        from .hosting import Hosting
        self.hosting = Hosting(self)
        from .dns import DNS
        self.dns = DNS(self)
        os.chmod(self.db_path, 0o600)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(str(self.db_path), timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def setup_token(self):
        with self.lock, self.db() as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise Fault("Administrator is already configured.", 409)
            token = secrets.token_urlsafe(36)
            db.execute("INSERT OR REPLACE INTO setup VALUES(1,?,?)", (digest(token), int(time.time()) + 1800))
            return token

    def log(self, db, actor, action, target):
        db.execute("INSERT INTO audit(user_id,actor,action,target,created) VALUES(?,?,?,?,?)",
                   (actor["id"] if actor else None, actor["username"] if actor else "setup", action, str(target)[:253], int(time.time())))

    def session(self, db, user):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        db.execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
        db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(token), user["id"], csrf, int(time.time()) + SESSION_SECONDS))
        return {"token": token, "csrf": csrf, "user": self.public_user(user)}

    @staticmethod
    def public_user(user):
        result = {key: user[key] for key in ("id", "username", "name", "role", "active", "site_limit", "storage_mb", "hosting_slot", "is_reseller", "parent_id", "plan_id", "admin_lock")}
        if user['is_reseller']:
            result['role'] = 'reseller'
        return result

    def authenticate(self, db, token):
        if not isinstance(token, str) or len(token) > 128:
            raise Fault("Please sign in.", 401)
        row = db.execute("SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
                         (digest(token), int(time.time()))).fetchone()
        from .distribution import available
        if not available(db, row):
            raise Fault("Your session has expired. Please sign in.", 401)
        return dict(row, role="reseller" if row["is_reseller"] else row["role"])

    def bootstrap(self, data):
        username = text(data.get("username"), "username", 32).lower()
        name = text(data.get("name"), "name", 80)
        if not USERNAME.fullmatch(username):
            raise Fault("Use a username starting with a letter, with 3–32 lowercase letters, numbers, dashes or underscores.")
        hashed = password_hash(data.get("password"))
        with self.lock, self.db() as db:
            row = db.execute("SELECT * FROM setup WHERE id=1 AND expires>?", (int(time.time()),)).fetchone()
            token = data.get("setup_token", "")
            if not isinstance(token, str) or not row or not hmac.compare_digest(digest(token), row["token"]):
                raise Fault("The setup token is invalid or expired.", 403)
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise Fault("Setup is already complete.", 409)
            db.execute("INSERT INTO users(username,name,password,role,site_limit,storage_mb,created) VALUES(?,?,?,'admin',100,1024,?)",
                       (username, name, hashed, int(time.time())))
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            db.execute("DELETE FROM setup")
            self.log(db, user, "administrator.created", username)
            return self.session(db, user)

    def login(self, data):
        username = text(data.get("username"), "username", 32).lower()
        now = int(time.time())
        with self.lock, self.db() as db:
            failure = db.execute("SELECT * FROM failures WHERE username=?", (username,)).fetchone()
            if failure and failure["blocked_until"] > now:
                raise Fault("Too many attempts. Try again in 15 minutes.", 429)
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            valid = password_matches(data.get("password"), user["password"] if user else self.dummy_password)
            from .distribution import available
            if not valid or not available(db, user):
                count = failure["count"] + 1 if failure and now - failure["window"] < 900 else 1
                window = failure["window"] if failure and now - failure["window"] < 900 else now
                db.execute("INSERT OR REPLACE INTO failures VALUES(?,?,?,?)", (username, count, window, now + 900 if count >= 5 else 0))
                db.commit()  # Preserve failed-attempt accounting before raising.
                raise Fault("Username or password is incorrect.", 401)
            entry = data.get('entry')
            if entry is not None:
                from .distribution import role
                if entry not in ('admin', 'reseller', 'customer') or role(user) != entry:
                    raise Fault('Use the sign-in page for your account type.', 403)
            db.execute("DELETE FROM failures WHERE username=?", (username,))
            self.log(db, user, "session.created", username)
            return self.session(db, user)

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise Fault("Invalid request.")
        method, data = request.get("method"), request.get("data", {})
        if not isinstance(method, str) or not isinstance(data, dict):
            raise Fault("Invalid request.")
        if method == "health":
            return {"service": "veyra-agent", "ok": True, "version": VERSION}
        if method == "login":
            return self.login(data)
        if method == "bootstrap":
            return self.bootstrap(data)
        allowed = {"overview", "accounts.list", "accounts.create", "accounts.active", "sites.list", "sites.create", "sites.active",
                   "files.list", "files.read", "files.write", "files.mkdir", "backups.list", "backups.create", "backups.download", "audit", "logout", "hosting.enable", "hosting.php", "hosting.wordpress", "hosting.tls", "databases.create", "databases.list", "databases.credentials", "jobs.list", "backups.full", "backups.restore", "backups.delete", "backups.describe", "backups.chunk", "plans.list", "plans.create", "plans.active", "plans.assign", "dns.list", "dns.create", "dns.save", "dns.delete", "dns.export", "dns.verify"}
        if method not in allowed:
            raise Fault("Unknown operation.", 404)
        read_only = method in {"overview", "accounts.list", "sites.list", "files.list", "files.read", "backups.list", "backups.download", "audit", "jobs.list", "databases.list", "databases.credentials", "backups.describe", "backups.chunk", "plans.list", "dns.list", "dns.export"}
        with self.lock, self.db() as db:
            actor = self.authenticate(db, request.get("token"))
            if not read_only:
                csrf = request.get("csrf")
                if not isinstance(csrf, str) or not hmac.compare_digest(csrf, actor["csrf"]):
                    raise Fault("Request verification failed. Refresh and try again.", 403)
            from .distribution import scope, manages
            if method.startswith('dns.'):
                return self.dns.dispatch(db, actor, method, data)
            if method.startswith('plans.'):
                return self.distribution.plans(db, actor, method, data)
            if method == 'jobs.list':
                clause, args = scope(actor)
                where = 'WHERE ' + clause if clause else ''
                return {'jobs': [dict(r) for r in db.execute('SELECT * FROM jobs ' + where + ' ORDER BY created DESC LIMIT 30', args)]}
            if method == 'databases.list':
                clause, args = scope(actor, 's.user_id')
                where = 'AND ' + clause if clause else ''
                return {'databases': [dict(r) for r in db.execute("SELECT s.id AS site_id,s.domain,s.database_name,u.username FROM sites s JOIN users u ON u.id=s.user_id WHERE s.database_name IS NOT NULL " + where + ' ORDER BY s.domain', args)]}
            if method in ('hosting.enable', 'hosting.php', 'hosting.wordpress', 'hosting.tls', 'databases.create', 'backups.full', 'backups.restore'):
                return self.hosting_job(db, actor, method, data)
            if method == "logout":
                db.execute("DELETE FROM sessions WHERE token=?", (digest(request["token"]),))
                self.log(db, actor, "session.closed", actor["username"])
                return {"ok": True}
            if method == "overview":
                return self.overview(db, actor)
            if method == "audit":
                clause, args = scope(actor, audit=True)
                where = "WHERE " + clause if clause else ""
                return {"events": [dict(r) for r in db.execute("SELECT id,actor,action,target,created FROM audit %s ORDER BY id DESC LIMIT 100" % where, args)]}
            if method.startswith("accounts."):
                return self.distribution.accounts(db, actor, method, data)
            if method == "sites.list":
                clause, args = scope(actor, "s.user_id")
                where = "WHERE " + clause if clause else ""
                return {"sites": [dict(r) for r in db.execute("SELECT s.*,u.username FROM sites s JOIN users u ON s.user_id=u.id %s ORDER BY s.domain" % where, args)]}
            if method == "sites.create":
                return self.site_create(db, actor, data)
            if method.startswith("backups."):
                return self.backup(db, actor, method, data)
            site = self.owned_site(db, actor, data.get("site_id"))
            self.site_idle(db, site)
            if method == 'databases.credentials':
                if not site['database_name']:
                    raise Fault('This website has no database.', 404)
                path = self.state / ('hosting/database-%d.json' % site['id'])
                if not path.exists():
                    raise Fault('Credentials are managed by the website configuration.', 404)
                self.log(db, actor, 'database.credentials_viewed', site['domain'])
                return json.loads(path.read_text())
            if method == "sites.active":
                self.distribution.manager(actor)
                if actor['role'] == 'reseller' and site['admin_hold']:
                    raise Fault('The server owner has suspended this website.', 403)
                if not isinstance(data.get("active"), bool):
                    raise Fault("Invalid site state.")
                new_status = "active" if data["active"] else "suspended"
                self.publish_config(site, new_status)
                db.execute("UPDATE sites SET status=?,admin_hold=? WHERE id=?", (new_status, int(actor["role"] == "admin" and not data["active"]), site["id"]))
                self.log(db, actor, "site." + new_status, site["domain"])
                return {"ok": True}
            return self.files(db, actor, site, method, data)

    @staticmethod
    def admin(actor):
        if actor["role"] != "admin":
            raise Fault("Administrator access is required.", 403)

    def owned_site(self, db, actor, site_id):
        site = db.execute("SELECT * FROM sites WHERE id=?", (integer(site_id, "site", 1, 2147483647),)).fetchone()
        from .distribution import manages
        if not site or not manages(db, actor, site['user_id']):
            raise Fault("Website not found.", 404)
        return site

    def site_root(self, site):
        with self.db() as db:
            owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if owner and owner['hosting_slot'] is not None:
            slot = self.hosting.slot(owner)
            return self.hosting.mounted(slot) / 'sites' / str(site['id']) / 'public'
        return self.sites / str(site["id"]) / "public"

    def site_idle(self, db, site):
        if db.execute("SELECT 1 FROM jobs j WHERE j.user_id=? AND j.status IN ('queued','running')", (site['user_id'],)).fetchone():
            raise Fault('A hosting operation is running for this customer. Try again when it finishes.', 409)

    def account_usage(self, db, user_id):
        total = 0
        for row in db.execute("SELECT * FROM sites WHERE user_id=?", (user_id,)):
            root = self.site_root(row)
            for folder, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
                for name in names:
                    try:
                        st = (Path(folder) / name).lstat()
                    except FileNotFoundError:
                        continue
                    if stat.S_ISREG(st.st_mode):
                        total += st.st_size
        return total

    def site_create(self, db, actor, data):
        domain = text(data.get("domain"), "domain", 253).lower()
        if not DOMAIN.fullmatch(domain) or domain.endswith((".local", ".localhost")):
            raise Fault("Enter a public domain name, for example example.com.")
        owner_id = actor["id"]
        if actor['role'] in ('admin', 'reseller'):
            owner_id = integer(data.get('user_id', actor['id']), 'owner', 1, 2147483647)
        from .distribution import manages, available
        if not manages(db, actor, owner_id):
            raise Fault('Choose one of your customer accounts.', 404)
        owner = db.execute("SELECT * FROM users WHERE id=? AND active=1", (owner_id,)).fetchone()
        if not available(db, owner) or owner['is_reseller']:
            raise Fault('Choose an active customer account.')
        if db.execute("SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running')", (owner_id,)).fetchone():
            raise Fault('Wait for this customer’s hosting operation to finish.', 409)
        count = db.execute("SELECT COUNT(*) FROM sites WHERE user_id=?", (owner_id,)).fetchone()[0]
        if count >= owner["site_limit"]:
            raise Fault("This account has reached its website limit.", 409)
        welcome = ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                   "<title>Welcome</title><style>body{font:18px system-ui;padding:12vh 10%;color:#183536;background:#f4f7f5}"
                   "h1{font-size:48px;letter-spacing:-2px}</style><p>VEYRA PANEL</p><h1>Your website is ready.</h1>"
                   "<p>Edit index.html in your file manager to make it yours.</p></html>").encode()
        if self.account_usage(db, owner_id) + len(welcome) > owner["storage_mb"] * 1024 * 1024:
            raise Fault("This account has reached its file storage limit.", 409)
        try:
            cursor = db.execute("INSERT INTO sites(domain,user_id,status,created) VALUES(?,?,'active',?)", (domain, owner_id, int(time.time())))
        except sqlite3.IntegrityError:
            raise Fault("This domain is already assigned to an account.", 409)
        site = {"id": cursor.lastrowid, "domain": domain, "user_id": owner_id}
        root = self.site_root(site)
        if owner['hosting_slot'] is not None:
            import pwd
            ident = self.hosting.identity(self.hosting.slot(owner))
            root.parent.mkdir(mode=0o750)
            os.chown(root.parent, 0, ident.pw_gid)
        try:
            root.mkdir(parents=True, mode=0o755)
            root.chmod(0o755)
            root.parent.chmod(0o750 if owner["hosting_slot"] is not None else 0o755)
            (root / "index.html").write_bytes(welcome)
            (root / "index.html").chmod(0o644)
            if owner['hosting_slot'] is not None:
                self.hosting.own_tree(self.hosting.slot(owner), root)
                run_fixed(['/usr/sbin/restorecon', '-R', str(root)])
            self.publish_config(site, "active")
        except Exception:
            shutil.rmtree(root.parent, ignore_errors=True)
            raise
        self.log(db, actor, "site.created", domain)
        return {"ok": True, "id": site["id"]}

    def publish_config(self, site, status):
        if self.development:
            return
        if not self.nginx:
            raise Fault('Nginx integration is not configured.', 503)
        path = self.nginx / ('veyra-site-%d.conf' % site['id'])
        root = str(self.site_root(site))
        if not re.fullmatch(r'/[a-zA-Z0-9_/-]+', root) or not DOMAIN.fullmatch(site['domain']):
            raise Fault('Unsafe website configuration.', 503)
        site = dict(site)
        runtime = site.get('runtime', 'static')
        php = runtime in ('php', 'wordpress')
        challenge = 'location ^~ /.well-known/acme-challenge/ { root /srv/veyrapanel/acme; default_type text/plain; }\n'
        common = ('root %s;\nindex index.php index.html;\nautoindex off;\ndisable_symlinks on from=$document_root;\n'
                  'client_max_body_size 10m;\nadd_header X-Content-Type-Options nosniff always;\n'
                  'location ~ /\\. { deny all; }\n'
                  'location ~* ^/wp-config\\.php { return 403; }\n'
                  'location ~* \\.(sql|ini|log|bak|old|swp)$ { return 403; }\n'
                  'location ~* ^/wp-content/uploads/.*\\.(php|phtml|phar)(/|$) { return 403; }\n') % root
        if status != 'active':
            serving = 'location / { return 503; }\nlocation ~ \\.php$ { return 503; }\n'
        elif php:
            with self.db() as db:
                owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
            slot = self.hosting.slot(owner)
            serving = ('location / { try_files $uri $uri/ /index.php?$args; }\n'
                       'location ~ \\.php$ { try_files $uri =404; include /etc/nginx/fastcgi_params; '
                       'fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; '
                       'fastcgi_param HTTP_PROXY ""; fastcgi_param HTTPS $https if_not_empty; '
                       'fastcgi_pass unix:/run/veyra-hosting/%s/php.sock; fastcgi_read_timeout 70s; }\n') % slot
        else:
            serving = 'location / { try_files $uri $uri/ =404; }\nlocation ~ \\.php$ { return 403; }\n'
        serving += 'location ~* \\.(php[0-9]*)(/|$) { return 403; }\n'
        serving += 'location ~* \\.(phtml|phar|cgi|pl|py|sh)(/|$) { return 403; }\n'
        tls = bool(site.get('tls'))
        content = 'server {\nlisten 80;\nserver_name %s;\n%s' % (site['domain'], challenge)
        if tls:
            content += 'location / { return 308 https://%s$request_uri; }\n}\n' % site['domain']
            content += ('server {\nlisten 443 ssl;\nserver_name %s;\nssl_certificate /etc/letsencrypt/live/veyra-site-%d/fullchain.pem;\n'
                        'ssl_certificate_key /etc/letsencrypt/live/veyra-site-%d/privkey.pem;\nssl_protocols TLSv1.2 TLSv1.3;\nssl_session_tickets off;\n') % (site['domain'], site['id'], site['id'])
            content += common + serving + '}\n'
        else:
            content += common + serving + '}\n'
        old = path.read_bytes() if path.exists() else None
        temporary = path.with_suffix('.pending')
        try:
            temporary.write_text(content)
            temporary.chmod(0o644)
            os.replace(str(temporary), str(path))
            run_fixed(['/usr/sbin/nginx', '-t'])
            run_fixed(['/usr/bin/systemctl', 'reload', 'nginx'])
        except Exception:
            if old is None:
                path.unlink(missing_ok=True)
            else:
                temporary.write_bytes(old)
                temporary.chmod(0o644)
                os.replace(str(temporary), str(path))
            with contextlib.suppress(Exception):
                run_fixed(['/usr/sbin/nginx', '-t'])
                run_fixed(['/usr/bin/systemctl', 'reload', 'nginx'])
            raise

    @contextlib.contextmanager
    def directory(self, root, relative=""):
        if not isinstance(relative, str) or len(relative) > 512:
            raise Fault("Invalid file path.")
        parts = relative.split("/") if relative else []
        if any(p in ("", ".", "..") or p.startswith(".") or "\\" in p or len(p) > 200 for p in parts):
            raise Fault("Use a relative path without hidden folders or parent references.")
        fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = new_fd
            yield fd
        except OSError:
            raise Fault("Folder not found or access refused.", 404)
        finally:
            os.close(fd)

    def file_parts(self, path):
        path = text(path, "file path", 512)
        if path.startswith("/") or "\\" in path:
            raise Fault("Use a relative file path.")
        folder, _, name = path.rpartition("/")
        if not name or name.startswith(".") or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_. -]{0,199}", name):
            raise Fault("Invalid file name.")
        return folder, name

    def check_entry_limit(self, root):
        count = 0
        for folder, directories, files in os.walk(root, followlinks=False):
            count += len(directories) + len(files)
            directories[:] = [d for d in directories if not (Path(folder) / d).is_symlink()]
            if count >= (12000 if self.hosting.enabled else 1000):
                raise Fault("This website has reached its file and folder entry limit.", 409)

    def files(self, db, actor, site, method, data):
        root, path = self.site_root(site), data.get("path", "")
        if method == "files.list":
            result = []
            with self.directory(root, path) as fd:
                for name in sorted(os.listdir(fd))[:1000]:
                    if name.startswith("."):
                        continue
                    st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode):
                        result.append({"name": name, "directory": stat.S_ISDIR(st.st_mode), "bytes": st.st_size, "modified": int(st.st_mtime)})
            return {"files": result}
        folder, name = self.file_parts(path)
        with self.directory(root, folder) as fd:
            if method == "files.mkdir":
                self.check_entry_limit(root)
                try:
                    os.mkdir(name, 0o755, dir_fd=fd)
                    os.chmod(name, 0o755, dir_fd=fd)
                    self.file_owner(db, site, fd, name, directory=True)
                except FileExistsError:
                    raise Fault("A file or folder with that name already exists.", 409)
            elif method == "files.read":
                try:
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(file_fd, "rb") as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise Fault("Only regular files can be opened.")
                        content = stream.read(FILE_MAX + 1)
                    if len(content) > FILE_MAX:
                        raise Fault("The editor supports files up to 256 KB.")
                    result = content.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    raise Fault("This file cannot be opened as editable UTF-8 text.")
                return {"content": result, "revision": hashlib.sha256(content).hexdigest()}
            elif method == "files.write":
                content = data.get("content")
                if not isinstance(content, str) or len(content.encode()) > FILE_MAX:
                    raise Fault("The editor supports files up to 256 KB.")
                encoded, old_size = content.encode(), 0
                try:
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                except FileNotFoundError:
                    file_fd = None
                    if data.get("revision") != "new":
                        raise Fault("The file no longer exists. Refresh the file list.", 409)
                    self.check_entry_limit(root)
                except OSError:
                    raise Fault("File access refused.", 403)
                if file_fd is not None:
                    with os.fdopen(file_fd, "rb") as stream:
                        st = os.fstat(stream.fileno())
                        if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX:
                            raise Fault("This file cannot be edited.")
                        old = stream.read(FILE_MAX + 1)
                        old_size = len(old)
                    if data.get("revision") != hashlib.sha256(old).hexdigest():
                        raise Fault("The file changed since you opened it. Reopen before saving.", 409)
                owner = db.execute("SELECT storage_mb FROM users WHERE id=?", (site["user_id"],)).fetchone()
                if self.account_usage(db, site["user_id"]) - old_size + len(encoded) > owner["storage_mb"] * 1024 * 1024:
                    raise Fault("This account has reached its file storage limit.", 409)
                temporary = ".veyra-" + secrets.token_hex(12)
                try:
                    write_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
                    with os.fdopen(write_fd, "wb") as stream:
                        stream.write(encoded)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temporary, 0o644, dir_fd=fd, follow_symlinks=False)
                    self.file_owner(db, site, fd, temporary)
                    os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
                finally:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(temporary, dir_fd=fd)
                self.log(db, actor, "file.saved", site["domain"] + "/" + path)
                return {"ok": True, "revision": hashlib.sha256(encoded).hexdigest()}
            else:
                raise Fault("Unknown file operation.", 404)
        self.log(db, actor, "folder.created", site["domain"] + "/" + path)
        return {"ok": True}

    def file_owner(self, db, site, fd, name, directory=False):
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if owner['hosting_slot'] is not None:
            ident = self.hosting.identity(self.hosting.slot(owner))
            os.chown(name, ident.pw_uid, ident.pw_gid, dir_fd=fd, follow_symlinks=False)
            os.chmod(name, 0o750 if directory else 0o640, dir_fd=fd, follow_symlinks=False)

    def backup(self, db, actor, method, data):
        from .distribution import scope, manages
        if method == "backups.list":
            clause, args = scope(actor)
            where = 'WHERE ' + clause if clause else '' 
            return {"backups": [dict(row) for row in db.execute("SELECT * FROM backups %s ORDER BY created DESC" % where, args)]}
        if method in ('backups.describe', 'backups.chunk', 'backups.delete', 'backups.restore', 'backups.download'):
            backup_id = text(data.get('id'), 'backup', 32)
            if not re.fullmatch(r'[0-9a-f]{24}', backup_id):
                raise Fault('Invalid backup.')
            row = db.execute('SELECT * FROM backups WHERE id=?', (backup_id,)).fetchone()
            if not row or not manages(db, actor, row['user_id']):
                raise Fault('Backup not found.', 404)
            path = self.backups / (backup_id + '.tar.gz')
            if method == 'backups.describe':
                sha = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(262144), b''):
                        sha.update(chunk)
                return {'filename': row['domain'] + '-' + backup_id + '.tar.gz', 'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}
            if method == 'backups.chunk':
                offset = integer(data.get('offset'), 'offset', 0, 200 * 1024 * 1024)
                with path.open('rb') as stream:
                    stream.seek(offset)
                    payload = stream.read(256 * 1024)
                return {'base64': base64.b64encode(payload).decode()}
            if method == 'backups.delete':
                site = self.owned_site(db, actor, row['site_id'])
                self.site_idle(db, site)
                path.unlink(missing_ok=True)
                db.execute('DELETE FROM backups WHERE id=?', (backup_id,))
                self.log(db, actor, 'backup.deleted', row['domain'])
                return {'ok': True}
            if path.stat().st_size > 5 * 1024 * 1024:
                raise Fault('Use the panel download stream for this larger backup.', 413)
        if method == "backups.download":
            backup_id = text(data.get("id"), "backup", 32)
            row = db.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
            if not row or not manages(db, actor, row["user_id"]):
                raise Fault("Backup not found.", 404)
            payload = (self.backups / (row["id"] + ".tar.gz")).read_bytes()
            self.log(db, actor, "backup.downloaded", row["domain"])
            return {"filename": row["domain"] + "-" + row["id"] + ".tar.gz", "base64": base64.b64encode(payload).decode()}
        site = self.owned_site(db, actor, data.get("site_id"))
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if owner['hosting_slot'] is not None:
            raise Fault('Use a full backup for isolated websites.', 409)
        count = db.execute("SELECT COUNT(*) FROM backups WHERE user_id=?", (site["user_id"],)).fetchone()[0]
        if count >= 10:
            raise Fault("This account already has 10 exports. Server-side retention management is required before creating more.", 409)
        root = self.site_root(site)
        # Keep this synchronous, bounded export safe on a small development VPS.
        paths, total = [], 0
        for folder, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(folder) / d).is_symlink()]
            for name in names:
                p = Path(folder) / name
                if name.startswith(".") or not stat.S_ISREG(p.lstat().st_mode):
                    continue
                total += p.lstat().st_size
                paths.append(p)
                if total > 5 * 1024 * 1024 or len(paths) > 1000:
                    raise Fault("This release supports site exports up to 5 MB and 1,000 files.")
        backup_id = secrets.token_hex(12)
        path = self.backups / (backup_id + ".tar.gz")
        try:
            with tarfile.open(str(path), "w:gz", dereference=False) as archive:
                for p in paths:
                    archive.add(str(p), arcname=str(Path("public") / p.relative_to(root)), recursive=False)
            size = path.stat().st_size
            db.execute("INSERT INTO backups(id,user_id,site_id,domain,bytes,created) VALUES(?,?,?,?,?,?)", (backup_id, site["user_id"], site["id"], site["domain"], size, int(time.time())))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        self.log(db, actor, "backup.created", site["domain"])
        return {"ok": True, "id": backup_id}

    def hosting_job(self, db, actor, action, data):
        if not self.hosting.enabled:
            raise Fault('Isolated hosting is not installed on this server.', 409)
        site = None
        if action == 'hosting.enable':
            self.distribution.manager(actor)
            from .distribution import manages, available
            owner = db.execute("SELECT * FROM users WHERE id=? AND role='customer' AND active=1", (integer(data.get('id'), 'customer', 1, 2147483647),)).fetchone()
            if not available(db, owner) or owner['is_reseller'] or not manages(db, actor, owner['id']) or owner['hosting_slot'] is not None:
                raise Fault('Choose an active customer without a hosting allocation.', 409)
            if db.execute('SELECT 1 FROM sites WHERE user_id=?', (owner['id'],)).fetchone():
                raise Fault('Enable isolated hosting before creating this customer’s websites.', 409)
            requested = integer(data.get('storage_mb', owner['storage_mb'] if owner['plan_id'] else 1024), 'hosting storage', 512, 4096)
            if owner['plan_id'] and requested != owner['storage_mb']:
                raise Fault('Hosting storage must match the assigned plan.', 409)
            # Legacy direct accounts may choose their first physical allocation,
            # but this is still charged against the owner reservation pool.
            if not owner['plan_id']:
                self.distribution.reserve(db, actor, owner['site_limit'], requested, exclude=owner)
                db.execute('UPDATE users SET storage_mb=? WHERE id=?', (requested, owner['id']))
            data = {'storage_mb': requested}
        else:
            if action == 'backups.restore':
                backup_id = text(data.get('id'), 'backup', 32)
                row = db.execute("SELECT * FROM backups WHERE id=? AND kind='full'", (backup_id,)).fetchone()
                if not row:
                    raise Fault('Full backup not found.', 404)
                site = self.owned_site(db, actor, row['site_id'])
            else:
                site = self.owned_site(db, actor, data.get('site_id'))
            owner = db.execute('SELECT * FROM users WHERE id=? AND active=1', (site['user_id'],)).fetchone()
            from .distribution import available
            if not available(db, owner):
                raise Fault('This customer or its reseller is locked.', 409)
            needed = {'hosting.php': ('php',), 'hosting.wordpress': ('php', 'wordpress', 'databases'), 'hosting.tls': ('tls',), 'databases.create': ('databases',)}
            for feature in needed.get(action, ()):
                self.distribution.require_feature(db, owner, feature)
            self.hosting.slot(owner)
            if action == 'hosting.php' and site['runtime'] != 'static':
                raise Fault('PHP is already enabled for this website.', 409)
            if action == 'hosting.tls' and site['tls']:
                raise Fault('HTTPS is already enabled for this website.', 409)
            if action == 'databases.create' and site['database_name']:
                raise Fault('This website already has a database.', 409)
            if action == 'hosting.wordpress' and (site['runtime'] != 'static' or site['database_name']):
                raise Fault('Choose a fresh static website without a database.', 409)
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            raise Fault('A hosting operation is already running. Wait for it to finish.', 409)
        job_id, now = secrets.token_hex(12), int(time.time())
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (job_id, owner['id'], site['id'] if site else None, action, 'queued', 'Waiting to start.', now, now))
        self.log(db, actor, action + '.queued', site['domain'] if site else owner['username'])
        db.commit()
        thread = threading.Thread(target=self.run_hosting_job, args=(job_id, dict(actor), dict(owner), dict(site) if site else None, action, data), daemon=True)
        thread.start()
        return {'ok': True, 'job_id': job_id}

    def run_hosting_job(self, job_id, actor, owner, site, action, data):
        import traceback
        from .hosting import command
        try:
            with self.hosting.worker_lock:
                with self.db() as db:
                    db.execute("UPDATE jobs SET status='running',message='Working on your server.',updated=? WHERE id=?", (int(time.time()), job_id))
                result = {}
                if action == 'hosting.enable':
                    with self.db() as db:
                        used = {r[0] for r in db.execute('SELECT hosting_slot FROM users WHERE hosting_slot IS NOT NULL')}
                        slot = next((n for n in range(1, 17) if n not in used), None)
                        if slot is None:
                            raise Fault('This release supports 16 isolated customers.', 409)
                        db.execute('UPDATE users SET hosting_slot=?,storage_mb=? WHERE id=?', (slot, data['storage_mb'], owner['id']))
                        owner.update(hosting_slot=slot, storage_mb=data['storage_mb'])
                    self.hosting.provision(owner)
                elif action == 'hosting.php':
                    self.hosting.start_php(self.hosting.slot(owner))
                    self.publish_config(dict(site, runtime='php'), site['status'])
                    result = {'runtime': 'php'}
                elif action == 'databases.create':
                    credentials = self.hosting.create_database(site, owner)
                    result = {'database_name': credentials['name']}
                elif action == 'hosting.wordpress':
                    slot = self.hosting.slot(owner)
                    with self.hosting.paused(slot):
                        result = self.hosting.wordpress(site, owner, data)
                elif action == 'hosting.tls':
                    result = self.hosting.tls(site)
                elif action == 'backups.full':
                    result = self.hosting.full_backup(site, owner)
                elif action == 'backups.restore':
                    with self.hosting.paused(self.hosting.slot(owner)):
                        result = self.hosting.restore(site, owner, data['id'])
                if site:
                    allowed = {'runtime', 'tls', 'wordpress_version', 'database_name'}
                    with self.db() as db:
                        for key in allowed & result.keys():
                            db.execute('UPDATE sites SET ' + key + '=? WHERE id=?', (result[key], site['id']))
                with self.db() as db:
                    db.execute("UPDATE jobs SET status='complete',message='Completed successfully.',updated=? WHERE id=?", (int(time.time()), job_id))
                    self.log(db, actor, action + '.complete', site['domain'] if site else owner['username'])
        except Exception as error:
            traceback.print_exc()  # Faults never contain passwords or subprocess output.
            message = str(error) if isinstance(error, Fault) else 'The hosting operation failed. Inspect the server log before retrying.'
            with self.db() as db:
                db.execute("UPDATE jobs SET status='failed',message=?,updated=? WHERE id=?", (message[:300], int(time.time()), job_id))
                self.log(db, actor, action + '.failed', site['domain'] if site else owner['username'])

    @property
    def public_ipv4(self):
        if self.development:
            return '127.0.0.1'
        path = self.state / 'public-https-prepared'
        if path.exists():
            match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', path.read_text())
            if match:
                try:
                    address = ipaddress.IPv4Address(match.group(0))
                    if address.is_global:
                        return str(address)
                except ValueError:
                    pass
        return None

    def overview(self, db, actor):
        from .distribution import scope
        clause, args = scope(actor)
        where = 'WHERE ' + clause if clause else ''
        count = db.execute("SELECT COUNT(*) FROM sites " + where, args).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM sites %s %s status='active'" % (where, "AND" if where else "WHERE"), args).fetchone()[0]
        disk = shutil.disk_usage(self.sites)
        memory = None
        if Path("/proc/meminfo").exists():
            values = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if len(line.split()) >= 2 and line.split()[1].isdigit()}
            memory = {"total": values.get("MemTotal"), "available": values.get("MemAvailable")}
        uptime = float(Path("/proc/uptime").read_text().split()[0]) if Path("/proc/uptime").exists() else None
        services = []
        if not self.development:
            for name in ("nginx", "veyra-agent", "veyra-web", "sshd"):
                r = subprocess.run(["/usr/bin/systemctl", "is-active", name], capture_output=True, text=True, timeout=5, check=False)
                services.append({"name": name, "status": r.stdout.strip() or "unknown"})
        return {"public_ipv4": self.public_ipv4, "hosting_enabled": self.hosting.enabled, "user": self.public_user(actor), "csrf": actor["csrf"], "version": VERSION,
                "development": self.development, "host": {"hostname": platform.node(), "os": platform.platform(), "cpus": os.cpu_count(),
                "load": list(os.getloadavg()), "memory": memory, "disk": {"total": disk.total, "used": disk.used}, "uptime": uptime},
                "counts": {"sites": count, "active": active, "accounts": db.execute("SELECT COUNT(*) FROM users WHERE role='customer' AND is_reseller=0" + (" AND parent_id=?" if actor['role']=='reseller' else ''), (actor['id'],) if actor['role']=='reseller' else ()).fetchone()[0] if actor['role'] in ('admin','reseller') else None},
                "features": self.distribution.features(db, actor), "reseller_pool": self.distribution.usage(db, actor) if actor["role"] == "reseller" else None,
                "services": services, "usage_bytes": self.account_usage(db, actor["id"]),
                "capabilities": (["Isolated customer storage and processes", "PHP 8.3", "Private MariaDB databases", "WordPress installer", "Customer domain HTTPS", "Local files and database backup/restore"] if self.hosting.enabled else []) + ["DNS zone editor, export and private authoritative preview", "Public TXT domain ownership checks", "Reseller accounts and delegated customers", "Hosting plans and reserved allowances", "Owner locks and scoped reseller access", "Sign-in and account ownership", "Customer panel accounts", "Static websites", "Text file editor", "Site suspension", "File storage allowances", "Site export downloads", "Audit history"],
                "planned": ["Public mail service", "Public DNS delegation", "Nested resellers and white-label branding", "Shell and application runtimes", "Scheduled and off-server backups", "Billing and AI integrations"]}
