# VectorCP capability catalog

Updated 4 November 2026. This catalog defines the intended scope for a free,
self-hosted hosting panel. It consolidates customer tools, reseller operations
and server administration into original product requirements. It is not a
claim that every tool is implemented.

**Available** means an implemented development capability, subject to the limits
in [FEATURES.md](FEATURES.md). **Partial** means a narrower implementation exists.
**Planned** means no complete backend/workflow is delivered. None of these labels
asserts an independent security audit or production acceptance. The 0.4.x
installation-layout validation remains separate from earlier service evidence.

Statuses describe the current development source. The **Unreleased** account,
security and file workflows are not part of the immutable 0.4.2 download; see
[CHANGELOG.md](CHANGELOG.md), [ACCOUNT_SECURITY.md](ACCOUNT_SECURITY.md) and
[FILE_MANAGER.md](FILE_MANAGER.md) for implementation limits and evidence.

Stable IDs identify work items and acceptance evidence. A row is a user workflow,
not necessarily a screen or a single development task. Read [PRODUCT.md](PRODUCT.md)
for the installation contract and [ROADMAP.md](ROADMAP.md) for delivery order.

## Install and maintain

**Roles:** Owner.

**Completion check:** Every supported profile installs on a clean image, refuses conflicting services and has a tested recovery route.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0101 | Preflight and fresh-host installation | Available |
| VCP-0102 | Private first-time owner setup | Available |
| VCP-0103 | Core, Complete and DNS-node profiles | Planned |
| VCP-0104 | Installation progress and safe retry | Planned |
| VCP-0105 | Trusted panel HTTPS and renewal | Partial |
| VCP-0106 | Offline operation without activation | Available |
| VCP-0107 | Architecture and platform checks | Partial |
| VCP-0108 | Versioned application upgrades and startup rollback | Available |
| VCP-0109 | Signed release channels and scheduled updates | Planned |
| VCP-0110 | OS updates and maintenance reboot windows | Planned |
| VCP-0111 | Independent clean-server recovery | Planned |
| VCP-0112 | Uninstall planning, data preservation and service cleanup | Planned |

## Identity and access

**Roles:** All roles.

**Completion check:** Attempt each operation with permitted, unrelated, expired and revoked identities; no cross-account state is exposed.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0201 | Password sign-in and session expiry | Available |
| VCP-0202 | Separate owner, reseller and customer entry points | Available |
| VCP-0203 | CSRF, host/origin validation and login throttling | Available |
| VCP-0204 | Active-session inventory and remote revocation | Available |
| VCP-0205 | Two-factor authentication and recovery codes | Available |
| VCP-0206 | Passkey enrollment and role policy | Planned |
| VCP-0207 | Account recovery and security notifications | Planned |
| VCP-0208 | Password strength policy and forced rotation | Available |
| VCP-0209 | Collaborator identities and granular permissions | Planned |
| VCP-0210 | External identity-provider connections | Planned |

## Account lifecycle

**Roles:** Owner / Reseller.

**Completion check:** Creation, changes and termination enforce parent policy, preserve recovery evidence and report partial failures.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0301 | Create customer and reseller accounts | Available |
| VCP-0302 | Search, filter and inspect accounts | Available |
| VCP-0303 | Account access locks and child-session revocation | Available |
| VCP-0304 | Independent website suspension | Available |
| VCP-0305 | Modify account details and contact information | Available |
| VCP-0306 | Change assigned hosting plan | Partial |
| VCP-0307 | Terminate an account with recovery and cleanup | Planned |
| VCP-0308 | Bulk account changes and suspensions | Partial |
| VCP-0309 | Transfer account ownership between resellers | Planned |
| VCP-0310 | Move account data between storage locations | Planned |
| VCP-0311 | Dedicated/shared address assignment | Planned |
| VCP-0312 | Restricted shell access policy | Planned |
| VCP-0313 | Account demo mode | Planned |
| VCP-0314 | Audited owner/delegate sign-on to a customer workspace | Planned |

Selected-account access and plan changes are implemented. Bulk website suspension
is still unfinished, so VCP-0308 remains Partial.

## Plans and reseller business

**Roles:** Owner / Reseller.

