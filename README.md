# VectorCP

**An open-source hosting control panel for server owners, resellers and customers.**

VectorCP is independently written under the MIT license. The product target is
an alternative to cPanel/WHM with BHPanel's documented feature coverage. Version
0.3.1 is an early development release. [Feature coverage](FEATURES.md) states the
remaining work; this release does not provide complete parity.

The product has no provider-specific dependency, license server or activation
fee. A user's VPS is one deployment. Do not embed its credentials or customer
data in the source. Supported installation target: dedicated AlmaLinux 9;
x86-64 has been exercised. Other platforms and ARM64 remain unverified.

## Project

Maintained by [SparkX Digital](https://www.sparkxdigital.co.uk/).
Project website: [vectorcp.net](https://vectorcp.net/).
Development repository: [SparkX-Digital/vectorcp](https://github.com/SparkX-Digital/vectorcp).
See the [roadmap](ROADMAP.md) for the next capability gates.

## Available

- Owner/reseller/customer authentication, hashed passwords and sessions, CSRF,
  exact Host/Origin checks, secure cookies, login throttling and scoped activity.
- Static websites, ownership, Nginx validation/reload/rollback, file management,
  atomic text edits and administrator website suspension.
- Up to 16 isolated customer allocations: non-login Linux identities, separate
  capped ext4 volumes, private mount namespaces and resource-controlled services.
- PHP 8.3 through a customer-specific PHP-FPM service. Shell execution functions
  are disabled in FPM; uploads cannot execute PHP in WordPress's uploads directory.
- A private MariaDB 10.11 instance per database-using customer. It has no TCP
  listener. Each website gets a separate database and application credential.
- WordPress installation from the current official release, HTTPS downloads and
  verification against the official per-file checksums. The installer runs as
  the customer, never as root. WordPress credentials stay out of argv and logs.
- Domain HTTPS via Let's Encrypt HTTP-01, DNS preflight and automatic renewal.
  An existing WordPress site can switch from HTTP to HTTPS through the panel.
- Local files-and-database backups, restore with a temporary previous copy and
  database rollback snapshot, download and retention deletion. Downloads use
  small retried requests and verify the final SHA-256 in the browser.
- Background job status for long operations. Interrupted jobs fail visibly;
  they are not silently restarted with potentially destructive duplicate work.
- Reseller delegation: each reseller manages its own customers, sites, files,
  databases, jobs and backups. Owner locks and website holds take precedence.
- Immutable customer/reseller packages, explicit assignment and retirement,
  inherited feature permissions and reserved customer/site/storage pools.
- A DNS record editor for A, AAAA, CNAME, MX, TXT, NS, CAA and SRV records,
  private authoritative validation, zone export and public TXT ownership checks.

## Use

1. Sign in through `/admin`, `/reseller` or `/customer`. The agent authorizes each
   operation regardless of the entry URL.
2. In **Hosting plans**, create a customer package. In **People**, create a
   customer with that package, then select **Enable hosting**. The owner may
   instead create a reseller package and reseller; that reseller creates its
   own customer packages and accounts.
3. Customer plans choose 512–4096 MB. This fixed volume includes files, databases, logs and
   temporary application data. Enable hosting before creating the customer's
   websites; migration/resizing of existing allocations is not implemented.
4. Add a website owned by that customer.
5. In **Apps & hosting**, select the website and install WordPress, or enable
   PHP and create a database. WordPress needs a fresh site containing only its
   welcome page. Keep the WordPress password separately from the panel password.
6. Point the domain's A record to the server IP. Remove conflicting A/AAAA
   records, then select **Enable HTTPS**. Only IPv4 serving is implemented.
7. Use **Backups** to create, download, restore or delete a local recovery copy.

The owner/admin account remains a control-plane identity; create application
sites under an isolated customer. Existing static accounts remain usable.
Locking panel access signs a customer out; website suspension is a separate action.
Mail delivery and public authoritative DNS are not provided by this release.
**DNS zones** provides a private preview and export for an existing DNS provider.
The preview listens only on the VPS loopback address. Public DNS records are not
changed by the editor. Exported SOA/NS entries describe the preview; adapt them
to the destination provider. Public DNS hosting, PowerDNS, DNSSEC and clustering
remain planned.

## Hosting boundaries and limits

Each customer uses a fixed non-login UID and its own mounted volume. Nginx has
read access through supplementary groups. PHP/database/task services see only
that customer's subtree under `/srv`; other customer trees, the control database
and the agent socket are hidden. Unix permissions add a second boundary. The
SELinux policy remains enforcing. No custom panel SELinux confinement policy is
claimed. The global database-network SELinux boolean remains off; database
connections use private Unix sockets with the correct labels.

The customer workload slice has a 2200 MB memory ceiling and 150% CPU quota in
the default small-server profile. Each customer has a 448 MB memory ceiling, 75% CPU quota and
48-task limit. PHP is limited to two workers, 96 MB per request and a 60-second
request timeout; its service ceiling is 256 MB. The database service ceiling is
192 MB. These are small-server defaults, not benchmarked capacity guarantees.

Total allocated volume sizes cannot exceed 16 GiB. Volume space is enforced by
its filesystem capacity, not by periodic usage reporting. Usable space is less
than the selected size because filesystem metadata consumes space. A separate
logical file allowance still protects panel writes. There is no shell, FTP or container runtime yet. Packages control customer/site/
storage reservations and feature permissions; adjustable CPU/memory/I/O/traffic
profiles and dynamic inherited package updates remain planned. Assigned packages
are immutable; retire them or assign a different package explicitly. Existing
physical volumes must keep the same storage size during reassignment.

The text editor supports UTF-8 files up to 256 KB. File listing shows at most
1000 entries per folder. Panel creation is limited to 12,000 entries per hosted
site; application writes are constrained by volume capacity. Backups support
200 MB of files, 16 MB per individual file, 12,000 entries, and 64 MB of database
SQL. Up to 5 copies / 512 MB per customer and 2 GiB total are retained. PHP pauses
for a consistent copy and during restore. Restore needs room for a temporary
second copy inside the customer's volume. Hidden regular files and empty
folders are included; symlinks and special files are excluded. These are local
website backups, not whole-server images. Keep a downloaded independent copy.

## Installation

The scripts target a dedicated AlmaLinux 9 host. The initial installer refuses
an existing hosting stack and defaults to a read-only preflight:

```sh
bash deploy/install.sh --check
bash deploy/install.sh --apply --open-http
```

The base installation is private on loopback. Bootstrap the owner through its
one-time setup token, then use `deploy/public-https.sh` for public administrator
HTTPS. Its staged `--check`, `--prepare`, `--publish` workflow is documented in
the script; the IP profile uses short-lived certificates and a renewal timer.
Do not rerun the initial installer on an installed host.

Extract the reviewed source release outside the active installation. The upgrade
helper defaults to preflight, makes an online SQLite/application backup when
applied, and restores the previous application if startup fails. Choose a quiet
maintenance window; the panel briefly stops while hosted websites keep serving.
For an existing installation:

```sh
python3 deploy/upgrade.py --check
python3 deploy/upgrade.py --apply
```

Install or refresh the optional native service profiles as needed:

```sh
bash deploy/hosting-install.sh --apply
bash deploy/dns-install.sh --apply
systemctl restart veyra-agent veyra-web veyra-web-public
```

The hosting helper installs official AlmaLinux PHP 8.3/MariaDB 10.11 packages
when missing, prepares fixed service identities/templates and SELinux labels,
and disables the unused shared default PHP/MariaDB services. Customer workloads
start on demand. SQLite migrations are additive and preserve existing owner
credentials, sites and sessions. Back up before upgrading. Clean-image recovery,
unrelated hosting stacks and distribution/version migrations are not tested.
The helper does not provision a domain, purchase a service or change SSH access.

### Compatibility with development installations

VectorCP was previously developed under the working name VeyraPanel. Version
0.3.1 introduces the public name while retaining the existing `veyra` Python
package, service names, verification-record prefix and `/opt/veyrapanel`,
`/var/lib/veyrapanel`, `/srv/veyrapanel` and related configuration paths. Current
installers use these identifiers too. This preserves the upgrade path for
existing installations; changing them manually can disconnect the panel from
its accounts, customer services and certificates.

See [branding](BRANDING.md) for the public name and identity.

## Local development and checks

Python 3.9+ on Unix; no third-party app runtime libraries are required. Local
validation deliberately does not simulate successful Linux hosting operations.

```sh
python3 dev.py --data /absolute/path/to/private/runtime
python3 -m unittest discover -s tests -v
```

To build a deterministic source-only ZIP and checksum outside the source tree:

```sh
python3 deploy/package.py --output /absolute/path/VectorCP-source.zip
```

Hosting features require the Linux services and are disabled in local mode.
See `VERIFICATION.md` for the exact live evidence and remaining limitations.

## Remaining product scope

Dynamic inherited plans, nested resellers, mail/webmail, public DNS/DNSSEC, customer shells
and FTP, scheduled/off-server/incremental backups, arbitrary application runtimes,
cron/Git, migration, WAF/scanning, billing, update/rollback management and AI/MCP
integrations remain further work. Independent security review, sustained load,
crash/disk-exhaustion recovery and comprehensive acceptance testing are pending.

See [architecture](ARCHITECTURE.md), [contributing](CONTRIBUTING.md),
[security](SECURITY.md), [changelog](CHANGELOG.md) and [coverage](FEATURES.md).
A public repository URL and monitored vulnerability-reporting channel have not
yet been established. This source archive can be used and modified under MIT.

The VectorCP source is independently written under the included MIT license.
PHP, MariaDB, WordPress and certificate tooling retain their own licenses.
Implementation references: [PHP-FPM](https://www.php.net/manual/en/install.fpm.configuration.php),
[MariaDB initialization](https://mariadb.com/docs/server/clients-and-utilities/deployment-tools/mariadb-install-db),
[WordPress installation](https://developer.wordpress.org/cli/commands/core/install/),
[systemd resource control](https://www.freedesktop.org/software/systemd/man/251/systemd.resource-control.html).
