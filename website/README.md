# VectorCP public website

The original static website at https://vectorcp.net/ shares the panel's MIT
license. It uses Python's standard library to build self-hosted HTML, CSS,
JavaScript, documentation search data and version history. It needs no database,
external fonts, analytics or runtime JavaScript framework.

## Build and verify

From the repository root, create the source archive outside the checkout, then
build into a separate empty output directory:

```sh
python3 deploy/package.py --output /tmp/VectorCP-0.4.4-development-source.zip
python3 website/build.py --panel-source . \
  --development-archive /tmp/VectorCP-0.4.4-development-source.zip \
  --output /tmp/vectorcp-website
python3 website/check.py /tmp/vectorcp-website
node --check /tmp/vectorcp-website/assets/site.js
```

The build copies the previously frozen public 0.4.2 and dated 0.4.3 mail
snapshot from `source-material`, with their original checksums. The panel image
is a captured development interface. New downloads must have unique names;
never replace an existing public archive with different bytes.

## Publish

Retain a private recovery archive first. Stage ZIPs outside the public document
root and deploy only built public files. Preserve the host's `.htaccess`,
`.user.ini`, `php.ini` and `.well-known`. `website-directives.htaccess` is a
reference for owner review, not a file to deploy automatically.

Verify local links, all deployed file hashes, phone/tablet/desktop layouts,
search, mobile navigation, release expansion, keyboard use and download
checksums. Keep no-JavaScript documentation links available and test failure
messages. Monitor the deployed website before declaring the update complete.

## Version history

`CHANGELOG.md` is the shared source for both documentation history and the
public `/changelog/` page. Every published development entry has a source
version, actual date and clear status. Development snapshots are not stable
production releases; historic snapshot labels do not create Git tags.
