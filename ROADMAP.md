# VectorCP roadmap

VectorCP aims to become a complete open-source hosting control panel for server
owners, resellers and customers. The current release is **0.3.1**, an early
development milestone. [FEATURES.md](FEATURES.md) is the detailed capability map;
[VERIFICATION.md](VERIFICATION.md) records what has actually been exercised.

These are ordered capability gates, not release-date promises. Scope can change
as implementation and testing uncover dependencies.

## Current foundation

Owner/reseller/customer roles; immutable hosting plans and reservations; isolated
static/PHP websites; per-customer databases; WordPress installation; domain HTTPS;
local website backup/restore; scoped jobs/activity; DNS editing with a private
authoritative preview and export. See the documented limits for each feature.

## 1. Public development foundation

Publish the source, accurate docs, working checks, issue guidance and a verified
private security-reporting route. Match release tags to reviewed source and
checksums. Exercise installation and recovery on a fresh dedicated test VM.

Complete when a new contributor can reproduce the documented setup, tests and
source package, and an operator can follow the tested recovery procedure.

## 2. Hosting reliability and account control

Improve resource profiles, storage lifecycle and plan changes. Exercise full
volumes, interrupted jobs, concurrent hostile workloads and backup/restore
failures. Build MFA/recovery and audit improvements with explicit boundaries.

Complete when authorization, isolation, rollback and recovery checks cover both
successful and failed operations on the supported Linux target.

## 3. Mail and public DNS

Implement mailboxes, routing, quotas, TLS, antispam, deliverability checks and a
webmail path. Provide public authoritative DNS, record lifecycle and DNSSEC with
clear delegation and network configuration. Current DNS preview is not public
DNS hosting; current package flags do not provide a working mail service.

Complete when external mail delivery and public DNS behavior are independently
verified, tenant boundaries hold and backup/restore includes these services.

## 4. Developer and recovery workflows

Add controlled cron, Git deployment, additional supported application runtimes,
restricted shell/FTP access and migration paths. Add scheduled, off-server and
incremental backups with retention and recovery verification.

Complete when every operation enforces role/ownership and resource limits, and
the documented recovery/migration path succeeds on real test installations.

## 5. Wider service and distribution coverage

Develop update/rollback management, WAF/scanning, billing integrations, broader
reseller models and extensibility. Independently assess security and sustained
load. Expand platforms only after installation, upgrade and recovery validation.
AI/MCP integrations remain exploratory until a narrow, authorized model exists.

Complete when feature claims are backed by repeatable acceptance evidence and
published operational limits. Full competitor parity will be tracked against
the detailed feature map rather than inferred from interface similarity.

## Contribute

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Propose one capability with a clear
user, acceptance criteria and service dependencies. Keep security reports private
using the route documented in [SECURITY.md](SECURITY.md).