**Completion check:** Children cannot exceed reserved parent capacity, bypass a disabled feature or override an owner restriction.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0401 | Customer and reseller packages | Available |
| VCP-0402 | Immutable assignment, retirement and explicit reassignment | Available |
| VCP-0403 | Customer, website and storage reservations | Available |
| VCP-0404 | Inherited feature permissions | Available |
| VCP-0405 | Dynamic package updates to existing accounts | Planned |
| VCP-0406 | Configurable CPU, RAM, process and I/O limits | Partial |
| VCP-0407 | Disk-byte and inode enforcement | Partial |
| VCP-0408 | Monthly transfer accounting and overage policy | Planned |
| VCP-0409 | Overselling policy and capacity reports | Planned |
| VCP-0410 | Reseller nameservers and brand identity | Planned |
| VCP-0411 | Reseller shared IP and dedicated address pools | Planned |
| VCP-0412 | Nested reseller tiers | Planned |
| VCP-0413 | Reseller customer exports and remote backups | Planned |
| VCP-0414 | Reseller usage reports and customer communications | Planned |

## Websites and domains

**Roles:** Customer / Delegated management.

**Completion check:** Validate ownership and routing; failed configuration reloads preserve the working site and unrelated virtual hosts.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0501 | Static websites and isolated PHP hosting | Available |
| VCP-0502 | Owned domains and website document roots | Partial |
| VCP-0503 | Subdomains, domain aliases and parked domains | Planned |
| VCP-0504 | Permanent/temporary redirects and HTTPS preference | Partial |
| VCP-0505 | Default, suspended and error pages | Partial |
| VCP-0506 | IPv4 and IPv6 serving and address changes | Partial |
| VCP-0507 | Alternative web-server stacks and safe switching | Planned |
| VCP-0508 | HTTP/2 and HTTP/3 negotiation | Planned |
| VCP-0509 | Per-site page cache and purge | Planned |
| VCP-0510 | Compression and content optimization | Planned |
| VCP-0511 | Directory indexes and MIME/handler configuration | Planned |
| VCP-0512 | Password-protected directories | Planned |
| VCP-0513 | Hotlink and credential-sharing controls | Planned |
| VCP-0514 | Proxy-aware visitor address handling | Planned |
| VCP-0515 | Optional visual website builder and exportable site output | Planned |

## Certificates

**Roles:** Customer / Owner.

**Completion check:** Verify real certificate chains, private-key access, validation failures and renewal without interrupting unrelated sites.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0601 | Domain ACME issue, DNS preflight and renewal | Available |
| VCP-0602 | Panel IP certificate profile | Available |
| VCP-0603 | Force HTTPS and update installed website URLs | Partial |
| VCP-0604 | Certificates for aliases, mail and webmail | Planned |
| VCP-0605 | Key and certificate inventory | Planned |
| VCP-0606 | Certificate request generation and manual import | Planned |
| VCP-0607 | Expiry dashboard, renewal logs and alerts | Planned |
| VCP-0608 | Service certificate replacement with rollback | Planned |

## Files and transfer

**Roles:** Customer.

**Completion check:** Test traversal, symlinks, archive escapes, quota exhaustion, permissions and recovery on actual customer storage.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0701 | Browse files and create folders | Available |
| VCP-0702 | Bounded atomic UTF-8 text editing | Available |
| VCP-0703 | Upload and download individual files | Available |
| VCP-0704 | Copy, move, rename and batch selection | Available |
| VCP-0705 | Trash, undo and permanent removal | Available |
| VCP-0706 | Archive create/extract with safe paths | Available |
| VCP-0707 | File permission and ownership controls | Available |
| VCP-0708 | Hidden-file controls and search | Available |
| VCP-0709 | Image resize, thumbnails and conversion | Planned |
| VCP-0710 | Disk/inode usage drill-down | Planned |
| VCP-0711 | FTP/FTPS accounts and client configuration | Planned |
| VCP-0712 | Restricted SFTP and SSH keys | Planned |
| VCP-0713 | WebDAV storage access | Planned |
| VCP-0714 | File and directory recovery from backups | Planned |

## Databases

**Roles:** Customer / Owner.

**Completion check:** Database identities and grants remain tenant scoped; failed imports, repairs and upgrades have a usable recovery copy.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0801 | Private MariaDB instances and per-site databases | Available |
| VCP-0802 | Database creation wizard | Partial |
| VCP-0803 | Database users and granular grants | Planned |
| VCP-0804 | Rename, remove, check and repair databases | Planned |
| VCP-0805 | Browser database administration and scoped sign-on | Planned |
| VCP-0806 | Database import/export and size reports | Partial |
| VCP-0807 | Remote access host allowlists and TLS | Planned |
| VCP-0808 | PostgreSQL databases, roles and administration | Planned |
| VCP-0809 | MongoDB databases and account controls | Planned |
| VCP-0810 | Private Redis and optional object caches | Planned |
| VCP-0811 | Combined database allowances across engines | Planned |
| VCP-0812 | Server database profiles and configuration | Planned |
| VCP-0813 | Database process inspection and safe cancellation | Planned |
| VCP-0814 | Database engine upgrades and restoration | Planned |
| VCP-0815 | Database ownership maps and orphan reconciliation | Planned |

