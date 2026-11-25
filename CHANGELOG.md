# Changelog

Verified user-visible changes are recorded with a version and date. Future work is
tracked in [FEATURES.md](FEATURES.md) and
[CAPABILITIES.md](CAPABILITIES.md). See [RELEASING.md](RELEASING.md) for tags,
checksums, versioning and publication rules.

## Unreleased

Future changes will be recorded here after implementation and verification.
Planned capabilities remain in the roadmap.

## 0.4.5 — 25 November 2026 · Development snapshot

### Added

- Root-only, check-first local message snapshots for the optional managed mail
  profile. Private manifests verify message content, folder structure, flags,
  keyword maps and timestamps without exporting passwords or account records.
- Additive recovery into a fresh folder tree in the same existing mailbox and
  account. Current inboxes, newer messages, access state and queued mail remain
  retained; quota, capacity, identity and content checks run before publication.
- Durable interrupted-message recovery. Ordinary publication recovery cannot
  clear these checkpoints. Explicit owner recovery withdraws uncommitted new
  folders into private retained staging, or finalizes a committed operation.

### Changed

- Mail recovery waits for panel readiness after restarting its agent/frontends.
  The Email accounts page distinguishes message recovery from configuration
  publication and directs the owner to the appropriate recovery guide.
- Mail documentation describes the bounded local snapshot workflow and its
  limits. Website and account-transfer backups continue to exclude mail.

### Development limits

- Local message recovery remains owner-only, limited to the same mailbox on the
  same managed installation. Scheduling, automatic retention, encryption, offsite
  mail recovery, clean-host reconstruction and a customer recovery interface are
  separate work. Native mail stays optional; this update does not activate mail,
  change existing routing, open ports or alter DNS.

## 0.4.4 — 24 November 2026 · Development snapshot

### Added

- Scoped, same-domain mail aliases delivering to one existing mailbox. Aliases
  have no login, password or extra storage. Creation and suspension share the
  mailbox publication checkpoint, ownership rules and destination access state.
- An explicit check-first native alias-profile upgrade for existing installations.
  It preserves mailbox credentials/messages, refuses customized configuration,
  retains private backups and leaves interrupted upgrades stopped for inspection.

### Changed

- Versioned, dated development history and a public changelog page. Earlier
  development entries use snapshot identifiers and actual merge dates; they are
  not retroactive stable releases or Git tags.
- Improved website documentation navigation, search, mobile layout and download
  guidance. Each change is verified before publication.

### Limits

- This is a development snapshot, not a stable production release. Aliases are
  receive-only and stay on their destination mailbox's domain. Catch-all aliases,
  chains, external forwarding, webmail, filtering, signing and mail backup remain
  separate work. No existing mail service, DNS or firewall is changed by an
  ordinary application upgrade.

## 0.4.3-dev.20261123 — 23 November 2026 · Mail hosting

- An optional owner-installed native mail profile: scoped mailbox/password/quota
  management, mail-domain approval, SMTP/IMAPS with TLS, sender/relay denials,
  bounded mailbox/queue volumes and durable access-publication recovery. Existing
  external routing is unchanged. At this snapshot, aliases, webmail, filtering, signing, mail backup
  and public delivery acceptance remain open. See [MAIL_HOSTING.md](MAIL_HOSTING.md).

## 0.4.3-dev.20261122 — 22 November 2026 · Account transfers

- Portable account v1 export, resumable checksummed upload, destination
  inspection and import into an existing empty isolation allocation. Primary
  SQL imports use fresh scoped credentials; managed WordPress connection lines
  are remapped. Imported sites stay suspended, DNS stays in recovery copies and
  schedules are paused. Durable allocation journals support failure rollback and
  explicit owner recovery after interruption. See
  [ACCOUNT_TRANSFERS.md](ACCOUNT_TRANSFERS.md) for limits and excluded services.

## 0.4.3-dev.20261120 — 20 November 2026 · DNS recovery and retention

- Monthly UTC backup schedules with day-of-month selection, month-end clamping
  and existing scoped retention. Daily and weekly schedules remain compatible.
- DNS record snapshot/import/export/restore, inactive-zone removal with a recovery
  copy and forward serial history. Durable checkpoints recover interrupted
  publications from committed records. Owner service repair rebuilds missing or
  damaged managed zones, retains original/unreferenced files privately and checks
  UDP/TCP readiness. Upgrades and profile changes refuse pending DNS recovery.
  See [DNS_RECOVERY.md](DNS_RECOVERY.md) for bounds and recovery limits.

## 0.4.3-dev.20261119.2 — 19 November 2026 · Public DNS

- An optional owner-installed public authoritative BIND profile with explicit
  interfaces, UDP/TCP readiness checks, private recovery copies and profile
  rollback. Existing zones stay drafts until activation repeats ownership checks
  through two public resolvers. Record editing, stale-form protection, controlled
  deactivation, zone rebuilds and bounded DNS diagnostics share the existing UI.
  See [PUBLIC_DNS.md](PUBLIC_DNS.md) for delegation and acceptance limits.
