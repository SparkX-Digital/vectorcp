# VectorCP 0.3.1 branding verification

The 0.3.1 change adopts the selected public name in the interface, documentation,
HTTP server identity and source packaging. Customer-hosting behavior and runtime
identifiers are retained. Earlier verification evidence below remains labeled
with the name and release under which it was performed.

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

# VeyraPanel 0.3 verification

Verified on 2–3 November 2026. This is an open-source product milestone, not
complete BHPanel parity or production acceptance. The 0.2 evidence follows.

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

# VeyraPanel 0.2 verification

Verified on 2 November 2026. This report describes the milestone actually built;
it does not establish complete BHPanel feature parity or production acceptance.

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
`/var/lib/veyrapanel/install-backups/hosting-qa-20261102/` recovery archive.
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
