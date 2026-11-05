# Account and sign-in controls

These changes are in the **Unreleased** working tree. The immutable 0.4.2
download does not include them. They remain development capabilities, without
an independent security audit or a production-support promise.

## Sessions

Open **Account & security** to see your own active sessions, their creation,
last activity and expiry times, and the device description supplied by each
browser. Device descriptions are untrusted display text, not verified identity
or location. Forwarded network headers do not establish device identity.

Sign out one session, the current session, or every other session. Revocation
takes effect in the agent on the next request. Session authentication tokens and
CSRF secrets are never returned in this inventory. Session IDs are identifiers,
not credentials. Up to 20 sessions may remain active; signing in on another
device revokes the oldest. Each session expires after eight hours. Last activity
is refreshed at most once a minute. Managers cannot inspect another account's
device list through this self-service endpoint.

The original session table remains compatible with the previous application;
new device metadata lives in a separate table. Upgrading preserves existing
sessions. Reverting to software predating two-factor support would remove its
enforcement: do not manually downgrade an installation that uses these controls.

## Authenticator and recovery codes

Enable the authenticator from **Account & security**, verify your current
password, then enter the setup key in a time-based authenticator app. Use issuer
`VectorCP`, your panel username, six digits, SHA-1 and a 30-second period.
Confirm a current code before enrollment becomes active. An unconfirmed setup
expires after ten minutes and belongs only to its initiating session.

The implementation follows [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238).
Its tests use the published SHA-1, SHA-256 and SHA-512 vectors. The product uses
SHA-1 for authenticator interoperability. The agent accepts the current step and
one adjacent step in either direction, and records the last accepted step to
refuse replay. Keep the server clock synchronized. After using an authenticator
code, wait for the next code before another protected action.

Enabling the authenticator signs out other sessions and displays eight recovery
codes once. Store them privately, separately from this server. Each random
128-bit code works once, together with your password. The database stores only
SHA-256 digests of recovery codes. Replacing codes invalidates the old set.
Disabling the authenticator or replacing recovery codes requires your password
and an unused authenticator or recovery code, and signs out other sessions.

Sign-in checks password and the second factor before issuing a session cookie.
A correct password without a second-factor code returns only an instruction to
show the code field. It creates no provisional authenticated session. Invalid
codes, enrollment confirmation and credential changes are throttled durably;
five failed attempts cause a 15-minute block. A restart does not reset the block.

Authenticator setup keys are stored in the agent's root-only state database;
they are not encrypted at rest. Protect the state directory, SQLite backups and
server root access. The web service cannot open that database. Credentials,
setup keys and recovery-code contents are excluded from audit messages. The
interface clears credential and recovery dialogs when they close. Recovery
email delivery, lost-password self-service, passkeys and external identity
providers are separate unfinished capabilities.

## Passwords and contact details

New passwords use 15–256 characters, reject a small built-in list of predictable
values and extremely repetitive strings, and use the existing salted
PBKDF2-SHA256 format. Existing shorter passwords can still sign in and change to
the new policy. This is an offline policy; it does not query a breach service or
claim comprehensive detection of weak passwords. Passphrases are supported.

Changing your password requires the current password and, when enabled, an
unused second-factor code. All sessions, including the current one, are revoked.
Sign in again with the new password. Your username and second-factor enrollment
remain unchanged.

Owners and resellers can reset passwords only for accounts in their management
scope. The manager verifies their own credentials and sets a temporary password.
This revokes the target's sessions and requires the target to choose a different
password before using hosting tools. The agent enforces this restriction for
direct requests as well as the interface. Resetting a password does not remove
the target's authenticator. Resellers cannot reset an owner-locked account, and
this workflow cannot reset the server owner's credentials.

Edit your own name and optional contact address after credential verification.
Managers can edit these fields for permitted accounts. Contact addresses are
administrative records, not verified addresses or a working notification service.

## Account management

Account search runs in the agent and supports name, username, contact address,
account type and access state. Results are paginated. Details include the plan,
file usage, websites and active-session count, without passwords or session
credentials. A reseller's filters cannot reveal unrelated customers.

Select up to 100 accounts for panel access changes or explicit plan assignment.
The entire selection is checked for scope and owner locks. A later failure rolls
back earlier assignments and reservations in that request. Access changes revoke
the selected accounts' sessions and those of their delegated customers. Website
suspension is separate: locking panel access does not stop hosted websites.
Bulk website suspension, termination and storage resizing remain unfinished.
