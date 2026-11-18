# Website redirects and error pages

Current development source 0.4.3; not part of the immutable 0.4.2 download.

Open **Websites & domains → Routing** beside a website. The owner, its customer,
and that customer's delegated reseller can inspect its settings. Saving requires
an active website, an authenticated account, the current settings revision and
the session's CSRF token. Website suspension overrides customer routing; activate
the site before changing it. Locked accounts and unrelated tenants are refused.

## Redirects

Each website supports up to 20 rules with status 301, 302, 307 or 308. An exact
path matches one location. A folder prefix ends with `/` and matches that folder
and its descendants; `/` covers the website. Exact paths take priority over
prefixes, then the longest matching prefix wins. The ACME challenge location
remains reserved for certificate validation.

For example, `/old/` → `https://example.net/new/` with **Keep the remaining folder
path** redirects `/old/image.png` to `https://example.net/new/image.png`.
**Keep query parameters** appends the original query; an existing destination
query uses `&`. Keeping a remaining path requires a prefix rule and a destination
ending with `/` without its own query. Turning either option off drops that part.

Sources use plain ASCII paths without hidden components, query strings or
regular expressions. Destinations are absolute HTTP/HTTPS URLs using public
domain names. Credentials, fragments, literal configuration characters, malformed
percent escapes and encoded control characters are refused. The agent does not
fetch a redirect destination. Duplicate rules, direct loops and detectable
same-site cycles are rejected; it cannot inspect another server's redirect chain.

Remaining paths are taken from the raw request URI, preserving percent encoding
without inserting decoded header controls. They are retained for canonical
source prefixes. If a source prefix is written in an alternate encoded or
normalized form, the destination base may be used without a remaining path.
Use canonical URLs for folder redirects. There is no arbitrary rewrite language,
alias-domain certificate management or redirect log viewer in this workflow.

## HTTPS preference

Existing websites default to redirecting HTTP to HTTPS after a domain certificate
is enabled. Clearing the checkbox serves both HTTP and HTTPS; it keeps the
certificate and renewal configuration. This preference does not rewrite an
application's settings. An application such as WordPress can continue redirecting
visitors itself. With the preference on, HTTP first redirects to this domain's
HTTPS URL; custom rules are then evaluated there.

## Error pages

Create a nonempty `.html` or `.htm` file up to 256 KB with the file manager, then
enter its website-relative path beside an error status. Supported statuses are
400, 401, 403, 404, 405, 410, 429, 500, 502, 503 and 504. Blank fields restore
the server default. Asset links should be absolute paths within the website.

The backend opens only a regular file below the selected website, with directory
and file symlink checks. Nginx serves it through an internal static location with
symlink protection and preserves the original HTTP status. A later missing,
unreadable or symlinked file falls back to that status. These locations never
execute PHP. HTML content can be edited afterward through the normal file manager
and remains ordinary website storage; it is not duplicated outside the quota.
Application-generated errors that an application handles itself are unchanged.

Suspended sites ignore customer redirects/error pages and return HTTP 503. The
default suspension page identifies the suspended state without exposing account
details. ACME validation stays available. The initial welcome page and normal
Nginx defaults remain available for websites without custom settings.

## Failure and recovery behavior

Settings are stored in an additive `site_routing` table. An old four-column
session table and existing account/site data remain compatible. Stale forms are
refused instead of replacing newer edits. Saving writes only this site's virtual
host, validates Nginx, and reloads it. A test or reload failure restores the prior
virtual-host bytes and rolls back the pending settings transaction. This follows
the existing panel's configuration recovery model, not a durable two-phase commit
across process crashes. Server-wide power-loss recovery remains separate work.

## Repeatable verification

```bash
python -m unittest discover -s tests -p test_routing.py -v
python -m unittest discover -s tests -p test_http.py -v
node --check vectorcp/static/routing-form.js
```

On an already marked disposable Linux acceptance guest only:

```bash
python3 tests/acceptance_routing_linux.py --allow-disposable-host
```

The opt-in driver starts its own Nginx on loopback 18080/18443 with an isolated
configuration and self-signed test certificate. It checks redirects, query/path
handling, custom 403/404/500 responses, missing/symlinked files, header controls,
HTTPS switching, suspension and an unrelated virtual host. It stops that process
and removes its fixtures afterward. It does not alter the installed web service
or establish public TLS trust or whole-installation acceptance.
