# Unreleased 0.4.3 optional mail hosting

Verified 23 November 2026. The development catalog records **253 workflows:
53 Available, 30 Partial and 170 Planned**. Mailbox/quota and local routing
capabilities are partial; aliases, webmail, filtering, signing and mail backup
remain open. Published 0.4.2 artifacts are unchanged.

- **220 Python unit/HTTP checks**, including **14 mailbox and 4 profile checks**, cover scoped
  access, CSRF, owner approval, reservations, secret handling, inherited access,
  publication interruption, damaged lookup recovery and stopped-profile gating.
  All 18 mail/profile checks also pass on native Python 3.9.
- Eight [native mail acceptance groups](tests/acceptance_mail_linux.py) pass on
  AlmaLinux 9.8 with Postfix 3.5.25, Dovecot 2.3.16 and SELinux enforcing. Two
  newly isolated QA customers and three mailboxes exercise verified IMAPS and
  STARTTLS submission, disabled plaintext/unused listeners, anonymous relay and
  sender denials, real queue/LMTP/IMAP delivery, cross-customer password/path and
  website-UID denials, native quota enforcement and immediate session revocation.
- A persisted checkpoint blocks service startup across an agent restart. Explicit
  owner recovery restores committed lookup data and retained mailbox messages.
  A separate four-part boot check also passes after deliberate termination and
  restart of the disposable QEMU process: startup-gate hashes persist, the
  checkpoint blocks automatic and explicit startup, committed mail records and
  nonempty message contents survive, and owner recovery restores healthy services.
  This is a VM process-crash test, not a physical host power-cut test.
- Mailbox and queue volumes are actually mounted and bounded. Native readers use
  a separate mail-only lookup with cost-12 bcrypt hashes. Customer website UIDs
  and the mail service user are denied access to the relevant private stores.
- Browser layout fits widths 320, 390, 463, 768, 1280 and 1920 without page
  overflow. Controls measure 44 px on mobile and 40 px on desktop; creation
  dialogs fit 320/390/1280 widths. No real mailbox credentials are entered into
  browser test forms.

All mail traffic in these checks stays on loopback with a private test
certificate. No public MX changes or Internet messages are part of acceptance.
WAN delivery, independent clients, signing/reputation, filtering, mail-specific
backup/restore, sustained load and independent security review remain unverified.
See [MAIL_HOSTING.md](MAIL_HOSTING.md) for installation and recovery limits.

---

# Unreleased 0.4.3 portable account transfers

Verified 22 November 2026. The development catalog records **253 workflows:
53 Available, 28 Partial and 172 Planned**. Portable v1 export is available
within [documented bounds](ACCOUNT_TRANSFERS.md); broader migration and full
disaster recovery remain partial. Published 0.4.2 artifacts are unchanged.

- All **201 Python unit/HTTP checks** pass on Python 3.13, including **18 transfer
  checks**. The transfer checks also pass on the native Python 3.9 guest. Ten
  JavaScript batch checks, JavaScript/shell syntax and deterministic source
  packaging checks pass.
- Seven [opt-in native acceptance groups](tests/acceptance_transfers_linux.py)
  pass on AlmaLinux 9.8, MariaDB 10.11, Nginx and SELinux enforcing: multi-site
  files/primary-SQL export; injected SQL-failure rollback; file hashes, table/row
  checksums, fresh credentials and SQL privilege denials; destination account and
  unrelated-record preservation; actual suspended Nginx responses; explicit
  recovery of a recorded source PHP maintenance stop; and source-site preservation.
- The native test uses a second control database and a different real customer
  volume/Unix identity on one guest to represent the destination. A deterministic
  interrupted-export checkpoint is retained across Engine initialization and
  recovered through the owner API. Unit tests simulate an interrupted import and
  verify the account hold and explicit rollback. This is not a hardware power-cut
  test, a two-machine WAN transfer or a complete clean-server restore.
- Browser checks exercise export, SHA-256-verified download, upload, conflict
  review, valid inspection, wrong-target confirmation rejection and suspended
  import. Layout fits widths 320, 390, 463, 768, 1280 and 1920 without page
  overflow. Actions measure 44 px on mobile and 40 px on desktop; upload dialogs
  fit 320/390/1280 widths without horizontal overflow.
- A private compatibility build rehearses the occupied integration layout on the
  disposable guest. The canonical installer and normal upgrade helper retain
  their documented fresh-install layout contract.

Managed WordPress connection-line rewriting is covered by unit checks; a full
WordPress application migration has not been accepted separately. Mail, extra
SQL identities/routines/events, other archive formats, remote/bulk migration,
independent DNS delegation/recovery, broader capacity and an independent security
audit remain open. Imported applications require review before activation.

---

