# Labs rehearsal runbook: two-hop release flow

Rehearse the whole flow on labs with a throwaway release id before the first real
release. Reference: `docs/PERCONA_OBS_TOOL.md` "Releasing packages" and
`docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` §4-§5.

Conventions: `<minor>` is the current PG 18 minor (for example `6`), the throwaway id is
`18.<minor>-99` (never collides with a real counter), the tag is `ppg/18.<minor>-99`, `N` is
the rehearsal PR number, `<instance>` is an `OBS_INSTANCES` name, `<web>` is the OBS web URL.
Pre-release project URL: `<web>/project/show/<pr_rootprj>:pr-N:ppg:releases:18`.

Never let the rehearsal PR leave a state that ships: finish with the Cleanup phase.

## Preconditions

- [ ] `OBS_INSTANCES` repo variable lists the labs instance with `name`, `apiurl`, `rootprj` and `pr_rootprj`: `gh variable get OBS_INSTANCES | jq '.[] | {name, apiurl, rootprj, pr_rootprj}'`. Expect: every entry has all four keys; `pr_rootprj` differs from `rootprj`.
- [ ] Per-instance secrets exist: `gh secret list | grep OBS_PASSWORD_` and `gh variable list | grep -E 'OBS_WEB_URL|OBS_USER|JENKINS'`. Expect: one `OBS_PASSWORD_<instance>` per instance, `OBS_WEB_URL` set, and the Jenkins variables/secrets the QA lanes use are present.
- [ ] Local `gh` works and tags are fetched: `gh auth status && git fetch percona --tags && git tag -l 'ppg/18.*' | tail -3`. Expect: logged in with repo and workflow scope; latest real `ppg/18.*` tag listed.
- [ ] Staging is green on labs and main is synced: `venv/bin/python -m percona_obs -P labs build status ppg:staging:18` and open the latest `sync-main` run in the Actions tab. Expect: no failed/broken packages; the last sync-main run has successful sync jobs.
- [ ] No other open release PR for major 18: `gh pr list --state open --search 'releases/18 in:files'`. Expect: none (one in-flight release PR per major).

## Cut

- [ ] From a clean branch off `percona/main`: `git switch -c rehearsal-18-99 percona/main && venv/bin/python -m percona_obs -P labs project release ppg:staging:18 --release-id 18.<minor>-99`. Expect: exits 0; one local commit; `root/ppg/releases/18/release.yaml` has a new `18.<minor>-99` entry with `source_commit` set to the synced main SHA; `CHANGELOG.md` has a `[18.<minor>-99]` section; only files under `root/*/releases/` changed (`git show --stat HEAD`).
- [ ] Optional dry run of the staging-side checks: `venv/bin/python -m percona_obs -P labs sync release ppg:releases:18 --dry-run`. Expect: staging-side checks pass. Note `sync release --from --dry-run` only runs these staging-side checks; it does not exercise the pre-release copy.
- [ ] Push the branch to `percona` (not a fork) and open the PR: `git push percona rehearsal-18-99 && gh pr create --repo percona/obs-packaging --title 'REHEARSAL 18.<minor>-99 (do not ship)' --body 'Labs rehearsal'`. Expect: PR opens; note `N`.

## Populate

- [ ] Open the PR's Checks tab, workflow "OBS Release PR". Expect: job `Resolve release PR` green (release-only, no conflicting PR, non-empty), then one job `Populate pre-release (<instance>)` per instance, serialized per instance; `obs-pr-check` does not run the sync for this PR.
- [ ] Read the PR comment headed "## OBS Release PR — ✅ Pre-release populated (<instance>)" and download artifact `prerelease-report-<instance>` (`gh run download <run-id> -n prerelease-report-<instance>`). Expect: one comment per instance listing the pre-release projects (`ppg:releases:18` among them); the report lists no failed package.
- [ ] Open `<web>/project/show/<pr_rootprj>:pr-N:ppg:releases:18` and check the project description. Expect: project exists, binaries present for the staging package set, description ends with `source_commit: <sha>` equal to the entry in `release.yaml`.
- [ ] Watch the check runs named `Release / OBS QA / …` (caller job `Release`; lanes are prefixed `OBS QA / ppg:releases:18 / …`). Expect: they start only after every populate leg succeeded and run against the pre-release repos; a failed lane can be re-run from the PR UI.
- [ ] Known limitation, check the QA lane list. Expect: package-level lanes are absent because `EXPECTED_VERSIONS` is empty on release mirrors (no package directories); only project-level lanes run. Do not treat this as a failure.

## Fix loop

