# Website file manager

The file manager operates inside the selected website's `public` directory.
Owners and resellers can manage only sites allowed by their existing account
scope. Customers cannot name another account's storage. Every change requires
the current session and CSRF verification, and pauses while a hosting job is
using that customer volume.

## Transfers

Upload and download regular files up to **32 MiB**, including binary files.
Upload names use the same ASCII name rules as the editor: start with a letter
or number, then letters, numbers, spaces, periods, dashes or underscores; at
most 200 characters per component and 512 per relative path. Hidden names,
absolute paths, backslashes, parent references and symbolic links are refused.

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
- Permanent removal of a regular file or empty directory. The interface
  requires typing `REMOVE`; a nonempty directory is refused. This is not trash
  or undo.

Copies and moves atomically refuse existing destinations, including a competing
website write. Entry revisions reject items changed since the list was loaded.
These checks do not lock external application writers; take a backup before
changing application-managed files. Temporary copies have deterministic cleanup
on ordinary failures, and full storage cannot truncate an existing destination.
Operations use directory descriptors and refuse symbolic links and special files.
Copied/uploaded files receive the same customer identity and restrictive hosted
permissions as files created in the text editor.

Filename search is case insensitive and stays within one website. It excludes
hidden entries and symbolic links, scans at most 12,000 entries and returns at
most 200 matches. The interface reports when this limit is reached. Folder
browsing remains limited to 1,000 entries per listing.

Recursive copying, batch selection, trash/undo, hidden-file controls, archive
extraction, permission editing and FTP/SFTP accounts remain separate catalog
items. An Actions dialog does not imply those workflows are implemented.

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

Upload records belong to their initiating actor as well as the selected site.
Even another manager of the site cannot claim that actor's staging record.
Read-only description, chunk, status and search calls require authentication;
all other operations also require CSRF verification. Mutations record the
actor and website-relative target in the activity history without file content
or credentials.
