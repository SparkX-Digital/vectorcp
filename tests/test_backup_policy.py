import datetime
import unittest
from unittest.mock import patch

from test_boundaries import BoundaryTests as Fixture
from vectorcp.backup_policy import next_run
from vectorcp.core import Engine


class BackupPolicyTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    call = Fixture.call
    refused = Fixture.refused

    def schedule(self, **overrides):
        self.engine.hosting.enabled = True
        with self.engine.db() as db:
            db.execute('UPDATE users SET hosting_slot=1 WHERE id=?', (self.alice['user']['id'],))
        values = dict(site_id=self.a_site, frequency='daily', hour=3, weekday=0, keep=2, enabled=True)
        values.update(overrides)
        return self.call(self.alice, 'backups.schedule.save', values)

    def test_utc_daily_weekly_boundary(self):
        now = int(datetime.datetime(2026, 11, 19, 3, tzinfo=datetime.timezone.utc).timestamp())
        self.assertEqual(next_run(now, 'daily', 3, 0), now+86400)
        self.assertEqual(next_run(now-1, 'daily', 3, 0), now)
        weekly = datetime.datetime.fromtimestamp(next_run(now, 'weekly', 3, 0), datetime.timezone.utc)
        self.assertEqual(weekly.weekday(), 0)
        self.assertEqual(weekly.hour, 3)

    def test_schedule_scope_validation_and_persistence(self):
        self.schedule()
        self.assertEqual(len(self.call(self.alice, 'backups.schedules')['schedules']), 1)
        self.assertEqual(self.call(self.bob, 'backups.schedules')['schedules'], [])
        self.refused(404, lambda: self.call(self.bob, 'backups.schedule.delete', {'site_id': self.a_site}))
        self.refused(403, lambda: self.call(self.alice, 'backups.schedule.delete', {'site_id': self.a_site}, csrf='forged'))
        for values in ({'keep': 5}, {'hour': 24}, {'weekday': True}, {'frequency': 'random'}, {'enabled': 1}):
            self.refused(400, lambda: self.schedule(**values))
        second = Engine(self.engine.state, self.engine.sites, development=True)
        with second.db() as db:
            self.assertEqual(db.execute('SELECT keep FROM backup_schedules').fetchone()[0], 2)

    def test_busy_job_defers_without_consuming_due_schedule(self):
        self.schedule()
        with self.engine.db() as db:
            db.execute('UPDATE backup_schedules SET next_run=1')
            db.execute("INSERT INTO jobs VALUES('busy',?,?,'backups.full','running','busy',1,1)", (self.alice['user']['id'], self.a_site))
        with patch.object(self.engine, 'hosting_job') as queue:
            self.engine.backup_policy.tick(100)
            queue.assert_not_called()
        with self.engine.db() as db:
            self.assertEqual(db.execute('SELECT next_run FROM backup_schedules').fetchone()[0], 1)

    def test_locked_account_skipped_and_downtime_coalesced(self):
        self.schedule()
        with self.engine.db() as db:
            db.execute('UPDATE backup_schedules SET next_run=1')
            db.execute('UPDATE users SET active=0 WHERE id=?', (self.alice['user']['id'],))
        with patch.object(self.engine, 'hosting_job') as queue:
            self.engine.backup_policy.tick(100)
            queue.assert_not_called()
        with self.engine.db() as db:
            policy = db.execute('SELECT * FROM backup_schedules').fetchone()
            self.assertEqual(policy['last_status'], 'failed')
            self.assertGreater(policy['next_run'], 100)

    def test_retention_never_deletes_manual_or_other_site_copies(self):
        self.schedule(keep=1)
        with self.engine.db() as db:
            for i, (sid, scheduled) in enumerate(((self.a_site, True), (self.a_site, True), (self.a_site, False), (self.b_site, True))):
                bid = '%024x' % i
                db.execute("INSERT INTO backups VALUES(?,?,?,?,?,?,'full')", (bid, self.alice['user']['id'] if sid==self.a_site else self.bob['user']['id'], sid, 'example.com', 1, i))
                (self.engine.backups/(bid+'.tar.gz')).write_bytes(b'x')
                if scheduled:
                    db.execute('INSERT INTO scheduled_backups VALUES(?,?)', (bid, sid))
        self.engine.backup_policy.retention(self.a_site)
        self.assertFalse((self.engine.backups/('%024x.tar.gz' % 0)).exists())
        for i in (1, 2, 3):
            self.assertTrue((self.engine.backups/('%024x.tar.gz' % i)).exists())

    def test_restart_marks_interrupted_schedule_failed_without_replay(self):
        self.schedule()
        with self.engine.db() as db:
            db.execute("INSERT INTO jobs VALUES('interrupted',?,?,'backups.full','running','busy',1,1)", (self.alice['user']['id'], self.a_site))
            db.execute("UPDATE backup_schedules SET last_job='interrupted',last_status='queued'")
        second = Engine(self.engine.state, self.engine.sites, development=True)
        with second.db() as db:
            self.assertEqual(db.execute('SELECT last_status FROM backup_schedules').fetchone()[0], 'failed')
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id='interrupted'").fetchone()[0], 'failed')


del Fixture