# Unreleased 0.4.3 DNS recovery and monthly retention

Verified 20 November 2026. The development catalog records **253 workflows:
52 Available, 23 Partial and 178 Planned**. Managed DNS lifecycle/consistency
repair and daily/weekly/monthly retention are now available within documented
limits. Combined configuration restore is partial: DNS records are covered;
certificates, cron and application configuration are not.

- All **183 local Python unit/HTTP checks** pass, including 21 DNS recovery checks.
  Ten Node regressions and JavaScript, Python and shell syntax checks pass.
- Five native acceptance groups pass on the disposable AlmaLinux 9/Python 3.9
  guest with real BIND and SELinux enforcing. They cover snapshot integrity,
  restore/removal/recreation, actual abrupt exits before/after SQLite commit,
  forward SOA recovery and both UDP/TCP transports. Recovery also succeeds when
  BIND is stopped and its generated file is corrupt. The source upgrade helper
  refuses a pending DNS checkpoint and successfully preserves the guest state
  across the candidate upgrade.
- Owner service repair rebuilds missing/corrupt zones, retains changed/unreferenced
  original files privately and preserves all pre-existing record rows. Three due
  monthly jobs create real archives and rotate only the new scheduled fixture;
  every pre-existing archive is compared by SHA-256 and its database row retained.
- A startup readiness failure found during native testing was fixed with bounded
  UDP/TCP connection retries. Repeated identical quarantine copies are reused.
  The complete native acceptance was rerun successfully after these runtime fixes.

These checks do not prove public delegation, independent nameserver recovery,
mail delivery, whole-account migration, clean-machine disaster recovery,
sustained capacity or an independent security audit. DNS record snapshots remain
separate from website files/SQL archives. The immutable 0.4.2 release is unchanged.
See [DNS_RECOVERY.md](DNS_RECOVERY.md) and
[BACKUP_SCHEDULING.md](BACKUP_SCHEDULING.md) for limits.

---

# Unreleased 0.4.3 public authoritative DNS follow-up

Verified 19 November 2026. The development catalog records **253 workflows:
50 Available, 24 Partial and 179 Planned**. Public DNS hosting, diagnostics and
zone repair now have narrower implementations; none is promoted to complete
public acceptance. The immutable 0.4.2 download is unchanged.

- All **160 local Python 3.13 unit/HTTP checks** pass in 111.404 seconds, including
  profile validation, migration without publication, draft exclusion, ownership,
  CSRF, plan/account/job gates, record edits, stale forms, managed TXT, in-zone
  nameserver addresses, serial wrap, failed-publication rollback and marker loss.
  The ten Node regressions and JavaScript/shell syntax checks also pass.
- Seven prepare groups pass with real BIND 9.16.23-40.el9_8.13 in the disposable
  AlmaLinux 9 guest on Python 3.9. They cover explicit IPv4/IPv6 interface readiness
  over UDP/TCP, unassigned-interface refusal, draft exclusion and a real failed
  external ownership query; fixture-authorized activation, edits and reload
  rollback; recursion/AXFR denial; refusing profile changes with active zones;
  deactivation and invalid-profile rollback; retained maintenance on incomplete
  recovery; and SELinux enforcing. The exact 29 installed runtime files match
  the reviewed source. Normal application upgrades retain the test state.
- An off-guest process queries the running service across the VM network boundary
  through host-loopback forwarding. Both UDP and TCP return authoritative SOA
  answers with the expected serial; edited A and configured NS answers match.
  This is not an Internet port-53, parent/glue or real-domain delegation test.
- The finish phase stops public hosting, keeps zone records, rebuilds private
  previews and confirms them over UDP/TCP. Agent, web and DNS services recover;
  the disposable harness preserves an initially active web frontend. Root-private
  profile recovery copies are retained and SELinux remains enforcing.
- The actual native browser creates a quoted/HTML-like TXT value, reopens its
  plain-text form, changes TTL from 900 to 1200 and shows the saved values as text.
  Live diagnostics show current authoritative serials over UDP and TCP and label
  missing public recursive answers correctly. Record, diagnostics, stop-hosting
  and activation dialogs fit 320, 390, 463, 768, 1280 and 1920 CSS pixels without
  document/dialog horizontal overflow. Dialogs stay at or below 560 pixels;
  visible record/confirmation controls measure at least 44 pixels on phones and
  40 elsewhere. Temporary viewport overrides are cleared.

Positive ownership in native acceptance is an explicit test fixture for reserved
`.test` names. Two public-resolver matching/failure cases are unit-tested; real
public ownership, independent nameserver availability, registrar delegation,
DNSSEC, DNS control-state recovery and independent security/capacity acceptance
remain pending. Files/service updates and SQLite commit are not crash-atomic;
owner inspection and a rebuild are required after an interrupted commit. See
[PUBLIC_DNS.md](PUBLIC_DNS.md). Mail and whole-account migration remain open.
Existing live services were not upgraded or reconfigured.

