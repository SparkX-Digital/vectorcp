# DNS record recovery and service repair

Unreleased 0.4.3 adds bounded DNS record snapshots, safe zone removal and recovery
of interrupted publications. These recover managed DNS records and generated
service files. Keep independent backups of the control database and server
configuration; this is not clean-machine or independent-nameserver recovery.

## Record snapshots

In **DNS zones → DNS recovery copies**, save the selected domain's current
records or import a VectorCP DNS records JSON file. Import stores a copy and does
not change live records. View or download a saved copy before restoring it.
Downloads and restores check its SHA-256. Imports validate the exact domain,
record types, complete names, TTLs, duplicates and CNAME conflicts.

Snapshots contain records, source serial and creation time. They exclude
ownership tokens, account credentials, public activation and the server's DNS
profile. TXT values may contain sensitive verification data; store downloads
privately. Limits are five copies per website, 512 across the server, 100 records
per copy and 256 KB per JSON import. Copies are never silently discarded.

Restore requires the exact domain and current zone revision. Stop public hosting
before restoring an active zone. Existing records are saved as a rescue copy
first, so keep one free copy slot. Restore replaces records, advances the local
SOA and generates a new ownership challenge. Public hosting remains inactive
until ownership is checked and explicitly activated again. Private-preview
zones remain available inside the server.

**Remove zone** also requires an inactive public zone, exact domain and current
revision. It saves a recovery copy before removing records and generated service
configuration. Website files remain. Serial history is retained so restoring or
recreating the zone does not regress the SOA. **Remove copy** deletes only that
saved snapshot and never changes the current zone.

## Interrupted DNS changes

Before generated files change, VectorCP writes and syncs a private recovery
checkpoint. The checkpoint remains until records are committed and native
UDP/TCP answers match. On restart, recovery uses committed database records,
advances SOAs and rebuilds the managed service. It also handles a stopped service
whose generated zone files are damaged. A failed repair retains its checkpoint
and pauses further DNS mutations, service-profile changes and upgrades.

If the panel remains available, the server owner can select the affected website
and choose **Recover pending change**. If startup itself cannot recover, inspect
the service logs, disk space and private checkpoint on the server. Retain the
checkpoint and recovery files while diagnosing the cause. Never delete it merely
to bypass a failed consistency check.

## Owner service repair

**Repair DNS service** checks every managed zone against committed records,
rebuilds missing files and the include configuration, validates BIND and checks
authoritative SOAs over UDP and TCP. Customer records and public activation flags
remain as committed. Changed generated zone files and unreferenced `site-N.zone`
files are copied privately before replacement/removal.

Original files are retained in `/var/lib/vectorcp/dns-quarantine/` with private
permissions. Identical retries reuse retained copies. There is no automatic
purge: archive older directories privately when the eight-directory or 128 MB
ceiling is reached. Repair requires at least 64 MB additional free space. Unsafe
symlinks, writable files, oversized files or more than 256 managed zones require
owner inspection rather than automatic repair. Unrecognized filenames are left
alone. This repairs generated zone/include files, not arbitrary BIND profiles,
registrar delegation, DNSSEC keys or an unavailable independent nameserver.

## Verification

`tests/test_dns_recovery.py` covers isolation, CSRF, snapshot integrity, storage
limits, stale revisions, unsafe files, quarantine retention and interrupted
commits. The opt-in `tests/acceptance_recovery_linux.py` requires a marked,
disposable Linux guest. It exercises real BIND UDP/TCP answers, abrupt process
exits before/after commit, stopped-service recovery, damaged/missing zones,
quarantine and monthly backup rotation with SELinux enforcing. Never run its
fixture creation on a customer server. External delegation and production
capacity are separate acceptance gates.
