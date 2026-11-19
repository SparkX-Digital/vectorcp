# Architecture

## Product and roles

VectorCP is a general-purpose open-source server product. A particular VPS,
provider, domain or billing account is a deployment, not a product dependency.
The default license is MIT. There is no license server, activation fee or paid
feature gate in the VectorCP application.

- **Owner / administrator:** host operations, packages, resellers and customers.
- **Reseller:** its own customer packages, reservations and delegated customers.
- **Customer:** its own websites, files, applications, databases and backups.

Separate entry paths are `/admin`, `/reseller` and `/customer`; the same frontend
serves them. Authorization is always in the agent and does not depend on a URL
or a hidden navigation item. Collaborators and nested reseller tiers are planned.

## Request path

A TLS reverse proxy serves an unprivileged Python HTTP process. It validates
Host, Origin, body bounds and operation names. Its HttpOnly session cookie is
sent to a root agent through a restricted local Unix socket. The agent verifies
the hashed session, active account and reseller, CSRF for mutations, role and
object ownership. The web process cannot choose the request's effective role.

`core.py` owns authentication, bounded files, sites, audit and job submission.
`distribution.py` owns reseller delegation and hosting packages. `hosting.py`
integrates isolated PHP, MariaDB, WordPress, certificates and local recovery.
`dns.py` owns validated records, serials, draft/active BIND publication and export.
`dns_profile.py` provides the owner-only private/public service transition; browser
requests cannot choose interfaces, probe destinations or nameserver configuration.
`hosting_task.py` exposes fixed customer tasks through root-only Unix sockets;
it accepts no arbitrary executable or shell command.

SQLite is private to the agent. Migrations are additive. Before upgrading, make
an online SQLite backup and copy the installed application. Never copy only a
live WAL-mode database file and assume it is a consistent backup.

## Resources and plans

A reseller reserves a customer count, aggregate website allowance and storage
pool. Every delegated customer consumes its full assigned allowance even while
locked. Top-level customer allocations and reseller pools count against the
host's 16 GiB reservation ceiling; children are not counted a second time.

Package templates are immutable in 0.3. New assignments are explicit. Retiring a
package stops new assignments while preserving current accounts. Reassignment
must fit actual usage and existing services. Physical volumes cannot be resized
through a package change. This differs from the full target's dynamic plan
inheritance; see `FEATURES.md`.

Storage uses a separate capped ext4 volume per customer. Actual application
writes meet a filesystem boundary. These limits cover that customer's site and
private database data. CPU/memory/task limits currently use fixed install
profiles; adjustable reseller aggregate cgroups, inode accounting and bandwidth
limits are not yet implemented.

## Services and changes

Use maintained Linux engines for HTTP, PHP, databases, DNS and future mail.
Generate configuration from typed values, validate before reload, retain the
previous configuration on failure, and confirm observed service state. Never
turn a dashboard button into an unrestricted root command dispatcher.

The default DNS service is a loopback private preview. Unreleased 0.4.3 adds an
optional authoritative public profile with explicit owner-selected interfaces,
draft exclusion, activation-time ownership checks, controlled deactivation and
UDP/TCP confirmation. Recursion and transfers remain disabled. See [PUBLIC_DNS.md](PUBLIC_DNS.md)
for delegation, independent-server and crash-recovery limitations. DNSSEC,
clustering and external synchronization remain planned.

A service is available only after its backend is installed and exercised.
Unimplemented features belong in the roadmap, not as pretend success actions.
