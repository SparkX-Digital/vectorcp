# Private database administration

Unreleased 0.4.3 adds **Databases** to the owner, reseller and customer workspace.
An isolated website still has one generated MariaDB database and its protected
application user. MariaDB listens on the customer's Unix socket, without TCP.
These tools do not provide a server-wide SQL console or a separate admin login.

- Inspect up to 200 tables and estimated table/index storage. Estimates come from
  MariaDB's information schema and need not equal exact filesystem use or row counts.
- Browse 25 rows at a time, up to 64 columns, 512 bytes per displayed cell and an
  offset of 10,000. NULL remains distinguishable. Display is read-only, escapes
  HTML, and replaces invalid UTF-8. Concurrent application writes can change row order.
- Create up to eight additional local users per website with generated logins,
  a descriptive label and individually selected database permissions. There are
  no global, FILE, SUPER, user-management or grant-option privileges. Existing
  database connections are disconnected after edits, rotation or removal.
- Passwords are shown once on creation/rotation and never stored in the control
  database or audit messages. The existing application credential remains in its
  private root-managed file; additional-user controls cannot alter that identity.
- Export a SQL file up to 1 MB, with a verified download hash. Full backups support
  database dumps up to 64 MB. Export rejects larger output rather than truncating it.
- Import a nonempty SQL file up to 1 MB after typing the destination database name.
  PHP is paused and the previous database is dumped first. SQL runs as that site's
  application identity, with client shell commands and LOCAL file loading disabled.
  A failed import restores the previous dump. The protected application password
  is reasserted and its outstanding connections are closed before PHP resumes.
  Queries have process/time/output bounds; this is not an arbitrary root SQL endpoint.

Database GRANT names escape wildcard characters. SQL import verifies the protected
application user has the expected grants and narrows a legacy unescaped schema
grant before executing customer SQL. Unexpected global/foreign grants require
administrator review. The existing password and application identity are retained.

SQL must target the selected schema. Dumps with server configuration, CREATE USER,
foreign definers or cross-database names may fail. This does not translate arbitrary
application configuration or make vendor-specific dumps portable. Server crashes,
failed rollback, full customer disks and all possible SQL workloads still need a
broader recovery audit. Keep an independent full backup before importing.

Every operation authenticates in the privileged agent and checks account hierarchy,
site ownership, the database plan feature and isolation allocation. Writes require
CSRF. Busy customer jobs block conflicting work. Import is a durable serialized job;
its result appears in Background jobs, including failure after a restart.

Tests: `tests/test_databases.py` covers boundary/failure contracts;
`tests/acceptance_data_linux.py` exercises actual MariaDB grants, SQL import,
rollback, export and table browsing in a marked disposable AlmaLinux guest.

Implementation references: [MariaDB GRANT](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant) and [MariaDB client binary mode](https://mariadb.com/docs/server/clients-and-utilities/mariadb-client/mariadb-command-line-client).
