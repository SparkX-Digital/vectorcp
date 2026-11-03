"""Reseller delegation and immutable hosting packages.

Reservations count locked accounts too. A reseller never owns the existing
customers of the server, and cannot expand privileges beyond its own package.
"""
import sqlite3
import time
from .core import Fault, USERNAME, integer, password_hash, text

FEATURES = ('php', 'wordpress', 'databases', 'tls', 'dns', 'mail')
POOL_MB = 16384


def migrate(db):
    for table, fields in {
        'users': [('is_reseller', 'INTEGER NOT NULL DEFAULT 0'), ('parent_id', 'INTEGER REFERENCES users(id)'),
                  ('plan_id', 'INTEGER REFERENCES plans(id)'), ('admin_lock', 'INTEGER NOT NULL DEFAULT 0')],
        'sites': [('admin_hold', 'INTEGER NOT NULL DEFAULT 0')],
    }.items():
        existing = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
        for name, definition in fields:
            if name not in existing:
                db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + name + ' ' + definition)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS plans (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
      name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('customer','reseller')),
      site_limit INTEGER NOT NULL, storage_mb INTEGER NOT NULL, customer_limit INTEGER NOT NULL,
      allow_php INTEGER NOT NULL, allow_wordpress INTEGER NOT NULL, allow_databases INTEGER NOT NULL,
      allow_tls INTEGER NOT NULL, allow_dns INTEGER NOT NULL, allow_mail INTEGER NOT NULL,
      active INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
      UNIQUE(owner_id,name));
    CREATE INDEX IF NOT EXISTS customer_parents ON users(parent_id);
    ''')


def role(user):
    return 'reseller' if user['is_reseller'] else user['role']


def scope(actor, column='user_id', audit=False):
    if actor['role'] == 'admin':
        return '', ()
    if actor['role'] == 'reseller':
        sql = column + ' IN (SELECT id FROM users WHERE parent_id=?)'
        args = (actor['id'],)
        if audit:
            sql = '(' + sql + ' OR ' + column + '=?)'
            args += (actor['id'],)
        return sql, args
    return column + '=?', (actor['id'],)


def manages(db, actor, user_id):
    if actor['role'] == 'admin':
        return True
    if actor['role'] == 'reseller':
        return bool(db.execute('SELECT 1 FROM users WHERE id=? AND parent_id=? AND is_reseller=0', (user_id, actor['id'])).fetchone())
    return actor['id'] == user_id


def available(db, user):
    if not user or not user['active']:
        return False
    if user['parent_id']:
        parent = db.execute('SELECT active,is_reseller FROM users WHERE id=?', (user['parent_id'],)).fetchone()
        return bool(parent and parent['active'] and parent['is_reseller'])
    return True


class Distribution:
    def __init__(self, engine):
        self.e = engine

    def manager(self, actor):
        if actor['role'] not in ('admin', 'reseller'):
            raise Fault('Administrator or reseller access is required.', 403)

    def features(self, db, user):
        allowed = {f: True for f in FEATURES}
        for current in (user, db.execute('SELECT * FROM users WHERE id=?', (user['parent_id'],)).fetchone() if user['parent_id'] else None):
            if current and current['plan_id']:
                plan = db.execute('SELECT * FROM plans WHERE id=?', (current['plan_id'],)).fetchone()
                if not plan:
                    raise Fault('The assigned hosting plan is unavailable.', 409)
                for f in FEATURES:
                    allowed[f] = allowed[f] and bool(plan['allow_' + f])
        return allowed

    def require_feature(self, db, user, feature):
        if not self.features(db, user)[feature]:
            raise Fault('This hosting plan does not include ' + feature + '.', 403)

    def usage(self, db, reseller):
        r = db.execute('SELECT COUNT(*),COALESCE(SUM(site_limit),0),COALESCE(SUM(storage_mb),0) FROM users WHERE parent_id=?', (reseller['id'],)).fetchone()
        plan = db.execute('SELECT * FROM plans WHERE id=?', (reseller['plan_id'],)).fetchone()
        return {'customers': r[0], 'sites': r[1], 'storage_mb': r[2], 'customer_limit': plan['customer_limit'] if plan else 0,
                'site_limit': reseller['site_limit'], 'storage_limit_mb': reseller['storage_mb']}

    def reserve(self, db, actor, sites, storage, exclude=None):
        if actor['role'] == 'reseller':
            u = self.usage(db, actor)
            if exclude:
                u['customers'] -= 1
                u['sites'] -= exclude['site_limit']
                u['storage_mb'] -= exclude['storage_mb']
            if u['customers'] + 1 > u['customer_limit'] or u['sites'] + sites > u['site_limit'] or u['storage_mb'] + storage > u['storage_limit_mb']:
                raise Fault('This reseller has insufficient customer, website or storage allowance.', 409)
        else:
            used = db.execute("SELECT COALESCE(SUM(storage_mb),0) FROM users WHERE role='customer' AND parent_id IS NULL AND id<>?", (exclude['id'] if exclude else -1,)).fetchone()[0]
            if used + storage > POOL_MB:
                raise Fault('The server hosting reservations would exceed 16 GB.', 409)

    def plan_for(self, db, actor, plan_id, kind):
        plan = db.execute('SELECT * FROM plans WHERE id=? AND active=1', (integer(plan_id, 'hosting plan', 1, 2147483647),)).fetchone()
        if not plan or plan['owner_id'] != actor['id'] or plan['kind'] != kind:
            raise Fault('Choose an available hosting plan that you own.', 403)
        return plan

    def plans(self, db, actor, method, data):
        self.manager(actor)
        if method == 'plans.list':
            where, args = ('', ()) if actor['role'] == 'admin' else ('WHERE p.owner_id=?', (actor['id'],))
            rows = [dict(r) for r in db.execute('SELECT p.*,u.username AS owner,(SELECT COUNT(*) FROM users c WHERE c.plan_id=p.id) AS assigned FROM plans p JOIN users u ON u.id=p.owner_id ' + where + ' ORDER BY p.id', args)]
            return {'plans': rows, 'pool': self.usage(db, actor) if actor['role'] == 'reseller' else {'reserved_mb': db.execute("SELECT COALESCE(SUM(storage_mb),0) FROM users WHERE role='customer' AND parent_id IS NULL").fetchone()[0], 'storage_limit_mb': POOL_MB}}
        if method == 'plans.create':
            kind = data.get('kind', 'customer')
            if kind not in ('customer', 'reseller') or (kind == 'reseller' and actor['role'] != 'admin'):
                raise Fault('Only the server owner can create reseller packages.', 403)
            name = text(data.get('name'), 'plan name', 80)
            sites = integer(data.get('site_limit'), 'website allowance', 1, 1000 if kind == 'reseller' else 100)
            storage = integer(data.get('storage_mb'), 'storage allowance', 512, POOL_MB if kind == 'reseller' else 4096)
            count = integer(data.get('customer_limit', 0), 'customer allowance', 1 if kind == 'reseller' else 0, 16 if kind == 'reseller' else 0)
            flags = []
            inherited = self.features(db, actor)
            for f in FEATURES:
                val = data.get('allow_' + f, True)
                if not isinstance(val, bool):
                    raise Fault('Invalid plan feature.')
                if val and not inherited[f]:
                    raise Fault('Your reseller package does not include ' + f + '.', 403)
                flags.append(int(val))
            if flags[1] and not (flags[0] and flags[2]):
                raise Fault('WordPress requires PHP and databases.')
            if actor['role'] == 'reseller' and (sites > actor['site_limit'] or storage > actor['storage_mb']):
                raise Fault('A customer plan cannot exceed your reseller package.', 409)
            try:
                cur = db.execute('INSERT INTO plans(owner_id,name,kind,site_limit,storage_mb,customer_limit,allow_php,allow_wordpress,allow_databases,allow_tls,allow_dns,allow_mail,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                 (actor['id'], name, kind, sites, storage, count, *flags, int(time.time())))
            except sqlite3.IntegrityError:
                raise Fault('You already have a plan with that name.', 409)
            self.e.log(db, actor, 'plan.created', name)
            return {'ok': True, 'id': cur.lastrowid}
        if method == 'plans.active':
            plan = db.execute('SELECT * FROM plans WHERE id=?', (integer(data.get('id'), 'plan', 1, 2147483647),)).fetchone()
            if not plan or plan['owner_id'] != actor['id']:
                raise Fault('Hosting plan not found.', 404)
            if not isinstance(data.get('active'), bool):
                raise Fault('Invalid plan state.')
            db.execute('UPDATE plans SET active=? WHERE id=?', (int(data['active']), plan['id']))
            self.e.log(db, actor, 'plan.enabled' if data['active'] else 'plan.retired', plan['name'])
            return {'ok': True}
        if method == 'plans.assign':
            target = self.target(db, actor, data.get('id'))
            plan = self.plan_for(db, actor, data.get('plan_id'), 'reseller' if target['is_reseller'] else 'customer')
            # An administrator may assign its direct accounts, not transfer a
            # delegated customer into a package the reseller cannot administer.
            if target['parent_id'] and actor['id'] != target['parent_id']:
                raise Fault('The owning reseller must assign this customer’s plan.', 409)
            if target['hosting_slot'] is not None and plan['storage_mb'] != target['storage_mb']:
                raise Fault('This customer has a fixed hosting volume. Choose a plan with the same storage size.', 409)
            if db.execute('SELECT 1 FROM jobs WHERE (user_id=? OR user_id IN (SELECT id FROM users WHERE parent_id=?)) AND status IN (\'queued\',\'running\')', (target['id'], target['id'])).fetchone():
                raise Fault('Wait for this customer’s hosting operation to finish.', 409)
            if target['is_reseller']:
                usage = self.usage(db, target)
                if usage['customers'] > plan['customer_limit'] or usage['sites'] > plan['site_limit'] or usage['storage_mb'] > plan['storage_mb']:
                    raise Fault('The reseller’s customer reservations exceed this package.', 409)
                for child in db.execute('SELECT * FROM users WHERE parent_id=?', (target['id'],)):
                    self.check_services(db, child, plan)
                    cp = db.execute('SELECT * FROM plans WHERE id=?', (child['plan_id'],)).fetchone()
                    if cp and any(cp['allow_' + f] and not plan['allow_' + f] for f in FEATURES):
                        raise Fault('A delegated customer package requires a feature missing from this package.', 409)
                # Unused reseller plans cannot later be assigned to bypass a downgrade.
                for cp in db.execute('SELECT * FROM plans WHERE owner_id=? AND active=1', (target['id'],)):
                    if any(cp['allow_' + f] and not plan['allow_' + f] for f in FEATURES):
                        raise Fault('Retire incompatible customer plans before changing this reseller package.', 409)
            else:
                self.check_services(db, target, plan)
            self.reserve(db, actor, plan['site_limit'], plan['storage_mb'], exclude=target)
            db.execute('UPDATE users SET plan_id=?,site_limit=?,storage_mb=? WHERE id=?', (plan['id'], plan['site_limit'], plan['storage_mb'], target['id']))
            self.e.log(db, actor, 'plan.assigned', target['username'] + ': ' + plan['name'])
            return {'ok': True}
        raise Fault('Unknown plan operation.', 404)

    def check_services(self, db, user, plan):
        sites = list(db.execute('SELECT * FROM sites WHERE user_id=?', (user['id'],)))
        if len(sites) > plan['site_limit'] or self.e.account_usage(db, user['id']) > plan['storage_mb'] * 1048576:
            raise Fault('Current usage exceeds this plan.', 409)
        for s in sites:
            used = {'php': s['runtime'] != 'static', 'wordpress': s['runtime'] == 'wordpress', 'databases': bool(s['database_name']), 'tls': bool(s['tls'])}
            for feature, active in used.items():
                if active and not plan['allow_' + feature]:
                    raise Fault('An existing website uses ' + feature + ', which this plan excludes.', 409)

    def target(self, db, actor, user_id):
        self.manager(actor)
        target = db.execute('SELECT * FROM users WHERE id=?', (integer(user_id, 'account', 1, 2147483647),)).fetchone()
        if not target or target['role'] == 'admin' or not manages(db, actor, target['id']):
            raise Fault('Customer account not found.', 404)
        return target

    def accounts(self, db, actor, method, data):
        self.manager(actor)
        if method == 'accounts.list':
            where, args = ('', ()) if actor['role'] == 'admin' else ('WHERE u.parent_id=?', (actor['id'],))
            rows = []
            for row in db.execute('SELECT u.*,p.name AS plan_name FROM users u LEFT JOIN plans p ON p.id=u.plan_id ' + where + ' ORDER BY u.username', args):
                rows.append(dict(self.e.public_user(row), plan_name=row['plan_name'], features=self.features(db, row)))
            return {'accounts': rows}
        if method == 'accounts.create':
            username = text(data.get('username'), 'username', 32).lower()
            if not USERNAME.fullmatch(username):
                raise Fault('Use a valid lowercase username, 3–32 characters.')
            name = text(data.get('name'), 'name', 80)
            kind = data.get('role', 'customer')
            if kind not in ('customer', 'reseller') or (kind == 'reseller' and actor['role'] != 'admin'):
                raise Fault('Only the server owner can create resellers.', 403)
            plan = None
            if data.get('plan_id') is not None:
                plan = self.plan_for(db, actor, data['plan_id'], kind)
                # Re-evaluate inherited flags even for plans created before a package change.
                inherited = self.features(db, actor)
                if any(plan['allow_' + f] and not inherited[f] for f in FEATURES):
                    raise Fault('This plan exceeds your current reseller features.', 403)
                limit, storage = plan['site_limit'], plan['storage_mb']
            elif kind == 'reseller' or actor['role'] == 'reseller':
                raise Fault('Choose a hosting plan.')
            else:
                # Keep existing owner API clients compatible; the UI uses packages.
                limit = integer(data.get('site_limit', 5), 'site limit', 1, 100)
                storage = integer(data.get('storage_mb', 100), 'storage limit', 10, 10240)
            self.reserve(db, actor, limit, storage)
            hashed = password_hash(data.get('password'))
            try:
                cur = db.execute("INSERT INTO users(username,name,password,role,is_reseller,parent_id,plan_id,site_limit,storage_mb,created) VALUES(?,?,?,'customer',?,?,?,?,?,?)",
                                 (username, name, hashed, int(kind == 'reseller'), actor['id'] if actor['role'] == 'reseller' else None, plan['id'] if plan else None, limit, storage, int(time.time())))
            except sqlite3.IntegrityError:
                raise Fault('That username is already in use.', 409)
            self.e.log(db, actor, 'reseller.created' if kind == 'reseller' else 'account.created', username)
            return {'ok': True, 'id': cur.lastrowid}
        target = self.target(db, actor, data.get('id'))
        if not isinstance(data.get('active'), bool):
            raise Fault('Invalid account state.')
        if actor['role'] == 'reseller' and target['admin_lock']:
            raise Fault('The server owner has locked this account.', 403)
        db.execute('UPDATE users SET active=?,admin_lock=? WHERE id=?', (int(data['active']), int(actor['role'] == 'admin' and not data['active']), target['id']))
        db.execute('DELETE FROM sessions WHERE user_id=? OR user_id IN (SELECT id FROM users WHERE parent_id=?)', (target['id'], target['id']))
        self.e.log(db, actor, 'account.access_enabled' if data['active'] else 'account.access_locked', target['username'])
        return {'ok': True}
