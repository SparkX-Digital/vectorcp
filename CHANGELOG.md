# Changelog

## 0.3.1 — 3 November 2026

- Adopt VectorCP as the public product name, replacing the VeyraPanel working
  identity in the interface, documentation, service descriptions and releases.
- Use the shared descriptor “Open-source hosting control” and the line
  “Your hosting. Your control.” across the sign-in screen and workspace.
- Retain existing package, service, storage, certificate and verification
  identifiers for compatibility with development installations.
- Share the release version between packaging, agent health and the workspace
  so the displayed release cannot drift from the source archive version.
- Document the public identity in `BRANDING.md`. Feature coverage is unchanged.

## 0.3.0 — 3 November 2026

- Add owner-created reseller accounts and reseller-owned customers.
- Add immutable customer/reseller packages, explicit assignment, retirement,
  feature permissions and non-oversold storage/site/customer reservations.
- Scope files, sites, database details, jobs, backups and activity to delegated
  customers. Preserve owner locks and revoke child sessions on a reseller lock.
- Add DNS record validation, private authoritative preview, serial tracking,
  zone export and public TXT ownership checks.
- Add separate owner/reseller/customer sign-in paths.
- Remove deployment-specific server addresses from application code.
- Document the open-source product contract, contribution process, architecture
  and feature gaps. Retain the MIT license.

See `VERIFICATION.md` for release validation; this entry alone does not assert
that every feature has passed its acceptance checks.

## 0.2.0 — 2 November 2026

Isolated customer storage and processes, PHP 8.3, private MariaDB, WordPress
installation, customer HTTPS and bounded local files/database backup recovery.

## 0.1.0 — 1 November 2026

Initial owner/customer authentication, static hosting, bounded file editing,
website suspension, local static exports and scoped activity.
