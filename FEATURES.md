# Feature coverage and roadmap

VectorCP is a free, MIT-licensed hosting control panel for personal websites
and hosting businesses. This is an implementation tracker, not a statement
that the complete product is available. Each area needs a working backend,
authorization checks, recovery behavior and reproducible acceptance evidence.

The [product specification](PRODUCT.md) defines the roles, installation contract
and release gates. The [capability catalog](CAPABILITIES.md) breaks the full
scope into customer, reseller and administrator workflows. Updated 5 November
2026 with Unreleased account/security, file and bulk website workflows. Demo
screens reveal controls, but cannot establish undocumented behavior or prove
that an action works on a real server.

Current target platform: dedicated AlmaLinux 9, x86-64 tested. Other distributions,
ARM64, a clean-machine full recovery and production capacity remain unverified.
The supplied VPS is the integration deployment, not the only supported provider.

## Milestones

1. Identity, authorization, safe jobs and isolated web hosting — partly shipped.
2. Owner/reseller/customer product, plans, DNS and mail — in progress.
3. File transfers, cron/Git, runtimes, WordPress operations, remote backups.
4. Web-stack choices, database engines, security tools and migration.
5. Billing integrations, API/MCP, DNS cluster, signed updates and parity audit.

Every target needs its real backend, permission/failure checks and Linux acceptance
evidence. Features can move between milestones when dependencies require it.

## Coverage