## Email and collaboration

**Roles:** Customer.

**Completion check:** Exercise external SMTP/IMAP, quotas, routing, filtering, TLS and recovery; no open relay or cross-mailbox access.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-0901 | Mailboxes, aliases and per-mailbox quotas | Planned |
| VCP-0902 | Webmail and client auto-configuration | Planned |
| VCP-0903 | Forwarders and domain-level forwarding | Planned |
| VCP-0904 | Local, remote and backup mail routing | Planned |
| VCP-0905 | Automatic replies with date windows | Planned |
| VCP-0906 | Default/catch-all address handling | Planned |
| VCP-0907 | Mailbox and domain filtering rules | Planned |
| VCP-0908 | Bulk address and forwarder import | Planned |
| VCP-0909 | Spam score controls, allowlists and denylists | Planned |
| VCP-0910 | Virus scanning and message quarantine | Planned |
| VCP-0911 | Challenge-based sender verification | Planned |
| VCP-0912 | Mailing lists and subscription controls | Planned |
| VCP-0913 | Delivery tracking, logs and failure diagnosis | Planned |
| VCP-0914 | SPF, DKIM, DMARC and PTR diagnostics | Planned |
| VCP-0915 | Mail encryption key management | Planned |
| VCP-0916 | Mailbox disk usage and safe pruning | Planned |
| VCP-0917 | Sending limits shared by SMTP and website scripts | Planned |
| VCP-0918 | Calendars, contacts and sharing permissions | Planned |
| VCP-0919 | External SMTP relay with verified TLS | Planned |
| VCP-0920 | Mail queue inspection, retry, freeze and bounded removal | Planned |
| VCP-0921 | Greylisting and trusted sender exemptions | Planned |
| VCP-0922 | Inbound domain and country policies | Planned |
| VCP-0923 | Server relayer, sent-mail and delivery summary reports | Planned |
| VCP-0924 | Mailbox format migration and permission repair | Planned |

## DNS

**Roles:** Customer / Owner.

**Completion check:** Validate public answers over UDP/TCP, delegation, serials and tenant ownership; private previews must be clearly identified.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1001 | Record validation for A, AAAA, CNAME, MX, TXT, NS, CAA and SRV | Available |
| VCP-1002 | Private authoritative preview and zone export | Available |
| VCP-1003 | Public TXT ownership verification | Available |
| VCP-1004 | Public authoritative DNS hosting | Planned |
| VCP-1005 | Automatic site zones and mail records | Planned |
| VCP-1006 | Zone templates and TTL management | Planned |
| VCP-1007 | DNSSEC signing, DS guidance and safe key removal | Planned |
| VCP-1008 | Dynamic DNS clients and scoped tokens | Planned |
| VCP-1009 | DNS diagnostics and nameserver reports | Planned |
| VCP-1010 | DNS-only nodes and cluster replication | Planned |
| VCP-1011 | External DNS record synchronization | Planned |
| VCP-1012 | Proxy, TLS mode and external cache controls | Planned |
| VCP-1013 | Zone deletion, cleanup, rebuild and consistency repair | Planned |

## PHP, apps and development

**Roles:** Customer.

**Completion check:** Each runtime executes as its account with resource limits, bounded logs, isolated secrets and recoverable deployments.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1101 | Isolated PHP 8.3 FPM services | Available |
| VCP-1102 | Per-domain PHP version and worker selection | Planned |
| VCP-1103 | Basic and advanced PHP settings editor | Planned |
| VCP-1104 | PHP extension and package selection | Planned |
| VCP-1105 | PHP compatibility-build maintenance policy | Planned |
| VCP-1106 | Language module installation | Planned |
| VCP-1107 | Cron schedules, presets and output delivery | Planned |
| VCP-1108 | Git repositories, branches and controlled deployment | Planned |
| VCP-1109 | Customer terminal with restricted filesystem | Planned |
| VCP-1110 | Node.js and Python lifecycle controls | Planned |
| VCP-1111 | Container application catalog and persistence | Planned |
| VCP-1112 | Optional third-party app installers | Planned |
| VCP-1113 | Application logs, health checks and restart | Planned |
| VCP-1114 | Panel maintenance schedules and task configuration | Planned |

## WordPress

