# Releasing VectorCP

The changelog is the human-readable product history. Git commits are the source
history. A documentation update or planned feature is not a release by itself.

## During development

Add user-visible changes under **Unreleased** in `CHANGELOG.md`, grouped as
Added, Changed, Fixed, Security, Deprecated or Removed when useful. Describe the
resulting behavior and installation implications. Track future work in the
feature catalog and roadmap rather than as a shipped addition.

## Prepare a version

1. Set the single version in `vectorcp/__init__.py`. Use a minor version for
   incompatible changes during 0.x development; explain migration requirements.
2. Move verified changes into a dated version entry. Preserve earlier dates
   and factual behavior. Record validation and unresolved limits in
   `VERIFICATION.md`; never imply an independent audit has occurred.
3. Run all tests, JavaScript/shell checks and the deterministic packager.
   Exercise installation, upgrade and recovery for changed service layouts.
4. Review the archive for credentials, runtime databases, private deployment
   files and unrelated material. Verify every entry matches the source.
5. Commit the final source, then wait for checks on that exact commit.
6. Create an annotated `v<version>` tag on the reviewed commit and a matching
   GitHub release. Attach the source archive and SHA-256 file. Verify archive
   content against the tagged tree.
7. Publish the same immutable archive and checksum on the project website.

## Rules

- Never replace a version's archive with different bytes. Publish a new version.
- Never tag source that differs from its archive or contains uncommitted changes.
- SHA-256 detects changed bytes; it is not signing. Do not call releases signed
  until signing and verification are implemented.
- Development snapshots must identify pending installation and migration gates.
- Retain private recovery copies before deployment. Ordinary releases and
  branding changes do not rewrite public Git history.
