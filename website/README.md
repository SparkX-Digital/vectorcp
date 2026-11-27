# VectorCP public website

The original static website at https://vectorcp.net/ shares the panel's MIT
license. It uses Python's standard library to build self-hosted HTML, CSS,
JavaScript, documentation search data and version history. It needs no database,
external fonts, analytics or runtime JavaScript framework.

The shared header/footer and product pages use reviewed HTML templates under
`templates/`, the common design is `assets/site.css`, and audience copy is in
`solutions.json`. Keep product claims aligned with the current capability catalog.
Native disclosure menus and FAQ controls work without JavaScript; task tabs and
documentation search add progressive enhancement. Keep all task panels available
in the no-script view.

Product images in `source-material/panel-045-*.jpg` are actual local development
screenshots with synthetic data. They do not show production customers or establish
production readiness. The website's self-hosted typefaces retain their original
licenses under `assets/fonts/`; see that directory's provenance notes. Preserve
those notices when redistributing the website.

## Build and verify

From the repository root, create the source archive outside the checkout, then
build into a separate empty output directory:

```sh
python3 deploy/package.py --output /tmp/VectorCP-0.4.5-development-source.zip
python3 website/build.py --panel-source . \
  --development-archive /tmp/VectorCP-0.4.5-development-source.zip \
  --output /tmp/vectorcp-website
python3 website/check.py /tmp/vectorcp-website
node --check /tmp/vectorcp-website/assets/site.js
```

The build copies the previously frozen public 0.4.2 and dated 0.4.3 mail
snapshot and 0.4.4 source from `source-material`, with their original checksums. The panel image
is a captured development interface. New downloads must have unique names;
never replace an existing public archive with different bytes.

## Publish

Retain a private recovery archive first. Stage ZIPs outside the public document
root and deploy only built public files. Preserve the host's `.htaccess`,
`.user.ini`, `php.ini` and `.well-known`. `website-directives.htaccess` is a
reference for owner review, not a file to deploy automatically. Use fresh publication
timestamps for changing deployed files; deterministic source-archive timestamps
must not be used as live HTML validators. Keep HTML and search JSON revalidation
separate from long-lived content-versioned asset caching.

Serve HTML and search JSON with
`Cache-Control: no-cache, max-age=0, must-revalidate, no-transform`.
The `no-transform` directive keeps delivery intermediaries from rewriting example
email addresses in copyable commands or injecting a decoding-script dependency.
For example, [Cloudflare documents this behavior](https://developers.cloudflare.com/waf/tools/scrape-shield/email-address-obfuscation/).
Check the actual public response headers and raw example text after deployment;
origin file checks alone do not verify delivery behavior. Keep the existing
host-generated settings intact when adding the narrow policy. See the
[website maintenance history](CHANGELOG.md).

Verify local links, all deployed file hashes, phone/tablet/desktop layouts,
search, mobile navigation, release expansion, keyboard use and download
checksums. Keep no-JavaScript documentation links available and test failure
messages. Monitor the deployed website before declaring the update complete.

## Version history

`CHANGELOG.md` is the shared source for both documentation history and the
public `/changelog/` page. Every published development entry has a source
version, actual date and clear status. Development snapshots are not stable
production releases; historic snapshot labels do not create Git tags.
