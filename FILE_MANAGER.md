# Website file manager

The file manager operates inside the selected website's `public` directory.
Owners and resellers can manage only sites allowed by their existing account
scope. Customers cannot name another account's storage. Every change requires
the current session and CSRF verification, and pauses while a hosting job is
using that customer volume.

**Unreleased additions:** folder copying, batch selection, recoverable trash,
hidden-file controls, permission editing and ZIP creation/extraction. These are
in the current source; the immutable 0.4.2 download contains the earlier subset.

## Transfers

Upload and download regular files up to **32 MiB**, including binary files.
Upload names use the same ASCII name rules as the editor: start with a letter
or number, then letters, numbers, spaces, periods, dashes or underscores; at
most 200 characters per component and 512 per relative path. Enable **Show hidden
files** to use dot names such as `.htaccess` or `.config`. Leading/trailing
whitespace, reserved `.vectorcp-` names, absolute paths, backslashes, parent
references and symbolic links are refused. Unsupported external filenames are
excluded from listings instead of being silently mapped to another file.

Uploads use sequential chunks of at most 256 KiB. A private, root-owned staging
directory holds incomplete data, outside the served website and customer
process namespace. The server checks the declared size and SHA-256 before
publishing a file atomically. A destination that appears during the transfer
is preserved. Uploads never replace an existing file.

The browser's Upload button resumes its current transfer after a failed request
when the same file remains selected. Closing the dialog cancels its staging
record. An interrupted agent can resume from the last committed offset.
Staging expires after one hour and is reclaimed on agent startup or the next
upload. There are at most eight active uploads and 64 MiB of declared staging
space server-wide. Pending reservations count against that customer's new
uploads; publication rechecks actual file usage and entry limits.

Completion receipts make a repeated finish request safe after a lost response.
They expire with the upload or when the server retains its newest 2,048 receipts.
A cancelled or expired receipt does not remove a published file.

Downloads use a revision tied to the source metadata and 256 KiB chunks. The
browser checks the complete SHA-256 before saving the file. A changed source
requires a fresh download. Browser verification requires HTTPS or a loopback
SSH tunnel. No transfer endpoint accepts an operating-system destination path.

## Actions and search

The **Actions** control beside an entry provides:

- Text editing for UTF-8 files up to 256 KiB, retaining the editor's existing
  content-revision check.
- Verified binary download and regular-file copy, up to 32 MiB.
- Move or rename a regular file or folder within the same website. A folder
  move includes its contents. The destination parent must already exist.
- Copy folders including their hidden contents: at most 32 MiB of file content,
  1,000 entries and 32 nested levels. A private stage on the customer's filesystem
  is published only after source-revision, quota and entry checks pass. Interrupted
  copy stages are reclaimed on the next folder-copy request for that site.
- Move a regular file or bounded folder into recoverable **Trash**, then restore
  to the original or another relative path without replacing existing items.
- Permanent removal of a regular file or empty directory. The interface
  requires typing `REMOVE`; a nonempty directory is refused. Use Trash first
  when you need recovery or permanent removal of a bounded folder tree.
- Inspect and change permissions using the supported safe modes. The agent
  refuses shared write and special privilege bits, and can normalize ownership
  only to this website's customer. It accepts no operating-system UID or GID.
  Restrictive permissions can stop a website from reading a file. Existing
  editor/upload defaults apply to new files. Editing an existing file preserves
  its read/execute restrictions and strips shared-write/special-privilege bits.

Select up to 20 entries for **Selected…** copy, move or permanent removal. Each
item is independently checked and reports its result. Completed items stay
completed when another item fails; batch file changes are not a transaction.
Selecting the same item twice, or a parent and its descendant together, is refused.

Copies and moves atomically refuse existing destinations, including a competing
website write. Entry revisions reject items changed since the list was loaded.
These checks do not lock external application writers; take a backup before
changing application-managed files. Temporary copies have deterministic cleanup
on ordinary failures, and full storage cannot truncate an existing destination.
Operations use directory descriptors and refuse symbolic links and special files.
Copied/uploaded files receive the same customer identity and restrictive hosted
permissions as files created in the text editor.

Filename search is case insensitive and stays within one website. The hidden-file
preference applies to browsing, search, editing and transfers; links are always
excluded. Search scans at most 12,000 entries and returns at
most 200 matches. The interface reports when this limit is reached. Folder
browsing remains limited to 1,000 entries per listing.