- A shared private-state maintenance lock prevents DNS mutations racing the
  supplied DNS/hosting profile helpers. The private installer refuses to overwrite
  a public profile; public profile changes refuse active zones.

## 0.4.3-dev.20261119.1 — 19 November 2026 · Databases and backup scheduling

- Scoped additional MariaDB users and individual database grants, password
  rotation/removal, read-only table browsing, size reports and bounded SQL
  import/export with failure rollback. See [DATABASE_ADMIN.md](DATABASE_ADMIN.md).
- Persistent daily/weekly/monthly UTC website backup schedules, storage accounting and
  rotation after success. Owner-configured SFTP destinations use pinned host
  keys, round-trip hash verification and recovery after local archive deletion.
  See [BACKUP_SCHEDULING.md](BACKUP_SCHEDULING.md) for limits and configuration.
- Reset the PHP start counter after intentional maintenance pauses so repeated
  backup/import jobs can resume PHP without exhausting the crash-loop limit.

## 0.4.3-dev.20261118 — 18 November 2026 · Website routing

- Website redirect rules with exact/folder matching, permanent/temporary status,
  query preservation and remaining-path options; an HTTPS preference that keeps
  the certificate installed; and static HTML error pages for selected statuses.
  Saves enforce ownership, account state, CSRF and revision checks, validate and
  reload Nginx, and restore the previous configuration on failure. Suspended
  websites override customer routing. See [WEBSITE_ROUTING.md](WEBSITE_ROUTING.md).
- Opt-in real Nginx routing acceptance checks on separate loopback listeners in
  an already marked disposable Linux guest.

## 0.4.3-dev.20261105.2 — 5 November 2026 · Selected website access

- Selected-website suspension and activation, bounded to 20 domains, with
  per-domain results, filter-aware selections, owner-hold enforcement and
  stopping without retries after uncertain responses.

## 0.4.3-dev.20261105.1 — 5 November 2026 · Accounts, security and files

- Own-device session inventory, individual/current/all-other revocation, bounded
  active sessions and migration of existing sessions without changing the
  original session table's four-column contract.
- Time-based authenticator enrollment and verification, durable replay/attempt
  checks and eight single-use recovery codes. Sign-in issues no session before
  its required second factor succeeds. Protected changes verify current credentials.
- Password policy, self-service password changes and scoped managed resets.
  Temporary passwords restrict hosting tools until changed; password changes
  revoke sessions and preserve the authenticator.
- Contact editing, scoped server-side account search/filter/pagination, account
  details and atomic selected-account access/plan changes.
- Recursive folder copy including hidden contents, per-item batch copy/move/remove
  results, hidden-file controls and safe permission/owner normalization.
- Recoverable website trash on customer storage, collision-safe restore and
  explicit permanent purge. Trash remains part of storage/entry accounting.
- Standard ZIP creation/extraction using bounded private staging, pre-parser
  metadata limits, safe paths, CRC checks, ownership normalization and no-overwrite
  publication. Retain the existing interface's shared sizing and spacing.
- An opt-in installed-service acceptance driver for disposable Linux guests;
  see [ACCOUNT_SECURITY.md](ACCOUNT_SECURITY.md) and [FILE_MANAGER.md](FILE_MANAGER.md).

### Fixed

- Refuse whitespace path aliases and reserved temporary names throughout file
  operations. Unsupported externally created names cannot silently select another file.
- Preserve existing restrictive file permissions when saving text; new text files
  atomically refuse destinations that appear while the save is in progress.
- Check new-password equality only after verifying the current credential, so
  password-change errors cannot bypass attempt limits to reveal a guessed password.
- Keep public login names separate from internal security-attempt counters and
  reclaim expired attempt records, preserving active blocks through restart.
- Clear closed credential/recovery dialogs and cancel unconfirmed authenticator
  enrollment when its setup dialog closes.

### Limits

- These dated 0.4.3 entries describe development source, not the immutable 0.4.2 download.
- Authenticator secrets rely on root-only database/state permissions and are not
  encrypted at rest. Email recovery/notifications and passkeys remain unfinished.
- Folder/archive/trash operations have explicit bounds; file batches report
  individual outcomes. Website batches stay in the browser and do not resume
  after it closes. Volume resizing, mail, public DNS, migration and the wider
  catalog remain unfinished.

## 0.4.2 — 3 November 2026 · Development snapshot

### Added

- Verified binary upload/download and regular-file copy up to 32 MiB. Uploads
  use bounded private staging, sequential retried chunks, one-hour expiry,
  restart recovery and idempotent completion receipts.
- Move/rename files and folders without replacing existing destinations, scoped
  filename search, and confirmed removal of regular files or empty directories.
- Ordinary file actions, upload progress and search controls in the existing
  responsive file manager. Keep the shared control, spacing and dialog scales.
