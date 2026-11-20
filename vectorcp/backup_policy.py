"""Persistent per-website UTC schedules, using the existing serialized jobs."""
import calendar
import datetime
import threading
import time

from .core import Fault, integer
from .distribution import available, scope

READ_ONLY = {'backups.schedules'}
OPERATIONS = READ_ONLY | {'backups.schedule.save', 'backups.schedule.delete', 'backups.schedule.run'}


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS backup_schedules (
      site_id INTEGER PRIMARY KEY REFERENCES sites(id),
      user_id INTEGER NOT NULL REFERENCES users(id),
      frequency TEXT NOT NULL, hour INTEGER NOT NULL, weekday INTEGER NOT NULL,
      keep INTEGER NOT NULL, enabled INTEGER NOT NULL, next_run INTEGER NOT NULL,
      last_run INTEGER, last_job TEXT, last_status TEXT NOT NULL DEFAULT 'never',
      last_backup TEXT, last_error TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS scheduled_backups (
      backup_id TEXT PRIMARY KEY REFERENCES backups(id) ON DELETE CASCADE,
      site_id INTEGER NOT NULL REFERENCES sites(id));
    UPDATE backup_schedules SET last_status='failed',
      last_error='The agent restarted during this run. Inspect the job and saved copies before retrying.'
      WHERE last_status='queued' AND last_job IN (SELECT id FROM jobs WHERE status='failed');
    ''')
    if 'destination' not in {r[1] for r in db.execute('PRAGMA table_info(backup_schedules)')}:
        db.execute("ALTER TABLE backup_schedules ADD COLUMN destination TEXT NOT NULL DEFAULT ''")
    if 'monthday' not in {r[1] for r in db.execute('PRAGMA table_info(backup_schedules)')}:
        db.execute('ALTER TABLE backup_schedules ADD COLUMN monthday INTEGER NOT NULL DEFAULT 1')


def next_run(now, frequency, hour, weekday, monthday=1):
    current = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    if frequency == 'monthly':
        def monthly(year, month):
            return current.replace(year=year, month=month,
                day=min(monthday, calendar.monthrange(year, month)[1]),
                hour=hour, minute=0, second=0, microsecond=0)
        candidate = monthly(current.year, current.month)
        if candidate.timestamp() <= now:
            candidate = monthly(current.year + (current.month == 12), current.month % 12 + 1)
        return int(candidate.timestamp())
    candidate = current.replace(hour=hour, minute=0, second=0, microsecond=0)
    if frequency == 'weekly':
        candidate += datetime.timedelta(days=(weekday-candidate.weekday()) % 7)
    if candidate.timestamp() <= now:
        candidate += datetime.timedelta(days=7 if frequency == 'weekly' else 1)
    return int(candidate.timestamp())


class BackupPolicy:
    def __init__(self, engine):
        self.e = engine
        self.stop = threading.Event()

    def list(self, db, actor):
        clause, args = scope(actor, 'p.user_id')
        query = '''SELECT p.*,s.domain,
          (SELECT COUNT(*) FROM backups b WHERE b.user_id=p.user_id) AS stored_copies,
          (SELECT COALESCE(SUM(bytes),0) FROM backups b WHERE b.user_id=p.user_id) AS stored_bytes
          FROM backup_schedules p JOIN sites s ON s.id=p.site_id'''
        return {'schedules': [dict(r) for r in db.execute(query + (' WHERE '+clause if clause else '') + ' ORDER BY s.domain', args)],
                'timezone': 'UTC', 'copy_limit': 5, 'byte_limit': 512 * 1024 ** 2}

    def dispatch(self, db, actor, method, data):
        if method == 'backups.schedules':
            return self.list(db, actor)
        site = self.e.owned_site(db, actor, data.get('site_id'))
        self.e.site_idle(db, site)
        owner = db.execute('SELECT * FROM users WHERE id=?', (site['user_id'],)).fetchone()
        if not available(db, owner):
            raise Fault('This customer or its reseller is locked.', 409)
        self.e.hosting.slot(owner)
        current = db.execute('SELECT * FROM backup_schedules WHERE site_id=?', (site['id'],)).fetchone()
        if method == 'backups.schedule.save':
            frequency = data.get('frequency')
            if frequency not in ('daily', 'weekly', 'monthly'):
                raise Fault('Choose a daily, weekly or monthly schedule.')
            hour = integer(data.get('hour'), 'UTC hour', 0, 23)
            weekday = integer(data.get('weekday', 0), 'weekday', 0, 6)
            monthday = integer(data.get('monthday', 1), 'monthly day', 1, 31)
            keep = integer(data.get('keep'), 'retained scheduled copies', 1, 4)
            enabled = data.get('enabled')
            if not isinstance(enabled, bool):
                raise Fault('Invalid schedule state.')
            destination = data.get('destination', '')
            if not isinstance(destination, str):
                raise Fault('Invalid offsite destination.')
            if destination:
                self.e.offsite.destination(destination)
            due = next_run(int(time.time()), frequency, hour, weekday, monthday)
            db.execute('''INSERT INTO backup_schedules(site_id,user_id,frequency,hour,weekday,keep,enabled,next_run,destination,monthday)
              VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(site_id) DO UPDATE SET frequency=excluded.frequency,
              hour=excluded.hour,weekday=excluded.weekday,keep=excluded.keep,enabled=excluded.enabled,next_run=excluded.next_run,destination=excluded.destination,monthday=excluded.monthday''',
                       (site['id'], site['user_id'], frequency, hour, weekday, keep, int(enabled), due, destination, monthday))
            self.e.log(db, actor, 'backup.schedule_saved', site['domain'])
            return {'ok': True, 'next_run': due}
        if not current:
            raise Fault('Backup schedule not found.', 404)
        if method == 'backups.schedule.delete':
            # Saved copies remain owned and downloadable after removing a policy.
            db.execute('DELETE FROM backup_schedules WHERE site_id=?', (site['id'],))
            self.e.log(db, actor, 'backup.schedule_deleted', site['domain'])
            return {'ok': True}
        if method == 'backups.schedule.run':
            return self.e.hosting_job(db, actor, 'backups.full', {'site_id': site['id']}, schedule_site=site['id'])
        raise Fault('Unknown backup policy operation.', 404)

    def retention(self, site_id):
        """Only called after a new, complete archive is durably registered.

        Never remove manual copies or another website's recovery points.
        Failure preserves remaining copies and fails the job visibly.
        """
        with self.e.lock, self.e.db() as db:
            policy = db.execute('SELECT keep FROM backup_schedules WHERE site_id=?', (site_id,)).fetchone()
            if not policy:
                return
            copies = db.execute('''SELECT b.id FROM backups b JOIN scheduled_backups p ON p.backup_id=b.id
              WHERE p.site_id=? ORDER BY b.created DESC,b.rowid DESC''', (site_id,)).fetchall()
            for row in copies[policy['keep']:]:
                (self.e.backups / (row['id'] + '.tar.gz')).unlink(missing_ok=True)
                db.execute('DELETE FROM backups WHERE id=?', (row['id'],))

    def tick(self, now=None):
        """Coalesce downtime into one run; busy jobs defer without losing a due run.

        The next due time and queued job are committed together before work starts.
        Interrupted jobs fail on startup and are never silently replayed.
        """
        now = int(time.time()) if now is None else now
        with self.e.lock, self.e.db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                return
            policy = db.execute('SELECT * FROM backup_schedules WHERE enabled=1 AND next_run<=? ORDER BY next_run,site_id LIMIT 1', (now,)).fetchone()
            if not policy:
                return
            site = db.execute('SELECT * FROM sites WHERE id=?', (policy['site_id'],)).fetchone()
            owner = db.execute('SELECT * FROM users WHERE id=?', (policy['user_id'],)).fetchone()
            due = next_run(now, policy['frequency'], policy['hour'], policy['weekday'], policy['monthday'])
            db.execute('UPDATE backup_schedules SET next_run=? WHERE site_id=?', (due, policy['site_id']))
            try:
                if not site or not owner or site['user_id'] != owner['id'] or not available(db, owner):
                    raise Fault('Scheduled backup skipped: the customer or reseller is locked.', 409)
                actor = dict(owner, role='customer')
                self.e.hosting_job(db, actor, 'backups.full', {'site_id': site['id']}, schedule_site=site['id'])
            except Fault as error:
                db.execute("UPDATE backup_schedules SET last_status='failed',last_error=?,last_run=? WHERE site_id=?", (str(error)[:300], now, policy['site_id']))

    def loop(self):
        import traceback
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            self.stop.wait(30)

    def start(self):
        worker = threading.Thread(target=self.loop, name='backup-scheduler', daemon=True)
        worker.start()
        return worker