**Roles:** Customer.

**Completion check:** Use official verified artifacts, account-owned execution and recovery checks before destructive maintenance.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1201 | Verified installation on a fresh website | Available |
| VCP-1202 | Switch installed site from HTTP to HTTPS | Available |
| VCP-1203 | Inventory and one-time administrator sign-on | Planned |
| VCP-1204 | Core, plugin and theme updates | Planned |
| VCP-1205 | Restore points and update rollback | Planned |
| VCP-1206 | Clone, staging and controlled promotion | Planned |
| VCP-1207 | Security checks and maintenance mode | Planned |
| VCP-1208 | Multisite, search/replace and migration | Planned |

## Backups and recovery

**Roles:** All roles.

**Completion check:** Prove recovery of selected components on an independent server, including full disks, interruptions and lost local catalogs.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1301 | Bounded local website files/SQL backups | Available |
| VCP-1302 | Scoped restore with previous-copy rollback | Available |
| VCP-1303 | Chunked download and SHA-256 verification | Available |
| VCP-1304 | Local retention limits and deletion | Available |
| VCP-1305 | Customer schedules and storage accounting | Planned |
| VCP-1306 | Server schedules and account selection | Planned |
| VCP-1307 | Daily, weekly and monthly retention policies | Planned |
| VCP-1308 | Free-space thresholds and staging paths | Planned |
| VCP-1309 | Back up suspended accounts and system configuration | Planned |
| VCP-1310 | Reseller schedules and independent destinations | Planned |
| VCP-1311 | SFTP, FTPS, S3 and optional drive destinations | Planned |
| VCP-1312 | Encrypted incremental repositories | Planned |
| VCP-1313 | Compression formats and integrity checks | Partial |
| VCP-1314 | Restore selected folder, database or mailbox | Planned |
| VCP-1315 | Restore DNS, certificates, cron and app configuration | Planned |
| VCP-1316 | Whole-account export/import and disaster recovery | Planned |

## Metrics, logs and notifications

**Roles:** Customer / Owner.

**Completion check:** Measure actual server data, enforce visibility and retention rules, and redact credentials in every diagnostic path.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1401 | Host resource summary and observed service state | Partial |
| VCP-1402 | Scoped background jobs and activity history | Available |
| VCP-1403 | Website visitor and request reports | Planned |
| VCP-1404 | Access/error log viewers and downloads | Planned |
| VCP-1405 | Bandwidth accounting and period reports | Planned |
| VCP-1406 | Website uptime and quality monitoring | Planned |
| VCP-1407 | Historical CPU, memory, disk and process metrics | Planned |
| VCP-1408 | Task-queue monitoring, retry and safe cancellation | Partial |
| VCP-1409 | Threshold alerts and contact routing | Planned |
| VCP-1410 | Notification inbox and delivery preferences | Planned |
| VCP-1411 | Log rotation and retention policies | Planned |
| VCP-1412 | Traffic report engines, account selection and processing schedules | Planned |

## Security operations

**Roles:** Owner / Delegated policies.

**Completion check:** Security changes preserve operator access, are attributable and tested against benign and adversarial fixtures.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1501 | Private agent socket and backend authorization | Available |
| VCP-1502 | Customer identities, volumes and namespaces | Partial |
| VCP-1503 | SELinux-enforcing service operation | Partial |
| VCP-1504 | Prevent PHP execution in application uploads | Partial |
| VCP-1505 | Firewall address, network, port and country rules | Planned |
| VCP-1506 | Automatic abuse blocks and safe expiry | Planned |
| VCP-1507 | Web firewall policies, rule exclusions and events | Planned |
| VCP-1508 | Malware scanning, quarantine and restoration | Planned |
| VCP-1509 | Rootkit, hardening and isolation reports | Planned |
| VCP-1510 | SSH authorization, privileged groups and compiler policy | Planned |
| VCP-1511 | Outbound SMTP and process-abuse restrictions | Planned |
| VCP-1512 | Threat-feed updates and protection profiles | Planned |
| VCP-1513 | Owner terminal with elevated-action MFA | Planned |
| VCP-1514 | Security audit export and incident evidence | Planned |
| VCP-1515 | OS administrator credential rotation with access recovery | Planned |
| VCP-1516 | User-directory exposure and network diagnostic policies | Planned |

## Server and network operations

**Roles:** Owner.