---

# Unreleased 0.4.3 database and recovery follow-up

Verified 19 November 2026. The development catalog records **253 workflows:
50 Available, 21 Partial and 182 Planned**. The immutable 0.4.2 download remains
unchanged. See [DATABASE_ADMIN.md](DATABASE_ADMIN.md) and
[BACKUP_SCHEDULING.md](BACKUP_SCHEDULING.md) for limits and owner configuration.

- All **143 local Python 3.13 unit/HTTP checks** pass in 109.495 seconds. They cover the new database, scheduler, offsite
  and HTTP boundaries alongside existing authentication, hosting and file workflows.
  The ten selected-website Node regressions and JavaScript/shell syntax checks pass.
- Seven real MariaDB/SFTP/scheduler groups pass on Python 3.9 in the disposable
  AlmaLinux 9 guest, with SELinux enforcing. They exercise generated databases,
  table browsing/size reports, read-only and edited grants, other-database denial,
  password rotation/removal, SQL export, failed import rollback and denial of
  client shell/server file commands. Database grant names escape wildcards;
  import narrows the known legacy pattern and refuses unexpected global grants.
- A pinned OpenSSH SFTP fixture accepts repeat uploads and mode-0600 archives.
  Wrong host keys fail. A deleted local copy is fetched, hash-verified and used
  to restore the original SQL values. Real due schedules create files/SQL/SFTP
  copies, rotate only their own scheduled archives and preserve manual/unrelated
  recovery points. A full allowance fails without deleting existing copies.
- Native checks exposed PHP's start-limit counter during repeated intentional
  maintenance pauses. Resetting that counter before the controlled restart fixes
  consecutive backup/import jobs; crash restart settings remain unchanged.
- Browser checks use the actual native database API. HTML-like cell content is
  displayed as text. A paused weekly schedule is saved, reopened and retains its
  website, hour, weekday, state and retention fields. At 320, 390, 463, 768, 1280
  and 1920 CSS pixels, the database browser and schedule dialog have no document
  or dialog horizontal overflow; dialogs stay at or below 560 pixels and visible
  button/text/select fields measure at least 44 pixels on phones and 40 elsewhere.
  Additional-user permission forms also fit 320, 390, 768 and 1280 pixels.
  Temporary viewport overrides are reset.

The SFTP fixture is another restricted user on the same disposable guest, not
an independent offsite server. This is workflow evidence, not clean-machine
recovery, fresh installation, production capacity, a crash-atomic SQL guarantee
or an independent security audit. Public mail/DNS, whole-account migration and
other catalog gaps remain open. Existing live panel and Mustr services were not
upgraded or reconfigured by this feature batch.

---

# Unreleased 0.4.3 website routing follow-up

Verified 18 November 2026. The catalog records **253 workflows: 47 Available,
18 Partial and 188 Planned**. VCP-0504 and VCP-0505 now cover bounded website
redirects, HTTPS preferences and static HTML error pages. See
[WEBSITE_ROUTING.md](WEBSITE_ROUTING.md) for the supported behavior and limits.
The immutable 0.4.2 public download remains unchanged.

- All **124 Python unit/local HTTP executions** passed on Python 3.13 in
  78.641 seconds. New checks cover ownership/CSRF/account locks, additive settings
  migration, restart persistence, stale forms, suspension, malicious URLs/paths,
  bounds and cycles, static file/symlink limits, failed Nginx test/reload rollback,
  HTTPS preferences and the authenticated HTTP API contract.
- Ten actual Nginx checks passed in the disposable AlmaLinux 9 acceptance guest
  while SELinux remained enforcing: folder suffix/query handling, exact-rule
  precedence, destination queries, custom 403/404/500 status preservation,
  missing-file fallback, a replaced cross-site symlink, encoded header controls,
  HTTPS preferences, suspension and an unrelated virtual host. These use the
  opt-in standalone loopback driver and a self-signed fixture certificate.
  This is routing execution evidence, not fresh installation, public TLS or
  independent confinement/security acceptance for this revision.
- Actual browser controls added a folder redirect and a custom 404 page, saved,
  and reopened their persisted values. The new form uses the existing shared
  layout and control scale. At **320, 390, 463, 768, 1280 and 1920 CSS pixels**,
  neither the document nor dialog overflowed horizontally; dialog widths stayed
  at or below 560 pixels. Visible buttons and text/select fields measured at least
  44 pixels on phones and 40 pixels at larger widths. Temporary viewport overrides
  were cleared. This verifies this form, not every screen/browser.
