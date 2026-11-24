# Releasing VectorCP

The changelog is the human-readable product history. Git commits are the source
history. A documentation update or planned feature is not a release by itself.

## During development

Keep future work in the roadmap. Record verified user-visible changes in a
version-and-date entry in `CHANGELOG.md`, grouped as
Added, Changed, Fixed, Security, Deprecated or Removed when useful. Describe the
resulting behavior and installation implications. Track future work in the
feature catalog and roadmap rather than as a shipped addition.

Use `## <version> — <day Month year> · Development snapshot` for a published
development snapshot and the actual publication date. If several earlier builds
shared an unreleased source version, use a snapshot identifier such as
`0.4.3-dev.20261123`, with the verified merge date. This records history without
creating retroactive tags or claiming a stable release. Preserve previous dates,
archive bytes and checksums. Leave **Unreleased** for changes not yet published.

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
