# Changelog

User-visible changes are recorded here. Future work belongs in **Unreleased**;
planned capabilities are tracked in [FEATURES.md](FEATURES.md) and
[CAPABILITIES.md](CAPABILITIES.md). See [RELEASING.md](RELEASING.md) for tags,
checksums, versioning and publication rules.

## Unreleased

No additional completed changes recorded.

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
