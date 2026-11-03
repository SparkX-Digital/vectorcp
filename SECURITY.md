# Security policy

This is an early development release. No independent security audit, production
support commitment or response-time guarantee has been established.

Do not post private keys, login details, customer data or a working exploit for
a live installation in a public issue. Use a repository host's private security
advisory facility once the public project is established. A monitored reporting
address and supported-version policy must be configured before public launch;
none is invented here.

A useful report gives the affected release, platform, prerequisite role, exact
reproduction using synthetic data, expected versus observed behavior and impact.

## Boundaries

The web frontend is unprivileged and cannot read the control database. A root
agent authenticates and authorizes each bounded operation over a local Unix
socket. Customer workloads have distinct Unix identities, fixed storage volumes,
private mount namespaces and cgroup limits. This is shared-kernel isolation, not
separate virtual machines. SELinux remains enforcing on the test installation;
a custom agent confinement policy is not yet provided.

The owner can administer the server and its customer data. A reseller can manage
only its delegated customers, including their files and backups. Reseller access
is deliberate administrative delegation. Customers cannot create other accounts
or increase their own allowances. An owner lock takes precedence over reseller
changes. No public arbitrary shell endpoint is provided.

DNS in 0.3 is a loopback-only authoritative preview. It cannot change a domain's
public DNS until the operator independently configures a public DNS service or
imports the zone at an existing provider. No public recursive resolver is enabled.

Production hardening, secret encryption, MFA/recovery, comprehensive audit of
service helpers, hostile concurrent workload testing, signed updates and clean
recovery drills remain necessary work. See `FEATURES.md` and `VERIFICATION.md`.