- JavaScript syntax checks and the ten existing selected-website Node tests
  passed. Public source packaging remains deterministic and excludes credentials.

No existing live customer website or installed production panel was changed by
this feature batch. Broad mail, public DNS, migration, database administration,
release signing and the rest of the catalog remain unfinished.

---

# Unreleased 0.4.3 bulk website follow-up

Verified 5 November 2026. The catalog now records **253 workflows: 45 Available,
20 Partial and 188 Planned**. VCP-0308 adds selected-website suspension/activation
to the already implemented atomic account access/plan changes. See
[BULK_OPERATIONS.md](BULK_OPERATIONS.md).

- All 113 Python unit/local HTTP executions passed again on Python 3.13 in
  74.778 seconds, including serving the new script with the existing CSP.
- Ten Node tests passed for ordered single-request execution, activation,
  permission/not-found/busy refusals, expired sessions, uncertain server/network
  responses, stopping without retries, and input bounds before any mutation.
- Actual local-browser controls suspended and reactivated two websites, cleared
  hidden selections after filtering, and showed both per-domain results. A
  reseller batch retained the owner's hold on one website while successfully
  activating its other website. The resulting list preserved the hold and
  correct states. No public website was suspended for these tests.
- The batch uses the existing `sites.active` privileged endpoint and its current
  authorization/configuration behavior. It adds no new privileged batch API.
  Native endpoint/owner-hold evidence is retained below; this follow-up browser
  batch itself was exercised locally, not against the native guest. Native
  evidence for PR #4 does not assert that this changed frontend was installed.
- JavaScript syntax and diff checks passed. The new batch UI uses the existing
  shared table, toolbar, dialog, selection and control styles. At the 463-pixel
  browser viewport it retains the table's contained horizontal scrolling, has
  no document overflow, and all visible buttons are at least 44 pixels high.

Website batches retain completed items and report refusals. They stop after an
uncertain response or session expiry. They do not resume after closing the page.
This remains development source, without a stable release or independent audit.

---

# Unreleased 0.4.3 account, security and file workflow verification

Verified 4 November 2026. This development source adds ten completed workflows;
the catalog contains **253 workflows: 44 Available, 21 Partial and 188 Planned**.
The immutable published 0.4.2 download is unchanged. The systems below describe
current source, with the limits in [ACCOUNT_SECURITY.md](ACCOUNT_SECURITY.md)
and [FILE_MANAGER.md](FILE_MANAGER.md), rather than full product parity.

## Automated checks

The final local Python 3.13 run passed **113 unittest executions** in 70.805
seconds. Tests cover scoped sessions, revocation, authenticator/recovery replay,
enrollment expiry and attempts, password policy/rotation, contact and account
scope, atomic account batches, additive legacy-session migration, hidden paths,
file permissions, no-overwrite text publication, recursive copy, per-item file
batches, private trash/quota/restart receipts, and ZIP safety/limits/CRC failures.
The published RFC authenticator vectors are checked. Test discovery retains an
existing imported fixture class, so execution counts are not unique-test claims.
JavaScript, Python, deployment shell syntax, source packaging and diff checks pass.

Native Python 3.9.25 tests run on the same disposable AlmaLinux 9.8 x86-64 guest
used for the 0.4.2 acceptance below. The complete final suite passed 113 executions in 111.296 seconds; the affected
security, file, archive and trash groups also passed during review. The guest remains in SELinux
Enforcing mode; no host firewall or existing website configuration was changed.

## Installed-service acceptance

The actual upgrade helper moved the initialized native guest to source version
0.4.3, preserving its existing owner session, customer sites and service layout.
The opt-in [workflow acceptance driver](tests/acceptance_workflows_linux.py)
passed all **13 installed-service checks**:

- Existing sessions migrate into a private inventory; revocation takes effect.
- Authenticator enrollment/recovery sign-in works without a provisional session.
- Managed reset revokes sessions, preserves MFA, blocks tools until rotation,
  and the chosen new password restores access.
- Contact editing, account search and details remain scoped.
- The installed unprivileged HTTP frontend issues a strict HTTP-only cookie only
  after the required second factor succeeds.
- Recursive copies include hidden contents, retain the correct customer Unix
  identity, and can be read through the actual Nginx virtual host.
- ZIP create/extract preserves hidden contents and rejects an unrelated customer.
- Permission changes retain customer ownership; trash restore survives an actual
  agent restart on the mounted customer volume.
- Only newly created verification files are purged; the additional verification
  account is locked, and enforcing SELinux remains active.

