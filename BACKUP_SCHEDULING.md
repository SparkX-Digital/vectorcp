# Automatic and SFTP backups

Unreleased 0.4.3 adds per-website daily or weekly schedules and verified SFTP
copies. Owners and resellers manage websites within their existing account scope;
customers manage their own isolated websites. This remains website recovery,
not a whole-account or whole-server migration system.

## Schedules

In **Backups → Automatic backups**, choose a website, UTC hour, daily/weekly
frequency, weekly day, retained-copy count (1–4), and enabled/paused state. The
agent checks due work every 30 seconds. A busy global job defers the due run;
downtime coalesces into one run instead of replaying every missed interval.
Locked customers/resellers are skipped with a recorded failure. Removing or
pausing a schedule retains saved copies. Run now uses the same job path.

The queued job and next due time are committed together. Restarted in-flight
jobs are marked failed and are not silently replayed. Scheduling is in the
agent, so it starts with the existing agent service and needs no new public port.

Scheduled and manual copies share the existing customer ceiling: five local
copies and 512 MB; the server ceiling is 2 GB. Full copies remain bounded to
200 MB of website files and 64 MB of SQL. Host staging requires at least 512 MB
free; SFTP verification/fetch requires a second archive plus 64 MB. These are
fixed checks, not configurable staging or a guarantee against concurrent disk use.

Rotation removes only older scheduled copies belonging to that website, after a
new copy has been created and, when selected, verified at its SFTP destination.
Manual copies and other websites' copies are preserved. When allowances cannot
fit both the old and new copies, the job fails and preserves existing recovery
points. Make room manually; retention never deletes first to force a backup to fit.
An offsite failure retains the newly created local copy and fails the schedule;
retry sending that copy or make room before the next run.

## Owner-configured SFTP destinations

The server owner prepares a restricted SFTP account and existing writable remote
folder. Use an independent server for actual disaster recovery. Create a dedicated
SSH key and verify the destination's host key through a trusted channel. Do not
use an unverified key scan as proof of server identity.

Store configuration in `/var/lib/vectorcp/offsite/destinations.json`, owned by
root with mode 0600, within a root-owned mode-0700 directory. It contains a JSON
array (up to eight entries), for example:

```json
[
  {
    "id": "archive-one",
    "label": "Independent archive server",
    "host": "backup.example.invalid",
    "port": 22,
    "user": "vectorcp_archive",
    "path": "/backups/vectorcp",
    "key": "/var/lib/vectorcp/offsite/archive-one.key",
    "known_hosts": "/var/lib/vectorcp/offsite/archive-one.known_hosts"
  }
]
```

The key must be root-owned, regular and private (0600). The known-hosts file must
be root-owned, regular and not group/world writable. Avoid symlinks. Pin the exact
host/port in known_hosts, including `[host]:port` for nonstandard ports. Configure
OpenSSH SFTP on the destination. The client ignores general SSH configuration and
agents, disables password fallback, and requires strict host-key verification.
Customer API requests can select a configured ID; they cannot supply a hostname,
remote path, SSH key or command. All configured labels are available to hosted
customers; this is a shared owner-controlled destination pool, not a reseller key vault.

Full local copies have **Send offsite**. A successful job uploads to a temporary
remote filename, renames it, downloads it again and verifies size and SHA-256.
Only then is a verified inventory record stored. No remote shell command is used.
A failed connection or wrong pinned key fails visibly. Partial remote uploads can
remain after interrupted transfers; the destination owner manages their cleanup.

SFTP encrypts transport. Archives are not encrypted at rest by VectorCP and contain
website secrets such as application configuration. Restrict destination access
and apply appropriate storage encryption. Remote copies are not automatically
pruned or deleted. Monitor destination capacity separately.

**Verified offsite copies → Fetch to server** re-downloads and checks the archive
before publishing a local recovery point. It also works after the local archive
was deleted; the remote inventory is kept independently in the control database.
Then choose Restore on the local copy. Fetch never restores a website automatically.

Loss of the control database, changing site allocations, a clean-machine restore,
mail/DNS/certificate/cron recovery and cross-server account import remain pending.
Keep the control-state recovery process separate from these website archives.
S3, FTPS, monthly policies and encrypted incremental repositories are not delivered.

## Evidence

`tests/test_backup_policy.py` checks scope, UTC boundaries, persistence, busy jobs,
locked accounts, interrupted runs and retention isolation. `tests/test_offsite.py`
checks destination validation, secret handling, scoped inventories, failed
transfers and corrupt downloads. The opt-in `tests/acceptance_data_linux.py`
exercises real MariaDB, archive restore, a pinned OpenSSH SFTP fixture and scheduled
rotation with SELinux enforcing. Its SFTP fixture runs on the same disposable
guest: this proves the transfer/recovery workflow, not independent-server disaster
recovery or production capacity. Never run acceptance fixtures on customer servers.