- An explicit opt-in native Linux acceptance harness for unused disposable
  installations, plus file operation and HTTP transfer boundary tests.

### Fixed

- Prepare certificate/ACME directories before granting the hosting agent access;
  fresh private installations no longer require prior public certificate setup.
- Restart and health-check the core panel after adding hosting/DNS unit paths.
  Serialize profile changes and refuse active hosting jobs.
- Refuse a setup-token request on an initialized installation before running
  agent startup recovery, preserving live job state.
- Preserve operation-specific storage/conflict errors after opening a directory
  instead of reporting every downstream filesystem error as a missing folder.

### Validation and limits

- Native AlmaLinux 9 x86-64 service, isolation, SQL, backup/restore, upgrade,
  deliberate startup rollback and reboot checks are recorded in VERIFICATION.md.
- File transfer limits and internal operations are documented in FILE_MANAGER.md.
  Recursive/batch copying, hidden-file controls, trash/undo, archives and file
  permission editing remain separate work.
- Older-layout migration, email, public authoritative DNS, billing and the wider
  catalog remain unfinished. This is not a stable production release.

## 0.4.1 — 3 November 2026 · Development snapshot

### Changed

- Replace the overview with a searchable, grouped Tools directory and a server
  or account information column. Keep account-management tools scoped to owners
  and resellers.
- Use a shared 40 px desktop / 44 px phone control scale, readable table and
  helper text, 24 px / 16 px page gutters and compact, consistent panels.
- Replace clipped phone navigation with an accessible drawer, keyboard focus
  management, background isolation and Escape dismissal.
- Label dialogs and table regions, focus initial fields, allow long values to
  wrap and keep wide tables within keyboard-accessible scrolling regions.
- Show visible page-loading status, fetch independent page data in parallel and
  prevent older navigation responses from replacing newer selections.
- Add filters for visible websites and accounts, clear empty search results,
  active-plan validation and distinct destructive-action buttons.
- Limit background job refresh to operation/status pages so file editors are
  not rebuilt while an operator is typing.
- Extend the target catalog to 253 workflows, explicitly separating remaining
  mail operations, optional integrations and hosting-business billing.

### Delivery limits

- This interface update adds no mail transport, public DNS delegation or billing
  backend. Planned catalog rows remain planned.
- The 0.4.x installation layout still needs fresh Linux and migration acceptance.
  Existing 0.3.x installations must not run the fresh installer or rename their
  active directories. This snapshot is not a stable release.

## 0.4.0 — 3 November 2026 · Development snapshot

### Added

- Original split-V identity, outlined wordmarks and light, dark and monochrome
  SVG variants; matching panel icons and brand usage guidance.
- A self-hosted product specification covering personal websites and hosting
  businesses, with owner, reseller and customer responsibilities.
- A detailed capability catalog covering customer tools and server operations,
  with implementation status and acceptance requirements.
- A documented release process for accurate changelogs, immutable archives,
  matching tags and checksums.

### Changed

- Use VectorCP throughout current product copy, source, package names, services,
  cookies, DNS ownership labels and default installation paths.
- Broaden fresh-host conflict detection to occupied web/control ports and
  existing control databases.
- Include brand assets in deterministic source archives.

### Upgrade requirements

- This snapshot introduces a new installation layout. The upgrade helper
  requires that layout and refuses older installations. A migration from 0.3.x
  remains pending; do not rename active service/data directories or reinstall
  over an existing server. See the README and verification notes.
- This is a development snapshot, not a stable production release. It does not
  add mail delivery, public authoritative DNS or the other planned services.

## 0.3.1 — 3 November 2026

- Establish the VectorCP public identity in the interface, documentation,
  service descriptions and source package.
- Share “Open-source hosting control” and “Your hosting. Your control.” across
  sign-in and workspace screens.
- Keep the existing installation layout unchanged in this version.
- Share the canonical version between packaging, agent health and workspace.

## 0.3.0 — 3 November 2026

- Add owner-created resellers and reseller-owned customer accounts.
- Add immutable customer/reseller packages, explicit assignment, retirement,
  feature permissions and non-oversold customer/site/storage reservations.
- Scope files, sites, database details, jobs, backups and activity to delegated
  customers. Preserve owner restrictions and revoke child sessions on a parent lock.
- Add DNS record validation, private authoritative preview, serial tracking,
  zone export and public TXT ownership checks.
- Add separate owner/reseller/customer sign-in paths.
- Remove deployment-specific server addresses from application code.
- Document the product contract, contribution process, architecture and gaps.

## 0.2.0 — 2 November 2026

- Add isolated customer storage and processes, PHP 8.3, private MariaDB,
  WordPress installation, customer HTTPS and bounded local backup recovery.

## 0.1.0 — 1 November 2026

- Add owner/customer authentication, static hosting, bounded file editing,
  website suspension, local static exports and scoped activity.

Verification is release-specific. A history entry does not assert that the
complete product or every acceptance gate is finished.
