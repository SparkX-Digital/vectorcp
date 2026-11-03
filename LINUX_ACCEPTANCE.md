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
maintenance with a local lock. A crash can leave
`/run/vectorcp-profile-maintenance`; inspect the interrupted installer and active
jobs before removing that marker and retrying. The marker blocks new hosting
jobs in the current agent. A normal helper exit removes it automatically.

This acceptance does not prove trusted public certificate issue/renewal, public
DNS delegation, email delivery, an older-layout migration, multi-platform
installation, independent disaster recovery or a production security audit.
Record the tested source, OS image, versions and actual results in
[VERIFICATION.md](VERIFICATION.md).
