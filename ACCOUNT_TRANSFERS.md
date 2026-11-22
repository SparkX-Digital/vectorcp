# Account transfers

Development workflow for server owners and resellers managing their own customers.
Use **Account management → Account transfers** on each server.

1. On the source server, export an isolated customer and confirm its username.
   PHP pauses during the copy. Download the verified archive privately.
2. On the destination, create a customer, assign a sufficient plan and enable
   isolated hosting. The customer must have no websites.
3. Upload the archive. Interrupted uploads resume with the same file and SHA-256.
   Inspect it for the chosen customer. Resolve reported conflicts or shortages.
4. Review the inventory and confirm the destination username. Import runs as a
   background job. Refresh to follow status; review Activity and Background jobs.
5. Verify applications and new database settings, review DNS recovery copies,
   issue certificates and activate websites deliberately. Update registrar/DNS
   routing only after checks pass. Enable backup schedules separately.

Existing domain names cannot be reused on the same control-plane database. This
workflow moves accounts between servers; it cannot merge or replace an account.
Destination login, ownership, plan and security settings remain unchanged.

## Included and excluded

Included: website files (including hidden files and empty folders), the primary
SQL database of each site, redirect rules, static error-page assignments, inactive
DNS recovery copies and paused daily/weekly/monthly backup schedules.

Each database receives a new identity and password. SQL runs through that new,
database-scoped application account, without server administration, FILE or
grant permissions. Managed WordPress `define('DB_NAME', '…');` connection lines
are remapped as plain text. Custom PHP configurations must be reviewed manually;
unrecognized WordPress connection definitions stop the import. No PHP is executed
by the importer. Review all imported application code before activation.

Excluded: source login hashes, sessions, authentication keys, certificates and
private keys, extra database users/grants, stored routines and scheduled database
events, email, cron/Git jobs, backup/trash
history, offsite destinations and source ownership/package recreation. General
application connection settings are not rewritten. Public DNS publication and
ownership/delegation are separate workflows. This is not a complete disaster
recovery system or a multi-format migration tool.

## Limits

- One isolated customer, 1–10 websites per archive; destination plan must fit.
- 350 MiB compressed **and expanded**, 12,000 file/folder entries in total.
- 16 MiB per website file; 200 MiB website files in total.
- 64 MiB SQL per site, 128 MiB SQL in total; primary databases only.
- 2 MiB manifest; plain USTAR inside one gzip member. Links, devices, extended
  TAR headers, duplicate/undeclared members and unsafe paths are refused.
- Every regular file and SQL dump is checked against its size and SHA-256.
- Two retained archives per operator; eight and 2 GiB globally. Remove private
  archives after keeping the required recovery copies elsewhere.
- Inspection needs 414 MiB free private staging space. Destination capacity
  estimates files plus three times SQL bytes and 64 MiB headroom; actual SQL
  expansion may exceed this estimate and fail within the capped volume.
- SQL client output is bounded to 1 MiB, CPU to 20 seconds and wall time to
  30 seconds. Split or simplify a database outside these limits before moving it.
- Browser verification reads an archive into memory. Use a desktop browser with
  sufficient memory for larger transfers; a streaming CLI remains planned.

## Failure recovery

New websites are reserved as suspended before filesystem/database work. A
durable private journal records only those new allocations and creation intents.
An ordinary failure removes those allocations and retains the archive for review
and a fresh inspection. Pre-existing orphan paths or database identities are
refused and preserved, rather than claimed by the rollback.

A server interruption retains the journal and blocks website operations for
that customer. A PHP maintenance-stop checkpoint also survives an interrupted
export, so owner recovery can restore a source PHP service that was active before
the stop. The owner must inspect its private state and choose **Recover**,
confirming the affected customer username to retry recovery. Recovery refuses changed
allocation mappings; inspect and repair unexpected changes before retrying.
The transfer record cannot be removed while recovery remains outstanding.

SQL dumps requiring privileged DEFINER identities or server-level statements are
refused by the fresh application account. Convert these to application-scoped
objects before export; the importer never elevates SQL permissions to bypass them.

Archives contain application secrets and SQL data. They are private, unencrypted
server files and authenticated downloads: protect downloaded copies and use an
encrypted storage destination. Do not place them in a public website directory.

## Portable v1 format

The archive contains `account/manifest.json`, then only declared paths under
`account/sites/N/public/` and optional `account/sites/N/database.sql`.
The JSON object has exactly `format` (`vectorcp-account`), integer `version` (1),
`account` (`username`, `name`) and `sites` (an ordered list). Each site contains
`domain`, `runtime`, nullable `wordpress_version`, `files`, `directories`, nullable
`database`, nullable `dns`, `routing` and nullable `schedule`.

`files` maps relative paths to `{bytes, sha256}`; `directories` lists relative
paths. `database` is `{bytes, sha256}`. DNS uses the documented
[DNS records snapshot format](DNS_RECOVERY.md). Routing contains `redirects` and
`error_pages` from [website routing](WEBSITE_ROUTING.md). Schedule contains
`frequency`, `hour`, `weekday`, `monthday`, `keep`; destination/offsite references
are excluded. DNS remains unpublished, forced HTTPS is off and TLS is unset.

## ADR-001: Empty-target portable transfers

**Status:** Accepted for the development implementation

**Date:** 2026-11-22

**Deciders:** VectorCP maintainers

**Context:** Account moves must preserve unrelated customers and avoid treating
uploaded archives or SQL as privileged instructions. Native service changes can
fail or be interrupted after the control database commits.

**Decision:** Use a bounded, checksummed portable format; import into a pre-created
empty isolation allocation, with fresh SQL identities, suspended sites and a
durable creation journal. Recheck scope, conflicts, features and space at execution.

**Options considered:**

| Option | Complexity | Cost | Scaling | Assessment |
| --- | --- | --- | --- | --- |
| Merge into occupied accounts | High | No extra allocation | Flexible | Ambiguous ownership and destructive rollback risk |
| Restore full server images | High | Image storage and matching hosts | Poor per-customer portability | Restores obsolete secrets and unrelated system state |
| Empty-target portable format | Moderate | Temporary archive and staging space | Bounded single-account jobs | Explicit scope and recoverable new allocations |

**Trade-off:** Empty targets and fixed size limits reduce automation and require
manual review of secrets, mail and public routing. They make allocation ownership
and cleanup reviewable without changing an occupied destination.

**Consequences:** Multi-format import, remote transfers, extra database identities,
mail, streaming clients and full-machine recovery need separate designs and real
acceptance evidence. Format changes require a new version rather than silently
accepting additional privileged metadata.
