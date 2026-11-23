# Native Linux acceptance

Use a disposable, unused AlmaLinux 9 x86-64 VM. Do not run acceptance against
customer data or an occupied hosting server. The harness refuses an installation
that already has an owner or accounts, and requires an explicit opt-in flag.
Local unit tests do not execute it.

1. Verify the reviewed source archive, extract it outside `/opt/vectorcp` and run
   the fresh installer with `--check`, followed by `--apply`.
2. Install the optional hosting and private DNS profiles from that same source.
   Keep the panel loopback-only; no public administrative or DNS port is needed.
3. From the extracted source, run:

```sh
sudo python3 tests/acceptance_linux.py --allow-disposable-host
```

This creates an owner, two customers and reserved `.test` websites; provisions
two fixed customer volumes; runs PHP and private SQL; attempts sibling/control
state reads; restores files and SQL from a local backup; and checks chunked
binary transfers through an agent restart. It exercises copy, move, search and
removal on real customer storage. It also checks enforcing SELinux, service
health, installer refusal on an existing host and private network listeners.

The script prints check names without credentials. Its resume context is stored
in the root-only state directory at `/var/lib/vectorcp/acceptance-context.json`;
the result summary is `acceptance-results.json` in that same directory.
Keep both files outside source archives and support bundles. The harness retains
its test records for inspection and does not erase the VM.

## Recovery and upgrade checks

For the Unreleased account/security/file workflows, copy the reviewed source to
the initialized disposable guest **before** upgrading. Its existing private
`acceptance-context.json` must contain the generated owner credentials and
isolated customer fixtures. Prepare a fresh owner session with the next source's
driver, then upgrade and verify:

```sh
python3 tests/acceptance_workflows_linux.py --allow-disposable-host --before-upgrade
python3 deploy/upgrade.py --check
python3 deploy/upgrade.py --apply
python3 tests/acceptance_workflows_linux.py --allow-disposable-host
```

The driver checks session migration/revocation, authenticator and recovery
sign-in, forced password rotation, account details/search, the installed HTTP
cookie flow, customer-owned folder copy, ZIP round-trip/scope, permissions and
trash recovery through an actual agent restart. It purges only its newly created
verification files and locks its additional verification account. The account
and its reservation remain for inspection. The safe result summary and source
file hashes are written to `security-acceptance-results.json` in root-only state.
Use optional `--candidate-archive /path/to/reviewed-source.zip` to record its hash.
Neither private context nor credentials belong in published source or logs.

Record `/proc/sys/kernel/random/boot_id`, reboot only the disposable guest, and
verify that the boot ID changes, both customer volumes remount, PHP/SQL and panel
services recover, the retained customer sessions remain scoped and the `.test`
site still returns its restored database value.

On the initialized test VM, extract the next reviewed source separately and use
`deploy/upgrade.py --check`, then `--apply`. Confirm the reported version, owner
and customer sessions, website content and database value. For startup rollback,
make a private copy of the candidate source and inject an import-time failure;
apply only that private copy to this disposable VM. Verify that the helper restores
the previous application, retains its database snapshot, and the website works.
Never publish that intentionally broken fixture as a release.

The service-profile helpers refuse active hosting jobs and serialize their
maintenance with `/var/lib/vectorcp/profile-maintenance.lock`. Unreleased DNS
mutations also take that lock in shared mode. A crash can leave
`/run/vectorcp-profile-maintenance`; inspect the interrupted installer and active
jobs before removing that marker and retrying. The marker blocks new hosting
jobs in the current agent. A normal helper exit removes it automatically.

This acceptance does not prove trusted public certificate issue/renewal, public
DNS delegation, email delivery, an older-layout migration, multi-platform
installation, independent disaster recovery or a production security audit.
Record the tested source, OS image, versions and actual results in
[VERIFICATION.md](VERIFICATION.md).

## Optional public DNS service checks

