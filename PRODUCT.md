# VectorCP product specification

Updated 3 November 2026. This defines the product being built; planned tools are
not available features. Read [FEATURES.md](FEATURES.md) for current status and
[CAPABILITIES.md](CAPABILITIES.md) for the full workflow catalog.

## Purpose

VectorCP is a free, open-source hosting control panel that people install on
their own servers. A person can manage their websites; a hosting company can
create plans, delegate reseller capacity and give each customer a private
workspace. The same product supports both uses.

The core source is MIT licensed. Installation and continued operation must not
depend on an activation key, subscription, a particular server provider or a
VectorCP account. Optional external services may have their own charges and
licenses; ordinary local hosting must work without them.

## Three workspaces

| Role | Responsibility | Boundary |
| --- | --- | --- |
| Owner | Operate the server; manage services, policies, accounts, resellers and recovery | Changes are authorized by the privileged agent and recorded |
| Reseller | Sell hosting within assigned capacity; manage their own plans, customers and recovery | Cannot change server policy, other resellers or owner restrictions |
| Customer | Manage their websites, files, apps, databases, mail, DNS and recovery | Cannot read or change another account or the host control plane |

Collaborator accounts, nested resellers and reseller branding are later
extensions. They need explicit permissions, expiry/revocation and audits.
Interface visibility alone never grants authority.

## Install on your server

The first supported target is a fresh dedicated AlmaLinux 9 x86-64 VPS or
physical server. Other distributions and ARM64 need installation, upgrade,
failure and recovery evidence before being advertised as supported.

The installation contract is:

1. Show OS, architecture, memory, storage, DNS and network checks before changing
   anything. Refuse existing or conflicting hosting services.
2. Show selected components and ports. Keep the initial panel private until an
   owner completes one-time setup and configures trusted HTTPS.
3. Validate configuration before activation. Record completed steps, provide
   useful failure reports and document recovery.
4. Enforce account limits and isolate data. Report provider restrictions such
   as blocked mail ports without pretending success.
5. Keep websites running independently of the browser, project website,
   contributor services and optional integrations.
6. Provide documented updates, backups, export and restoration to another server.

Planned profiles are **Core** (PHP websites and essential services), **Complete**
(additional databases and application runtimes) and **DNS node** (authoritative
DNS for a cluster). The current scripts do not implement this profile selector.
They are development tooling, not a finished one-command production installer.
See the current release's installation and migration limitations.

## Navigation and daily work

Customer tools are organized around Websites, Files, Databases, Email, DNS,
Applications, Backups, Metrics, Security and Preferences. The owner adds
Accounts, Resellers, Plans, Services, Server health, Transfers, Network,
Updates and Audit. Resellers see delegated business tools.

Global search should find tools and permitted accounts. Each operation needs a
clear result, useful validation, visible background progress where needed and
a recoverable failure state. Empty screens explain the next available action.
Keyboard access, mobile layouts and accessible labels are part of delivery.

## What counts as complete

Every capability needs:

- A working service and stored state, an interface and documented limits.
- Backend role and ownership checks, including cross-tenant negative cases.
- Input, quota and concurrency validation; secrets excluded from logs and URLs.
- Observable success/failure, bounded jobs and cancellation where safe.
- Backup/export implications, recovery behavior and upgrade compatibility.
- Repeatable acceptance checks on the supported Linux installation.

A screen, an enabled package flag or a mocked demo does not satisfy this gate.
Public demos contain disabled actions and omitted pages; research from them
informs the scope but does not establish a complete behavior contract.

## Delivery order

1. Finish installation, versioned upgrades, storage lifecycle and recovery tests.
2. Complete account administration, configurable resource plans and MFA/recovery.
3. Deliver mail and public DNS as externally tested services.
4. Expand file transfer, database permissions, PHP settings and WordPress tools.
5. Add schedules, remote backups, safe restores, Git and controlled runtimes.
6. Add transfers, billing connectors, security operations and cluster tooling.
7. Expand platforms and optional integrations after acceptance gates pass.

This is an ordered engineering plan without promised delivery dates. The
[roadmap](ROADMAP.md), [changelog](CHANGELOG.md) and verification notes must stay
consistent with what has actually shipped.

## Ownership and implementation

SparkX Digital maintains VectorCP. Use original source and assets or dependencies
whose licenses permit the intended use. Keep the public identity VectorCP and
describe capabilities in terms of the work users perform. Publish accurate
release notes, required dependency attribution and verified limitations.
