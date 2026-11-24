# Optional mail hosting — development profile

VectorCP can provision virtual mailboxes on AlmaLinux 9 x86-64 using the
distribution's Postfix 3.5 and Dovecot 2.3 packages. This is a limited development
profile: mailbox creation, password changes, quotas, suspension, local-domain
delivery, authenticated SMTP submission and IMAPS are implemented. Same-domain
receive-only aliases are also implemented. External forwarding, webmail, spam/virus
filtering, signing, mail backup and broader
routing remain planned. Internet delivery and reputation are not accepted.

The profile is optional. An application upgrade adds the controls without
installing mail packages, opening ports or changing DNS. Existing external mail
providers and their MX records are preserved.

## Install

Use the supported canonical VectorCP installation after upgrading the application.
This installer does not migrate an existing mail server. It refuses active mail
services, modified mail packages, queued messages, occupied mail ports, existing
profiles/images and mail records whose storage/profile has disappeared.

Prepare a root-owned certificate chain covering the full mail-server hostname
and a matching root-only private key. The certificate must have at least one day
remaining. A private CA can be used for testing; public clients need a trusted
certificate. No certificate or password is supplied by the project.

From an extracted, reviewed development source tree:

```sh
sudo bash deploy/mail-install.sh \
  --hostname mail.example.net \
  --cert /root/mail-fullchain.pem --key /root/mail-key.pem \
  --storage-mb 512
```

This checks only. Repeat with `--apply` to install. The default listener is
**127.0.0.1**, intended for local evaluation. For reachable hosting, explicitly
add each assigned IPv4 using `--listen`, arrange matching hostname/MX/PTR and
sender policies, and configure the host/provider firewall for TCP 25, 587 and
993. IPv6, POP3, port 143 and implicit-TLS submission on 465 are not provided.
The installer makes no firewall, registrar or public-DNS changes. Keep existing
mail routing until the intended replacement has passed its delivery checks.

Installation briefly stops the panel frontends and agent, backs up configuration,
queue and the control database privately, and installs packages from the OS
repositories. Existing customer web/database services are not restarted. Final
readiness checks verify the certificate and IMAP/STARTTLS listeners, encrypted
authentication advertisement and anonymous relay rejection before reporting
success. The private command log is retained with the installation backup.

## Upgrade an existing mail profile for aliases

An ordinary application upgrade preserves native mail configuration. After
upgrading to source version 0.4.4, the owner can run this on a supported managed
mail installation:

```sh
cd /opt/vectorcp
sudo python3 -m vectorcp.mail_alias_profile
# After reviewing the check-only result:
sudo python3 -m vectorcp.mail_alias_profile --apply
```

The helper requires a healthy managed profile, idle hosting jobs and unchanged
Postfix configuration. It briefly pauses the panel and both mail services,
retains private configuration/control/lookup backups, durably adds the alias map
and verifies TLS readiness. Mailbox storage and queued messages are preserved.
It makes no DNS, firewall or credential changes. Repeating the helper on a healthy
upgraded profile is a check-only no-op. An interrupted upgrade leaves mail stopped
and a maintenance marker. Root must inspect the private backup, command log,
profile marker and managed map before recovering; do not reinstall or format mail
storage. Fresh mail installations include the alias map.

## Receive-only mail aliases

Under **Email accounts → Mail aliases**, select a destination mailbox and enter
another address before `@`. The alias shares that mailbox's domain, inbox and
quota. It has no password and cannot sign in or send. Only the owning customer,
its reseller or the server owner can manage it. Mailbox and alias names cannot
collide, including suspended addresses. Up to 64 aliases per customer and 512 per
server are retained. Suspension preserves the address and rejects new delivery;
queued/already delivered messages remain. Destination, domain, account, reseller
and package suspension also pause aliases. Access changes use the existing
stop-before-commit checkpoint and owner recovery.

