# Contributing to VectorCP

VectorCP is an MIT-licensed, independently written hosting control panel. Its
product target is a complete open-source alternative to cPanel/WHM with the
feature coverage documented for BHPanel. The current release is early software;
check `FEATURES.md` before starting work or choosing it for hosting customers.

## Work locally

Use Python 3.9+ on Unix. The application uses the Python standard library and
plain JavaScript/CSS. Linux integrations require a dedicated AlmaLinux 9 test VM.

```sh
python3 dev.py --data /absolute/path/outside/the/source/tree
python3 -m unittest discover -s tests -v
```

Runtime state contains credentials. Keep it outside this repository. Never add
SSH keys, session tokens, production databases, customer files or private logs.
Use generated example data in tests, and redact diagnostic output.

## Changes and reviews

Explain the problem, resulting behavior, supported roles, and relevant checks.
For a service integration, include a repeatable installation procedure, syntax
validation, rollback, resource limits, and at least one real Linux acceptance
check. Mark tests that require root or a VM clearly. Use temporary directories
for ordinary tests; never make tests discover or modify a live installation.

The privileged agent must authorize every request itself. New operations belong
in a narrow allowlist, with strict input types and target ownership checks.
Do not accept arbitrary commands, paths, unit names, configuration fragments or
user IDs as authority from the web frontend. Run customer code as the customer.

A visible screen does not complete a feature. Update `FEATURES.md` with what
works, what was exercised and what remains. Test failure and isolation behavior
as well as the successful path. Accessibility and narrow-screen use matter too.

## Releases

Set the release version in `veyra/__init__.py`; core imports it. Update
`CHANGELOG.md`, installation instructions and `VERIFICATION.md`. A source archive
must contain the license, templates, fixed task helpers, renewal hook and timer,
tests and documentation, while excluding runtime data and secrets. Publish an
archive SHA-256. Signed distribution and automated rollback remain planned;
do not represent an unsigned archive as a verified update channel.

Contributions must be original or carry compatible licensing and attribution.
Bundled service engines and customer applications retain their own licenses.