| Area | Current status | Target behavior | Acceptance target |
| --- | --- | --- | --- |
| Installation | Partial: fresh native installation and application upgrade/startup rollback verified on AlmaLinux 9 x86-64. Selectable profiles and alternate architectures pending. | Fresh AlmaLinux 9; x86-64 and ARM64; Core, Complete and DNS-only profiles; resumable setup | Install on clean images; interruption and retry; refuse incompatible or conflicting hosts |
| Initial access | Partial: one-time setup and role entry paths; further onboarding remains. | One-time administrator setup; separated administrator/reseller and customer entry points | Setup cannot be claimed without its token; token expires after use; correct role routing |
| Authentication | Partial: authenticator/recovery codes, session management, password policy/rotation, CSRF and throttling. Email account recovery and passkeys pending. | Password hashing, rate limits, session controls, two-factor authentication and recovery | Session fixation, cross-site request forgery, brute-force and recovery tests |
| Hierarchy | Partial: owner → reseller → customer. Collaborators/nested tiers pending. | Administrator, reseller, customer and collaborator scopes | Cross-account and cross-reseller requests refused in the backend |
| Branding | Partial: original shared VectorCP identity. Reseller branding pending. | Original VectorCP interface plus reseller identity settings | Consistent branding across login, navigation, emails and reseller views |
| Accounts | Partial: creation, contact editing, search/details, password resets and atomic selected-account access/plan changes and per-domain bulk website suspension/activation. Termination and migration pending. | Creation, plan changes, suspension, restoration and termination | Idempotent jobs; ownership checks; protected system usernames; explicit destructive workflows |
| Plans | Partial: immutable packages and explicit assignment. Dynamic inherited updates pending. | Resource allowances and feature switches, inherited by existing accounts | Changing a plan updates actual enforcement and creation limits |
| Reseller pools | Partial: reserved customer/site/storage allowances. Traffic and aggregate adjustable cgroups pending. | Shared disk, traffic, account, CPU, memory and process limits; overselling policies | Children cannot escape parent limits; accurate pool accounting and recovery from full pools |
| Disk quotas | Partial: capped ext4 volumes. Inode ceilings/XFS integration pending. | Byte and inode ceilings on XFS and ext4 | Actual writes fail at limits; enforcement survives reboot |
| Process limits | Partial: fixed customer PHP/DB/task profiles. Adjustable full-workload policies pending. | CPU, memory, process counts and disk I/O across PHP, cron, apps and shells | Measured load tests; no unlimited alternate execution path |
| Usage and bandwidth | Planned; not implemented. | Usage reporting, monthly transfer accounting and over-limit behavior | Reset boundaries and restoration after plan upgrade; certificate renewal remains possible |
| Web stacks | Planned; not implemented. | Nginx with Apache, and OpenLiteSpeed; preview and switch with rollback | Working sites checked before and after switching; failed switch restores prior stack |
| Protocols | Planned; not implemented. | HTTPS, HTTP/2, HTTP/3 and automatic required network configuration | External protocol negotiation tests, including UDP/QUIC |
| Domains | Partial: owned sites and suspension. Aliases/redirects/dedicated IPs pending. | Sites, aliases, subdomains, redirects, suspension and dedicated IP selection | Ownership validation; no conflicting names; expected virtual-host routing |
| PHP | Partial: isolated PHP 8.3. Version/extension/settings management pending. | Per-site versions, extensions, settings and per-account workers | Isolation between pools; setting validation; correct version served by each site |
| Older PHP versions | Planned; not implemented. | Optional compatibility runtimes with a documented security-maintenance policy | Explicit supported-build policy and a demonstrable maintenance source before advertising support |
| Page cache | Planned; not implemented. | Site-level enablement and purge; bypass of private and commerce pages | No personalized response leakage; cache invalidation tests |
| Object caches | Planned; not implemented. | Account-specific Redis and Memcached | One customer cannot read another customer's cache |
| Certificates | Partial: IP/customer HTTP-01 TLS and renewal. Aliases/mail certificates pending. | ACME issue and renewal; aliases; forced HTTPS; mail and webmail TLS | Validation failure recovery; real certificate verification and renewal rehearsal |
| Files | Partial: text editing, binary transfers, recursive copy/batches, hidden files, permissions, recoverable trash and bounded ZIP archives. Image editing and FTP/SFTP pending. | File browsing, edits, permissions, transfers, archives and trash | Traversal, symlink, archive-escape, ownership and quota tests |
| FTP and SSH | Planned; not implemented. | Account access, keys, plan restrictions and jailed customer shells | No access to other homes or host secrets; changes preserve administrator access |
| Terminals | Planned; not implemented. | Customer jail; administrator sudo workflow with two-factor gate and timeout | Server-side role checks; session teardown; escape testing |
| Scheduled tasks | Planned; not implemented. | Account-owned cron entries within plan limits | Environment and resource limits enforced; invalid expressions refused |
| Git deployment | Planned; not implemented. | Repository-backed deployment and deployment hooks | Secret handling; branch validation; deployment failure does not corrupt the live site |
| WordPress | Partial: verified fresh install and HTTP→HTTPS. Updates/sign-in management pending. | Installation, updates, sign-in and management workflows | Fresh-install and upgrade tests; isolated execution; controlled credential handling |
| Optional installers | Planned; not implemented. | Softaculous integration | Licensing and supported-version validation; no assumption that a third-party paid product is included |
| Runtime apps | Planned; not implemented. | Node.js and Python apps from customer folders | Account-owned services, lifecycle controls, logs and enforced limits |
| Container apps | Planned; not implemented. | n8n, Ghost, Gitea, Vaultwarden, Grafana, Uptime Kuma and Ollama | Reviewed image sources; persistent data; limits; networking; backup and upgrade recovery |
| MariaDB | Partial: private instances and site databases. User management/browser administration pending. | Databases, users, access controls, dump/restore and browser administration | Cross-account database access denied; connection and query constraints exercised |
| PostgreSQL | Planned; not implemented. | Per-account databases and users with administration sign-on | Role isolation; ownership and recovery tests |
| MongoDB | Planned; not implemented. | Per-account database controls | Authentication and tenant boundaries; dump/restore tests |
| Shared DB allowance | Planned; not implemented. | A plan's combined database count across engines | Cannot multiply the allowance by choosing different engines |
| Mail service | Planned; not implemented. | Postfix, Dovecot, mailbox and domain management | External SMTP/IMAP tests; routing and account ownership |
| Mail filtering | Planned; not implemented. | Rspamd, DKIM and optional ClamAV | Spam/virus test fixtures; clean mail still delivered |
| Mail applications | Planned; not implemented. | Roundcube and customer panel sign-on | TLS and scoped sign-on; no open relay |
| Mail rules | Planned; not implemented. | Forwarding, automatic replies and filtering | Loop prevention, permission checks and mailbox-specific behavior |
| Mail limits | Planned; not implemented. | Recipient-based sending limits across authenticated SMTP and website mail | Both submission paths share the allowance; correct multi-recipient accounting |
| Deliverability | Planned; not implemented. | PTR checks, public mail-DNS checks, port checks and queue controls | Real external delivery tests; useful diagnosis of provider restrictions |
| SMTP relay | Planned; not implemented. | Provider presets and custom TLS relay, validated before applying | Failed credentials do not replace working configuration; narrow firewall changes |
| Authoritative DNS | Partial: private BIND preview/editor/export. Public PowerDNS integration pending. | PowerDNS, automatic zones, editable records and serial management | Correct answers over UDP and TCP; authorization and conflicting-record checks |
| DNSSEC | Planned; not implemented. | Signing and DS guidance; controlled removal of signing keys | Validate a real chain of trust; safe sequencing when disabling |
| DNS clustering | Planned; not implemented. | DNS-only node, hosting-node membership, replication and reconciliation | Multi-node propagation; outage and ownership-transfer tests; removal propagates |
| External DNS | Planned; not implemented. | Cloudflare tokens, domain links, record synchronization, proxy and cache controls | Least-privilege token handling; reconciliation and failure recovery |
| Visitor addresses | Planned; not implemented. | Trusted Cloudflare address handling | Spoofed forwarding headers cannot forge visitor identity |
| Firewall | Planned; not implemented. | Address, network, ASN, country and port controls; threat feeds | Required access preserved; trusted addresses not accidentally blocked |
| Login protection | Planned; not implemented. | Repeated failure detection and temporary/permanent blocking | Real login failures produce expected blocks and safe expiry |
| Attack profiles | Planned; not implemented. | DDoS presets and per-account outbound SMTP restrictions | Measured behavior; legitimate traffic and relay exceptions remain possible |
| Web firewall | Planned; not implemented. | ModSecurity, detection/blocking modes, scoped rule exclusions and activity | Reproduce attacks and false positives without disabling unrelated protection |
| Malware watch | Planned; not implemented. | File inspection, confidence-based decisions, quarantine, restore and content exceptions | Benign/adversarial fixtures; no unsupported detection-quality claim |
| Upload restrictions | Partial: Nginx denies PHP in WordPress upload paths. Wider adversarial tests pending. | Prevent PHP execution in WordPress upload directories | Direct and indirect execution attempts refused |
| Security scans | Planned; not implemented. | Isolation checks, rootkit scanning, hardening and scheduled reporting | Findings distinguish reports from automatic changes; bounded safe fixes rechecked |
| SELinux | Partial: verified enforcing on current host. Broad clean-install coverage pending. | Operation with enforcing policies | Fresh install, updates, apps and restores work with enforcement enabled |
| Server backups | Planned; not implemented. | Jobs, schedules, selected components, retention and destinations | Actual recovery proves files, databases and mail are usable |
| Customer backups | Partial: bounded local files/SQL backup/restore/download. Schedules/remote destinations pending. | Account-owned schedules, storage accounting, download and restore | Quota headroom maintained; no recursive inclusion of prior backups |
| Reseller backups | Planned; not implemented. | Customer selection, reseller storage and non-overlapping windows | Ownership and pool constraints; do not interfere with server jobs |
| Remote storage | Planned; not implemented. | Local, SFTP, FTPS, S3-compatible storage and Google Drive | Connection tests, host/certificate verification, outage recovery and discovery after rebuild |
| Backup formats | Planned; not implemented. | gzip, zstd, uncompressed and encrypted incremental repositories | Restore using only the documented archive/key material on a clean machine |
| Partial restore | Planned; not implemented. | Account, folder, database, mailbox, DNS, cron and application data | Restore only selected material; unrelated current data remains intact |
| Migration | Planned; not implemented. | Documented third-party backup formats, remote account transfers and VectorCP exports | Versioned fixtures for each supported transport and backup format |
| Bulk migration | Planned; not implemented. | Accounts, plans and reseller hierarchies; preview, conflicts and progress | Source remains unchanged; partial failures can be resumed and reviewed |
| API access | Planned; not implemented. | Scoped, revocable tokens with expiry and network restrictions | Ownership, permission, expiry, revocation and replay tests |
| Billing modules | Planned; not implemented. | WHMCS, Blesta and FOSSBilling provisioning and sign-on | Real supported-version contract tests for lifecycle and plan changes |
| AI connections | Planned; not implemented. | Per-role MCP tools, restricted permissions and revocable access | Tools cannot exceed their role or expose credentials or unrestricted execution |
| AI authorization | Planned; not implemented. | OAuth authorization-code flow with PKCE and strict redirects | Complete protocol and negative security tests before public exposure |
| AI assistant | Planned; not implemented. | User provider keys, encrypted settings/chats, unlock controls and token budgets | Provider destinations restricted; tenant separation; explicit application of changes |
| AI audit and undo | Planned; not implemented. | Action history and conflict-aware restoration of eligible prior state | Undo refuses after intervening edits; irreversible actions never represented as reversible |
| System services | Partial: observed health and fixed hosting jobs. General lifecycle UI pending. | Service status, lifecycle management, software installation and monitoring | Observed process health; validated changes; failed operations reported accurately |
| Updates | Planned; not implemented. | Signed channels, scheduled panel/OS updates, health checks and rollback | Reject bad signatures; simulate failed update; restore working service |
| Administration | Partial: dashboard, audit and jobs. Broader network/alert/log controls pending. | Network settings, alerts, jobs, logs, audit and initial-setup checks | Real host data; secrets redacted; permissions and failure states correct |

The catalog is a product specification. Implementations must use original code
or appropriately licensed dependencies. A new website version does not silently
redefine a shipped release's acceptance scope. Third-party integrations remain
optional and retain their own licenses.