There are no external destinations, alias chains, catch-all addresses, alias
editing or address removal in this batch. Create another alias and suspend the
previous one when changing a routing address. Native lookup tables only publish
active mappings. See the [Postfix virtual alias manual](https://www.postfix.org/virtual.5.html).

## Owner, reseller and customer workflow

1. Create an ordinary isolated customer, give it a plan including Email and add
   its website. Mail domains follow these website domains.
2. As the server owner, open **Email accounts → Enable mail** and confirm the
   exact domain after checking ownership and routing. Resellers and customers
   cannot activate domains themselves.
3. The customer, its owning reseller or the server owner can create mailboxes,
   change their passwords/quotas and suspend them. Requests are scoped by actual
   account ownership and protected against cross-site request forgery.
4. Connect using the full email address: **IMAPS 993 with TLS**, and **SMTP 587
   with STARTTLS and authentication**. Passwords are separate from panel login.

Passwords require 15–72 characters and at most 72 UTF-8 bytes; control characters
are refused. Dovecot generates cost-12 bcrypt hashes via standard input, without
putting passwords in process arguments. Plaintext passwords and hashes are never
returned by the panel or recorded in its activity log. Users cannot retrieve a
forgotten mailbox password; an authorized operator sets another one.

Only authenticated submission can relay to other domains. Its envelope sender
must match the authenticated mailbox; an empty submission sender is refused.
Port 25 accepts known active local recipients and does not provide authentication
or anonymous external relay. System-user delivery and website `sendmail` pickup
are disabled. SMTP message rate limits are global per-client controls, not the
planned shared per-customer allowance for SMTP and website scripts.

## Storage, limits and isolation

- A separately mounted, preallocated ext4 mailbox image is 128–8192 MB. A second
  256 MB image bounds the native queue. Both use `nosuid,nodev,noexec`; service
  dependencies require the mounts. These are separate from customer web volumes.
- At most 80% of mailbox volume capacity is reserved for mailbox quotas, leaving
  room for metadata. Mail reservations per customer cannot exceed its package's
  storage allowance. Mail and website files use separate physical volumes; this
  is not one combined filesystem quota. Suspended boxes retain reservations.
- Up to 32 mailboxes per customer and 128 per server; each has 1–4096 MB quota.
  Message size is capped at 16 MB. Dovecot enforces quotas for IMAP APPEND and
  LMTP delivery. Lowering a quota preserves messages and can block new delivery.
- A non-login virtual-mail service identity stores messages. Isolation is through
  native authentication and mailbox namespaces, not a separate OS UID for every
  mailbox. Customer website UIDs cannot read this store.
- Native services read a small separate lookup database containing only mail
  domains, mailbox hashes, homes, quotas and effective access. They cannot read
  the panel control database through this interface. A dedicated SELinux file
  type permits the required mail readers; SELinux remains enforcing.

Suspending a mailbox, website, customer or parent reseller revokes effective mail
access. Plan mail permissions are inherited. Domain disablement keeps messages
and credentials but rejects delivery. There is no purge/termination operation in
this batch. Mail messages and metadata are excluded from website backups and
portable account transfers; those exports do not protect mail.

## Publication and recovery

Mailbox and effective access changes briefly stop **both** native mail services
before committing the control change. This disconnects existing SMTP/IMAP
sessions. A durable root-only checkpoint is written first; only committed state
is published into the lookup, then services restart. Website and database
services keep running.

An interrupted publication leaves mail stopped. Native unit startup is blocked
by `/var/lib/vectorcp-mail/pending.json`. A separate root-owned startup program
checks mounts, lookup ownership and the checkpoint; inaccessible checkpoints
fail closed. Installer configuration, TLS files and unit gates are replaced
atomically and synced to disk before activation. The Email accounts page also detects
missing/corrupt lookup data, missing mounts and inactive services. It reports
paused access rather than claiming those mailboxes are active. Customers cannot
restart a profile stopped by its owner.

After inspecting the mail journal, mounts and configuration, the owner can use
**Recover mail services**, confirming `RECOVER MAIL`, to rebuild from committed
records and restart services. Recovery does not delete or overwrite mailbox
messages. Never remove a checkpoint merely to bypass startup checks. A missing
volume needs storage recovery first.

An interrupted **installation** needs root inspection of the private installation
backup, command log and `/run/vectorcp-profile-maintenance`. Before the installed
profile marker exists, the panel recovery action is not an installer resume tool.
Do not delete or reformat images to retry. Certificate renewal/replacement is
currently owner-managed; the installer copies the supplied files and does not
install an automatic mail certificate renewal workflow.

## Acceptance evidence and remaining work

The opt-in [native acceptance script](tests/acceptance_mail_linux.py) uses a
marked disposable AlmaLinux guest, two separate newly isolated customers and
synthetic domains. Eight groups verify TLS, disabled plaintext/unused listeners,
relay/unknown-recipient/sender denials, real queue-to-LMTP-to-IMAP delivery,
cross-customer password/path denials, IMAP and LMTP quota rejection, password and
account revocation, persisted-checkpoint recovery with message retention, bounded
mounts, password hashes and healthy services with SELinux enforcing.

These tests use loopback routing and a private test certificate. No Internet
messages are sent. They do not establish WAN SMTP delivery, independent-client
compatibility, PTR/reputation, signing/filtering, high-volume capacity, clean-host
mail restoration or an independent security audit. Public rollout needs those
acceptance checks and mail-specific backups. This is not complete mail parity.

Implementation references: [Dovecot 2.3 SQL authentication](https://doc.dovecot.org/2.3/configuration_manual/authentication/sql/),
[Dovecot quota](https://doc.dovecot.org/2.3/configuration_manual/quota_plugin/),
[Dovecot password schemes](https://doc.dovecot.org/2.3/configuration_manual/authentication/password_schemes/),
and [Postfix parameters](https://www.postfix.org/postconf.5.html).

A separate [prepare/verify boot harness](tests/acceptance_mail_boot_linux.py)
records startup-gate hashes, committed mail-record digests and a nonempty
message inventory. After deliberate QEMU process termination and restart, four
checks verify retained gates/checkpoint/data and explicit owner recovery. The
eight protocol groups pass again afterward. This is not a physical host
power-cut test.