## Recoverable trash

Trash is outside the served `public` tree, in a root-only directory on the same
customer filesystem. A durable metadata receipt is written before moving the
payload. The filesystem move is the commit point; recovery does not depend on a
second database transaction. The payload and its metadata count against file
storage and entry allowances. Restoring an item does not consume another full
copy of its contents. Static exports and website backups do not include trash.

Each website may retain up to 100 entries, with a 32 MiB / 1,000-entry limit on
each removed tree. Nothing is automatically expired. Restore refuses an existing
destination and leaves the trash item intact on conflict. Permanent purge is a
separate confirmed action and cannot be undone. Interrupted receipts without a
payload are reclaimed when listing trash; existing public files are preserved.
An interrupted purge can leave a smaller payload available for inspection/retry.

## ZIP archives

Create a standard ZIP from a regular file or bounded folder, including hidden
contents, or extract a ZIP into a **new** website-relative folder. Sources remain
unchanged and existing destinations are preserved. Both operations stage outside
the public tree on the customer's filesystem, normalize customer ownership and
publish only after checks succeed. The next archive request reclaims abandoned
private archive stages for that site.

This profile supports unencrypted stored/deflated ZIP entries, at most 32 MiB of
ZIP input/output and total uncompressed file content, 1,000 entries including
implicit folders, and 32 nested levels. The central directory is bounded before
the ZIP parser allocates entry records. Multi-disk and ZIP64 end-record containers
are refused. Other archive formats and encrypted archives remain separate work.

Extraction refuses absolute/parent paths, backslashes, whitespace aliases,
reserved names, NUL names, duplicates, file-as-folder conflicts, links and special
files. CRC failure, quota exhaustion and source changes remove the private stage
without publishing a partially extracted folder. Nested ZIP files stay ordinary
files; extraction is not recursive. Archive permission/ownership metadata is
replaced by the panel's safe customer defaults. The format is described by the
[ZIP specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT);
the implementation uses Python's standard `zipfile` module.

FTP/SFTP accounts, image editing and recovery of selected files from saved backups
remain separate catalog items.

## Internal operations

These operations use the existing same-origin JSON `/api` envelope, session
cookie and mutation CSRF header. They are not long-lived public API tokens.

| Operation | Required data in addition to `site_id` | Result |
| --- | --- | --- |
| `files.upload.start` | `path`, `bytes`, lowercase `sha256` | `id`, `received`, `chunk_bytes` |
| `files.upload.chunk` | `id`, `offset`, `base64` | Committed `received` offset |
| `files.upload.status` | `id` | Path, sizes, chunk limit, completion state |
| `files.upload.finish` | `id` | Verified `sha256` and `ok` |
| `files.upload.cancel` | `id` | `ok`; staging removed |
| `files.describe` | `path` | Size, metadata `revision`, `sha256`, chunk limit |
| `files.chunk` | `path`, metadata `revision`, `offset` | Base64 data, `next`, total size |
| `files.copy` / `files.move` | `path`, metadata `revision`, `destination` | `ok` |
| `files.remove` | `path`, metadata `revision` | `ok` |
| `files.search` | `query` | Scoped matches and `limited` flag |
| `files.permissions` | `path` | Mode, revision, safe choices and account owner |
| `files.chmod` | `path`, metadata `revision`, `mode` | Current mode and revision |
| `files.batch` | `items` of path/revision, `operation`, destination folder when copying/moving | Per-item outcomes |
| `files.trash` | `path`, metadata `revision` | Recoverable entry `id` |
| `files.trash.list` | — | Scoped retained entries |
| `files.trash.restore` | `id`, optional `destination` | `ok`; refuses conflicts |
| `files.trash.purge` | `id` | `ok`; irreversible |
| `files.archive.create` / `files.archive.extract` | `path`, metadata `revision`, `destination` | `ok`; bounded ZIP profile |

File operations accept the Boolean `show_hidden` preference. It controls name
visibility and explicit hidden-path access, not another tenant's authorization.

Upload records belong to their initiating actor as well as the selected site.
Even another manager of the site cannot claim that actor's staging record.
Read-only description, chunk, status and search calls require authentication;
all other operations also require CSRF verification. Mutations record the
actor and website-relative target in the activity history without file content
or credentials.