On that disposable guest only, the Unreleased `tests/acceptance_dns_linux.py`
requires `--allow-disposable-host`, the operator-owned `--public-ip` and either
`--prepare` or `--finish`. Prepare configures the guest fixture IPv4 marker if
absent; it does not issue a TLS certificate. It checks actual BIND profile changes,
draft exclusion, a failed real ownership query, fixture-authorized activation,
record edits, reload/profile rollback, recursion/transfer denial and SELinux.
It leaves one reserved `.test` zone active for an off-guest UDP/TCP query.
Finish stops public hosting, retains records and rebuilds the private preview.
Use temporary, guest-only network rules if needed for the off-guest check; do not
open the production host firewall. Positive ownership is a controlled test fixture,
not evidence of real public ownership or registrar delegation. Never publish its
private baseline owner credentials or control-state context.

## DNS recovery and monthly backups

On an existing marked disposable guest with private DNS and a spare site slot
in isolated customer slot 2, run `tests/acceptance_recovery_linux.py` with
`--allow-disposable-host`. This creates dedicated `.test` fixtures, stops the
agent while testing, checks BIND UDP/TCP, snapshot restore/removal, actual abrupt
process exits before/after commit, stopped-service recovery, missing/corrupt zone
repair and private quarantine. It runs three monthly backup jobs, verifies
retention and hashes every pre-existing archive. Existing schedules are restored;
the new monthly fixture is left paused. SELinux must remain enforcing.
The script deliberately refuses insufficient fixture capacity; it does not
silently reset existing sites. This proves neither public delegation nor a
clean-server disaster recovery path.

## Portable account transfers

On a marked disposable guest with the earlier native account/SQL fixtures, run:

```sh
sudo python3 tests/acceptance_transfers_linux.py --allow-disposable-host
```

The driver exports isolated customer slot 1, provisions a fresh destination
allocation and uses a separate control database to represent another server.
It verifies archive/file/SQL integrity, table row checksums, scoped credentials,
injected SQL failure rollback, unchanged source/account records, suspended Nginx
responses and explicit PHP maintenance-stop recovery after an interrupted-export
checkpoint. The guest remains SELinux enforcing. It retains private result JSON,
archives and test allocations for inspection; it never changes public routing.
It needs enough free allocation slots/storage and stops/restarts the guest agent.
Never run it on an occupied production host. These checks do not establish WAN
transport, mail, hardware power-cut recovery or full-machine disaster recovery.

The source upgrade helper takes the same maintenance lock and refuses a pending
DNS checkpoint before swapping application files. Its check-only mode remains
read-only.

## Optional mail profile

After upgrading the marked disposable guest, prepare a root-owned private test
certificate covering `mail.example.test` and its root-only key under
`/root/vectorcp-mail-test-tls/`. Install the optional profile with loopback
listeners, then run (from the extracted source):

```sh
sudo bash deploy/mail-install.sh --hostname mail.example.test \
  --cert /root/vectorcp-mail-test-tls/cert.pem \
  --key /root/vectorcp-mail-test-tls/key.pem --storage-mb 512 --apply
sudo env PYTHONPATH=/opt/vectorcp python3 tests/acceptance_mail_linux.py --apply
```

The harness creates two additional isolated customers and three synthetic
mailboxes. Its private resume fixture and safe result are under
`/var/lib/vectorcp/mail-acceptance/`. Eight native groups cover TLS, relay/sender
denials, queue/LMTP/IMAP delivery, cross-mailbox and website-UID denials, quota
enforcement, revocation and persisted-checkpoint recovery with retained messages.
SELinux remains enforcing. It sends no external messages and changes no DNS.
This is loopback/private-certificate evidence, not WAN delivery or full mail DR.
See [MAIL_HOSTING.md](MAIL_HOSTING.md) for boundaries and installation recovery.

For the mail reboot fence, complete delivery acceptance first, then run:

```sh
sudo env PYTHONPATH=/opt/vectorcp python3 tests/acceptance_mail_boot_linux.py --apply --prepare
# Restart ONLY this disposable guest; leave the private checkpoint intact.
sudo env PYTHONPATH=/opt/vectorcp python3 tests/acceptance_mail_boot_linux.py --apply --verify
```

The separate boot result records four checks. The reviewed run deliberately
terminated/restarted the VM process, verified unchanged startup-gate hashes,
blocked automatic and explicit native startup while pending, preserved real
messages and committed records, then recovered through the owner API. Native
SMTP/IMAP acceptance passed again after recovery. This is a virtual-machine
process crash, not a physical host power-loss test.
