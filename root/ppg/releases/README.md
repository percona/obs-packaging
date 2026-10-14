See [root/README.md](../../README.md) for documentation on the releases structure and instructions on cutting a release.

The `ppg:releases:*` projects described by this tree are never populated straight from
staging: opening a release PR copies staging into a per-PR pre-release project
(`obs-release-pr.yml`, `sync prerelease`), and merging it copies that pre-release into the
release project (`obs-release.yml`, `sync release --from`).
