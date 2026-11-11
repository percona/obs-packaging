See [root/README.md](../../README.md) for documentation on the releases structure and instructions on cutting a release.

The `ppg:releases:*` projects described by this tree are never populated straight from
staging: opening a release PR and adding the `obs-sync` label (a hand-opened PR needs it too; retry is remove-then-add) copies staging into a per-PR pre-release project
(`obs-release-pr.yml`, `sync prerelease`), and merging it copies that pre-release into the
release project (`obs-release.yml`, `sync release --from`).

The release branch itself can be cut in CI: `gh workflow run obs-release-cut.yml -f units="ppg:staging:18" -f branch=release/18.6-2`
(`obs-release-cut.yml`) runs `project release --yes` for every unit and force-pushes one commit on top of
`main` to the branch. It does not open the PR; open it and add `obs-sync` yourself.