**Completion check:** Validate configuration before applying, health-check after changes and provide a tested maintenance/recovery path.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1601 | Service inventory and status | Partial |
| VCP-1602 | Service start, stop, restart and monitoring policy | Planned |
| VCP-1603 | Web, mail, DNS, FTP and database configuration | Planned |
| VCP-1604 | Software components and supported package sources | Planned |
| VCP-1605 | Hostname, resolver and server clock management | Planned |
| VCP-1606 | IP address pools, IPv6 ranges and reservations | Planned |
| VCP-1607 | Shared/dedicated address migration | Planned |
| VCP-1608 | Process inspection and termination | Planned |
| VCP-1609 | Storage usage and quota diagnostics | Partial |
| VCP-1610 | Contact manager and system-mail routing | Planned |
| VCP-1611 | Configuration clustering and linked nodes | Planned |
| VCP-1612 | Graceful/forced reboot with service recovery | Planned |
| VCP-1613 | Package database diagnostics and supported repair | Planned |
| VCP-1614 | Server configuration presets and validated advanced settings | Planned |

## Transfers and migration

**Roles:** Owner / Authorized reseller.

**Completion check:** Read the source without changing it; preview conflicts and restore tested fixtures with resumable, auditable jobs.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1701 | Import documented account archive formats | Planned |
| VCP-1702 | Remote SSH/API account transfer | Planned |
| VCP-1703 | Bulk transfer with inventory and mapping | Planned |
| VCP-1704 | Reseller, package and ownership mapping | Planned |
| VCP-1705 | Convert an addon domain into its own account | Planned |
| VCP-1706 | Review transfer logs, conflicts and retries | Planned |
| VCP-1707 | Verify files, databases, mail and DNS after import | Planned |
| VCP-1708 | Export a portable VectorCP account | Planned |

## Preferences and extensibility

**Roles:** All roles / Owner policies.

**Completion check:** Preferences respect ownership; integrations use scoped revocable access and never expose unrestricted privileged execution.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1801 | Product name, role labels and consistent identity | Available |
| VCP-1802 | Account locale and language catalogs | Planned |
| VCP-1803 | Theme, navigation and favorite tools | Planned |
| VCP-1804 | Contact and account preferences | Planned |
| VCP-1805 | Reseller logo, colours and customer-facing templates | Planned |
| VCP-1806 | Scoped API tokens, expiry and network restrictions | Planned |
| VCP-1807 | API schema, developer documentation and hooks | Planned |
| VCP-1808 | Billing provisioning, suspension and sign-on connectors | Planned |
| VCP-1809 | Optional plugin registration and permissions | Planned |
| VCP-1810 | Authorized MCP tools and provider connections | Planned |
| VCP-1811 | AI settings, budgets and explicit change approval | Planned |
| VCP-1812 | Conflict-aware action history and eligible undo | Planned |
| VCP-1813 | Locale authoring, copy, import and export | Planned |
| VCP-1814 | Optional social publishing integration with scoped consent | Planned |
| VCP-1815 | Redacted support bundles and diagnostic reports | Planned |
| VCP-1816 | Optional integration catalog, license and update inventory | Planned |

## Hosting business and billing

**Roles:** Owner / Authorized reseller.

**Completion check:** Provisioning is idempotent and respects hosting permissions;
payment webhooks are authenticated, retried safely and reconciled with invoices.
Panel installation and use never require a paid license or activation service.

| ID | Capability | Status |
| --- | --- | --- |
| VCP-1901 | Hosting product catalog and customer checkout | Planned |
| VCP-1902 | Customer portal and service ownership | Planned |
| VCP-1903 | Invoices, credits and auditable adjustments | Planned |
| VCP-1904 | Recurring subscriptions, renewals and proration | Planned |
| VCP-1905 | Optional payment gateways and authenticated webhooks | Planned |
| VCP-1906 | Tax configuration, currencies and invoice numbering | Planned |
| VCP-1907 | Provision, suspend, unsuspend and cancel paid services | Planned |
| VCP-1908 | Billing roles, reseller balances and spending permissions | Planned |
| VCP-1909 | Revenue reports, reconciliation and exports | Planned |
| VCP-1910 | Billing notices, delivery logs and customer preferences | Planned |

## Coverage limits

The public demonstrations used for research omit pages and disable operations.
This list covers the visible tool families and the additional planned service
requirements; it cannot establish every hidden setting, API contract or edge
case. New discoveries extend the catalog through reviewed work items. Optional builders,
social publishing and commercial services require their own original integration;
a link or a similar-looking screen does not establish equivalent behavior.

Do not mark an entire family complete because one row works. Each capability
needs authorization, failure, quota, concurrency, upgrade and recovery checks.
Optional third-party integrations retain their own licenses and requirements.