- [ ] Force the record check to fail: merge any trivial change under `root/ppg/staging/` through a normal PR into main and wait for its `sync-main` run to finish, then push the rehearsal PR unchanged (`git commit --amend --no-edit -s && git push percona rehearsal-18-99 --force-with-lease`). Expect: `Populate pre-release (<instance>)` fails before any freeze with "staging changed since the cut" and a staging-path diff; the OBS pre-release is untouched; QA does not start.
- [ ] Refresh the cut: `git fetch percona && git rebase percona/main && venv/bin/python -m percona_obs -P labs project release ppg:staging:18 --release-id 18.<minor>-99 && git push percona rehearsal-18-99 --force-with-lease`. Expect: the entry's `source_commit` and the changelog section are refreshed in place (still one `18.<minor>-99` entry); populate and QA go green.
- [ ] Repopulate without a push: `gh workflow run obs-release-pr.yml -f pr_number=N && gh run watch $(gh run list --workflow obs-release-pr.yml --limit 1 --json databaseId -q '.[0].databaseId')`. Expect: `Resolve release PR` and every `Populate pre-release (<instance>)` green; update in place (same pre-release project, idempotent); a fresh PR comment per instance.

## Merge

- [ ] Merge the rehearsal PR (squash or rebase, as the repo allows): `gh pr merge N --rebase`. Expect: PR merged; workflow "OBS PR Cleanup" job `Tag release and dispatch obs-release` runs.
- [ ] Check the tag and the single dispatch: `git fetch percona --tags && git tag -l 'ppg/18.<minor>-99'` and `gh run list --workflow obs-release.yml --limit 5`. Expect: tag `ppg/18.<minor>-99` exists at the merge commit; exactly one new `OBS Release` run (event `workflow_dispatch`) with inputs `pr_number=N` and the tag.
- [ ] Watch that run. Expect: `Validate inputs` green, `Release to OBS (<instance>)` green per instance, `Publish GitHub releases and delete the pre-release` green, `Delete the pre-release (<instance>)` green; the pre-release URL above now returns "project not found".
- [ ] Check the outputs: `gh release view ppg/18.<minor>-99` and `<web>/project/show/<rootprj>:ppg:releases:18`. Expect: GitHub release exists with the changelog section as notes; the release project holds the copied binaries (these are the throwaway binaries, see Cleanup).
- [ ] Check `sync-main`: `gh run list --workflow sync-main.yml --limit 3`. Expect: a `sync-main` run on the release-only merge push (not skipped), green; it does not tag or touch the released projects.

## Recovery

- [ ] Manual re-dispatch of hop 2 (a leg failed, or obs-pr-cleanup could not dispatch): `gh workflow run obs-release.yml --ref main -f pr_number=N -f tags="ppg/18.<minor>-99"`. Expect: the run is idempotent; legs re-copy from the intact pre-release, GitHub release is created or its notes updated, pre-release deleted at the end. A failed copy fails `Publish GitHub releases…` with an `::error::` and keeps the pre-release.
- [ ] Pre-release already deleted but the release must be redone: `gh workflow run obs-release-pr.yml -f pr_number=N`, wait for it to go green, then re-dispatch `obs-release.yml` as above. Expect: the pre-release is recreated (works for a merged PR while its head ref resolves) and hop 2 succeeds again.
- [ ] A queued populate that was displaced by a newer pending run in the same per-instance group (nothing frozen, nothing copied; known limitation): `gh workflow run obs-release-pr.yml -f pr_number=N`. Expect: the displaced run's pre-release is populated by the dispatched run.

## Cleanup

- [ ] Delete the throwaway GitHub release and tag: `gh release delete ppg/18.<minor>-99 --cleanup-tag --yes && git push percona :refs/tags/ppg/18.<minor>-99; git tag -d ppg/18.<minor>-99`. Expect: `gh release list` and `git ls-remote --tags percona 'ppg/18.<minor>-99'` show nothing.
- [ ] Revert the release.yaml and CHANGELOG entry through a normal PR: `git switch -c revert-rehearsal-18-99 percona/main && git revert -s <merge-or-commit-sha> && git push percona revert-rehearsal-18-99 && gh pr create`. Expect: the PR changes only `root/ppg/releases/18/release.yaml` and `CHANGELOG.md`; it is a release-only PR with no new `release.yaml` entry, so no tag or dispatch follows (check that "OBS PR Cleanup" tags nothing); merge it and confirm `sync-main` is green, so the `PPG_RELEASE` counter is back to its real value.
- [ ] Remove throwaway binaries from the production release project if any landed: `osc -A <apiurl> ls <rootprj>:ppg:releases:18 | head`, then for each throwaway package `osc -A <apiurl> rdelete -m 'remove rehearsal 18.<minor>-99' <rootprj>:ppg:releases:18 <package>`. Expect: the release project contains only real releases. Careful: delete only packages copied by the rehearsal, never the project; if unsure, compare against the previous real release's package list.
- [ ] If `obs-release.yml` never ran, delete the leftover pre-release: `venv/bin/python -m percona_obs -P pr-N sync delete ppg:releases:18 --help` first to confirm flags, then delete the tree `<pr_rootprj>:pr-N:ppg:releases:18`. Expect: the project is gone on every instance (the PR cleanup normally removes PR trees on close, so this is only needed when the PR stayed open).
- [ ] Final check: `gh pr list --state open --search 'releases/18 in:files'` and `git tag -l 'ppg/18.*-99'`. Expect: no open rehearsal PR and no throwaway tag; the next real cut derives the correct counter.
