# Maintaining the sanitized export

This repository is separate from the installed local skill. Do not replace a
working device deployment, scheduler or Gateway configuration as a side effect
of publishing source changes.

When syncing a future fix:

1. Copy only reviewed source files, not the installed skill's `.state/`, results,
   model caches, screenshots, environment files or dependency directories.
2. Preserve the configurable device, asset and launcher paths in this export.
   Include the shared recognizer and ADB helpers: a source-only copy of the main
   skill without those modules is incomplete.
3. Keep resource paths relative. Keep Sprite, Android drawable and screenshot
   template provenance categories distinct; do not publish account screenshots
   or the original source-machine paths in provenance JSON.
4. Retest changed code in an isolated environment. Private corpus tests may be
   used locally, but do not move their account-dependent expectations into the
   public tests. Record the tested exported source hashes locally before commit.
5. Review the exact staged file list, run a secret scan and a private-identifier
   scan, and inspect Git metadata. Use a GitHub noreply author address if the
   ordinary Git identity contains a personal email.
6. Verify the published branch SHA and complete remote tree against the intended
   commit/file set. Review every future commit before pushing: removing a secret
   in a later commit does not remove it from public history.

The ignore file is a convenience, not a privacy guarantee. Do not use force-add
to bypass exclusions for runtime data.