The final private acceptance candidate was SHA-256
`86f13bd006ae4df979e65662650b35b64c96e665208fe4945d1d577c4122bd3f`.
All ten installed Python/frontend file SHA-256 values match commit
`6ceb93adc1c1519a68ca1910fdf3f0dd25e4e251` (PR #4). The subsequent bulk-website UI
follow-up documented above is separate from that native acceptance candidate. Private fixture credentials and customer configuration
are excluded from the result summary and source. No stable release or independent
security audit is claimed.

## Interface checks

The new Accounts, Account & security and File manager pages were measured at
320, 390, 463, 768, 1280 and 1920 px. No document overflow or visible button below
the shared 40 px desktop / 44 px phone minimum was observed. Temporary viewport
overrides were cleared.

Actual browser controls exercised account search/details/contact editing,
remote session revocation, hidden-file editing, recursive copy, batch copy,
trash/restore and ZIP create/extract. Existing-credential two-factor sign-in and
the temporary-password tool gate were also verified. Credential changes and
permanent purge used isolated backend/native fixtures; their browser dialogs
were inspected without changing retained user credentials or deleting user data.

The security review was performed by the implementing agent and added regression
fixes for password-comparison errors, counter namespaces, text-save conflicts,
permission preservation, ZIP creation/extraction limits and trash receipt sync
ordering. It is not an independent audit. Wider production load, hostile live
application races, power-loss/disaster recovery, secret encryption, mail/public
DNS, migration, alternate platforms and the rest of the catalog remain unfinished.

---

# VectorCP 0.4.2 file operations and native installation verification

Verified 3 November 2026. This remains a development snapshot. The catalog now
contains **253 workflows: 34 Available, 26 Partial and 193 Planned**. Fresh-host
installation, application upgrade/startup rollback and bounded individual file
transfers now have implementation and acceptance evidence. Copy/move, permanent
removal and search have narrower implementations; their broader catalog rows
remain Partial.

## Automated and browser checks

All 70 local unit and HTTP tests passed on Python 3.13 in 43.631 seconds.
They include tenant and actor ownership, CSRF, traversal/symlinks/special files,
no-overwrite conflicts, changed-source revisions, upload offset retries,
checksum rejection, staging/entry/quota limits, agent restart recovery, simulated
full storage, scoped search and a complete binary transfer through HTTP.
The setup-token regression check preserves a live running job. Maintenance
blocks new hosting jobs. JavaScript, Python and deployment shell syntax passed.

The actual file-manager interface was checked at 320, 390, 463, 768, 1280 and
1920 px widths: no document overflow and no visible button below the shared
40 px desktop / 44 px phone minimum. A 3,145,984-byte binary was uploaded,
downloaded, copied, renamed and found using the actual browser controls.
The local source, stored upload, copy and downloaded file had identical SHA-256:
`679361bf172a2b2f3d48919ee7b2b6fea9cf6e351005736ac7274ac8fde4e0f2`.
Permanent removal was exercised by backend/native acceptance; its browser
confirmation and Cancel path were checked without deleting retained user data.

## Native clean-host evidence

A private disposable KVM guest used the official AlmaLinux 9.8 x86-64 GenericCloud
image `AlmaLinux-9-GenericCloud-9.8-20261102.x86_64.qcow2`. Its checksum was verified
against the signed official CHECKSUM using the AlmaLinux 9 signing key:

- Image SHA-256: `6f94881458dfe966474544b12e86d078d81a600457188045d317b0ce3c3bdca7`.
- Signing-key fingerprint: `BF18AC2876178908D6E71267D36CB86CB86B3716`.
- Guest: one vCPU, 1,536 MiB configured RAM and a 16 GiB sparse disk. The host
  bounded the test workload's CPU and memory and exposed guest SSH on host
  loopback only. No public firewall or existing website configuration changed.

An empty second guest installed the 0.4.2 candidate with `install.sh --check`
and `--apply`, then the native hosting and private DNS helpers. The published
opt-in `tests/acceptance_linux.py` completed its checks on that installation:

- Panel, web, Nginx and private DNS active with SELinux Enforcing.
- Fresh installer refuses an existing application; private owner setup works.
- Two 512 MiB customer volumes and correctly scoped customer sessions/sites.
- Customer PHP and private MariaDB work; reads of a sibling volume and control
  database fail. Database network permission remains off; no TCP SQL listener.
- A local files/SQL backup restores both the website file and database value,
  retaining a working PHP site.
- A 3,145,984-byte binary upload resumes after restarting the agent; verified
  download, idempotent finish, copy, move, search and removal work on actual
  isolated customer storage.

The clean candidate archive used for this run was SHA-256
`4df048c80ba51091f04edfc40f8915bd04d9dfa9b2c1f2501afa0b233b69faf5`.
It is a private acceptance fixture, not the immutable public source archive;
publication adds the final evidence documentation without changing those runtime
files. See [LINUX_ACCEPTANCE.md](LINUX_ACCEPTANCE.md) to reproduce the procedure.

## Upgrade and reboot evidence

A first disposable guest installed the previous 0.4.1 source and exposed two
fresh-profile issues: missing certificate directories broke agent mount setup,
and new DNS writable paths did not take effect without restarting the agent.
The 0.4.2 helpers fixed both; retry recovered the guest and passed native hosting
and backup/restore checks.

The actual application upgrade helper then upgraded that initialized guest to
0.4.2 while preserving owner/customer sessions, files and SQL. Applying a private
source copy with a deliberate import-time failure triggered startup rollback.
The helper restored the previous application and retained its database snapshot;
the authenticated panel and PHP/database probe worked afterwards.

A guest reboot changed its boot ID. Both customer ext4 volumes remounted;
panel, web, Nginx, DNS, customer PHP and database services recovered. The PHP
probe returned the restored SQL value and continued to deny sibling/control
state reads. The existing integration host's services remained active.

## Remaining boundaries

This work does not verify trusted public certificate issue/renewal under the new
layout, public DNS delegation, mail, older-layout migration, independent disaster
recovery, alternate platforms, sustained hostile load or a production security
audit. The existing 0.3.x integration installation is still running its original
backend layout; new APIs are accepted on the private native 0.4.2 installation.
Do not deploy its new frontend onto an older backend or rename active storage.
The wider unfinished catalog remains accurately marked.

Earlier evidence below is retained for its original version and scope.

---

# VectorCP 0.4.1 interface snapshot verification

All 56 existing tests passed locally on Python 3.13 in 42.998 seconds during
the interface change. No hosting, authentication, database schema or privileged
operation implementation changed. JavaScript syntax passed.

The actual local application was exercised with owner, reseller and customer
sessions at a 463 px phone viewport. Every implemented page was opened; working
entry points, tool search, mobile navigation, Escape/focus behavior, table labels
and form dialogs were checked. Seventy-eight private rendered-markup checks passed across 320, 390, 463, 768,
1280 and 1920 CSS pixels: no document overflow or undersized buttons. They cover
ten owner pages, reseller/customer tool directories and a customer editor.
These are layout checks, not service integrations. Native phone checks also
covered ten form dialogs, list/no-result filters, a saved/reopened text file and
an invalid DNS record; the error remained in its dialog without losing input.
See [INTERFACE.md](INTERFACE.md) for the component contract.

The catalog now contains 253 workflows: 31 Available, 26 Partial and 196 Planned.
New catalog entries describe work; they do not introduce working services.

## Installation boundary carried forward

# VectorCP 0.4.0 development snapshot verification

The current source uses the VectorCP package, service and storage identifiers.
This changes the installation layout; the upgrade helper refuses installations
that do not have that layout. A verified migration from 0.3.x is not included.
Do not use the fresh installer on an existing hosting server.

All 56 tests passed locally on Python 3.13 in 47.014 seconds after the namespace
change and wordmark-route update. JavaScript and all four deployment shell
scripts passed syntax checks.
They cover authorization, tenant boundaries, HTTP, jobs, plans, backups and DNS.
The original logo was inspected in the actual local application's sign-in screen
and the generated public website. The new wordmark routes are included in the
HTTP asset and security-header checks. Source packaging includes the SVG assets.

Fresh AlmaLinux installation, renamed service units, certificate paths, customer
volume mounts, restart recovery and upgrades have not yet been accepted under
the 0.4.0 layout. Earlier live checks below prove the earlier layout only. Local
tests must not be presented as proof that the new Linux deployment works.
The existing integration server has not been migrated by this publication.

Read-only product research on 3 November 2026 inventoried the public customer
and administrator tools and representative account, mail, database, DNS, backup
and scheduled-job interfaces. Some demo actions are disabled or pages omitted;
research is not a behavioral test or a completeness certification. The original
222-workflow catalog is a target specification with explicit statuses.

The changelog preserves the dates and behavior of earlier versions. The release
process requires matching source, tags and checksums; this development snapshot
is not a stable release and does not claim signed updates or an independent audit.

## Earlier release evidence

The following evidence remains scoped to its original version and deployment.

# VectorCP 0.3.1 branding verification

The 0.3.1 change adopts the selected public name in the interface, documentation,
HTTP server identity and source packaging. Customer-hosting behavior and runtime
identifiers are retained. Earlier verification evidence below retains its original release scope.

Final local validation on Python 3.13: all 56 existing tests passed in 42.684 seconds.
The JavaScript syntax check and all four deployment-script syntax checks passed.
The actual application's anonymous owner sign-in page was inspected in a browser
under its VectorCP title. No credentials were created or changed in that check.
Backend comparison against 0.3.0 found no changes to hosting or authentication
behavior. Release reporting now imports the package version instead of using a
second hardcoded value; the first live check caught that duplicate setting.
The historical 0.3.0 archive retains its original SHA-256.

The first test invocation could not bind its local HTTP/Unix sockets under the
tool sandbox; after granting loopback access, the complete suite passed. No
application fix was required for that environment restriction.

The live upgrade completed with application and database recovery copies retained.
All 14 installed application files match the checked source. The running agent
reports version 0.3.1. Panel/health, WordPress demo and delegated reseller demo
endpoints returned HTTP 200 with TLS certificate verification enabled. The four
panel/proxy services are active and SELinux remains enforcing. An existing owner
browser session continued to open its workspace with the new VectorCP branding.

The source packager verifies all archive entries against the source, excludes
runtime data and private deployment files, and uses the VectorCP release prefix.
A public repository and project domain have not been launched as part of this
branding change. This release does not add to the 0.3.0 feature coverage.

# 0.3 verification

Verified on 2–3 November 2026. This is an open-source product milestone, not
complete product scope or production acceptance. The 0.2 evidence follows.

## Automated and deployment checks

56 tests passed locally on Python 3.13 (41.110 seconds) and on AlmaLinux 9's
Python 3.9 (59.900 seconds). Added coverage includes reseller/customer scoping,
cross-reseller rejection, owner hold/lock precedence, parent-session revocation,
immutable package reassignment, existing volume-size protection, non-oversold
reservations, inherited job feature checks, separate role entry paths, DNS
validation/injection rejection, CNAME conflicts and publication rollback.

Both check and apply paths of `deploy/upgrade.py` were exercised. It retained a
consistent SQLite backup and application copy before migration. The application
restarted successfully; Nginx and existing customer services were not restarted
by the upgrade. Customer website checks returned HTTP 200. Failure rollback of
the upgrade helper itself has not been fault-injected.

All 14 installed application files match SHA-256 hashes of this release's
sources. Python/JavaScript syntax and deployment shell checks passed.

## Live role and DNS acceptance

A retained reseller demo was created with a 2 GB, 6-site, 2-customer package. Its
customer has a 512 MB, one-site package and a separate actual customer volume.
Through public HTTPS requests, the reseller could manage its own customer and
could not read the original WordPress customer's files, database details or DNS,
or lock that unrelated customer. Its customer could not access hosting-plan
management or another customer's files. Attempts to create an administrator or
change an existing allocation's size were rejected.

The owner suspended the reseller demo website; the reseller could not reverse
that hold. The owner locked its customer; the reseller could not unlock it.
Those temporary holds were restored by the owner. Locking the reseller invalidated
both its current session and its customer's current session; it was then unlocked.
These are useful retained demo accounts, not hidden verification fixtures.

A private DNS zone and TXT record were created through the reseller's normal
permissions. The zone export contained the expected values. Real BIND answered
A queries over UDP and TCP and returned the test TXT value. Queries requiring
recursion were REFUSED, and AXFR failed as intended. Port 53 listens only on
127.0.0.1; the firewall still permits only SSH, HTTP and HTTPS. The matching TXT
ownership challenge was correctly reported absent at an independent public
resolver. This does not verify ownership of a real customer domain.

The reseller then requested a real HTTPS certificate through its delegated
hosting permissions. The job completed. The existing owner account, WordPress
demo and its credentials were preserved. SELinux is enforcing, and the final
system-service check found no failed units.

## Interface checks

Owner and reseller sign-in were exercised in the actual browser. The owner saw
all four sample packages; the reseller saw only its delegated customer. The
reseller package form exposed the customer-pool field when its package type
changed. The DNS view showed only that reseller's website and private records.
The package view measured 463 px for both viewport and document width, with its
table scrolling inside the panel rather than overflowing the whole page.
Screenshots are retained as separate deployment deliverables.

## Product and operational limits

The application is MIT-licensed and contains no provider-specific IP/domain
configuration in its application source. Contribution, architecture, security
and 69-area feature coverage documents are included. A public repository and
monitored vulnerability-reporting destination have not yet been established.

Plans are immutable templates with explicit assignment in 0.3; they do not yet
provide dynamic inherited edits. CPU/memory/task profiles remain fixed, with no
adjustable aggregate reseller cgroups or bandwidth allowance. Public DNS,
PowerDNS/DNSSEC/clustering, mail, nested resellers, reseller branding and the
other gaps in `FEATURES.md` remain further work. The private DNS preview does
not change public domain records. The deployment's existing domain already uses
Cloudflare and Zoho; its public records and email routing were left untouched.

No independent security audit, sustained capacity benchmark, clean-image install
matrix, ARM64 acceptance, crash/disk-exhaustion recovery drill or complete
reference-product workflow comparison is claimed.

---

# VectorCP 0.2 verification

Verified on 2 November 2026. This report describes the milestone actually built;
it does not establish complete product acceptance or production readiness.

## Automated checks

38 tests passed on the local Python 3.13 runtime (25.484 seconds) and the supplied
AlmaLinux VPS's Python 3.9 runtime (42.098 seconds). They cover authentication,
role/ownership and CSRF boundaries, traversal/symlink rejection, file revisions,
allowances, Nginx validation rollback, suspension, exports, audit scoping,
public HTTPS origin/cookie behavior, archive safety, backup chunk/deletion
ownership, job scoping and mutation locks. JavaScript syntax, Python compilation
and deployment shell syntax checks passed. The narrow-screen grid was corrected
and visually checked after the functional tests.

Tests use isolated temporary state. They do not open or alter the live control
state. The Linux-only hosting implementation was additionally exercised against
the actual installed services as described below.

## Real VPS workflow

- Preserved the existing owner credentials and original panel state through an
  additive schema migration. Public owner sign-in remains on the trusted IP URL.
- Provisioned a customer-specific capped ext4 volume, Linux identity, PHP-FPM
  service and private MariaDB instance through the running panel API.
- A PHP probe in a second customer returned its actual separate UID (988), could
  read its own file and could not see the first customer's files/database socket,
  another PHP socket, the panel database or `/etc/shadow`. FPM shell execution
  functions were unavailable. Its 512 MB allocation exposed a 510,873,600-byte
  filesystem after metadata overhead. The corrected isolation check passed.
- Initialized a fresh private database through the root-only task socket and
  bounded customer service, with no SSH shortcut for database initialization.
- Installed the current official WordPress release (7.1.4 at verification time),
  checked downloaded files against the official checksum list, and executed the
  installer under the customer's UID and namespace. A second fresh install
  passed after the service readiness fixes.
- Served the demo over trusted public HTTPS and signed into its WordPress
  administrator dashboard using the delivered credentials.
- Issued a trusted certificate for a customer hostname and converted an existing
  HTTP WordPress installation to HTTPS. Page content used the HTTPS URLs.
- Created local files/database backups. Changed a real website file and database
  title, restored the backup through the panel job, and verified both original
  file contents and database title returned. A file added after the snapshot was
  absent after restore. Repeated the check against the updated backup code.
- Downloaded all 35,308,778 bytes of a real backup through public authenticated
  chunk requests; SHA-256 matched the private server archive. The browser's
  download workflow also completed its final integrity check successfully.
- Direct backend and local Nginx/TLS streamed downloads matched the archive hash.
  Long single public transfers were truncated on this connection, so the UI now
  uses bounded retried chunks rather than depending on one long response.
- Verified trusted public panel TLS, secure cookies, authenticated access, exact
  origin rejection and logout after customer certificates were added. The panel
  is explicitly the default TLS server so clients without SNI receive its IP
  certificate, rather than a customer's certificate.

## Host state

The original AlmaLinux 9.8 host remains on kernel
5.14.0-687.61.1.el9_8.x86_64. SELinux remains enforcing, firewall rules retain
SSH/HTTP/HTTPS only, and control backends bind to loopback. The global SELinux
`httpd_can_network_connect_db` boolean remains off. Correct local socket labels
allow the private databases to operate without that proposed global permission.
The unused shared default PHP-FPM and MariaDB services are masked.

Customer PHP, database and task services have separate identities, namespaces,
capability restrictions and cgroup limits. The parent workload budget and each
customer slice were inspected. No custom SELinux domain for the Python panel
is claimed. Existing public administrator certificate renewal had already been
rehearsed inside its production systemd restrictions; renewal now includes
customer certificates as well. A staging dry run of all three current certificate lineages (panel IP, demo domain and verification domain) succeeded with the deployment hook.

The two disposable verification customers and their sites were removed from active
hosting after explicit user approval. Their volumes, configuration, unused test
certificate and a complete panel database snapshot are retained in the private
`/var/lib/vectorcp/install-backups/hosting-qa-20261102/` recovery archive.
The owner and working WordPress demo were excluded. Audit history remains.

## Limits and further work

No sustained load test, independent penetration/security review, clean-image
recovery test, deliberate disk exhaustion or power-loss restore test has been
performed. Ordinary exception rollback is implemented; interrupted jobs require
administrator inspection. Hosted IPv6, volume resizing, existing-site migration,
mail, hosted DNS, resellers/plans, shells/FTP, arbitrary application runtimes,
scheduled/off-server/incremental backups, migration, billing, WAF/scanning and
AI/MCP integrations remain further work. Local website recovery copies are not
whole-server disaster-recovery images. See README.md for all numerical limits.
