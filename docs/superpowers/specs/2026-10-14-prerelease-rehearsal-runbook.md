# Labs rehearsal runbook: two-hop release flow

Rehearse the whole flow on labs with a throwaway release id before the first real
release. Reference: `docs/PERCONA_OBS_TOOL.md` "Releasing packages" and
`docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` §4-§5.

Conventions: `<minor>` is the current PG 18 minor (for example `6`), the throwaway id is
`18.<minor>-99` (never collides with a real counter), the tag is `ppg/18.<minor>-99`, `N` is
the rehearsal PR number, `<instance>` is an `OBS_INSTANCES` name, `<web>` is the OBS web URL.
Pre-release project URL: `<web>/project/show/<pr_rootprj>:pr-N:ppg:releases:18`.

`-P labs` and `-P pr-N` below are placeholder profile names; use your own.

Never let the rehearsal PR leave a state that ships: finish with the Cleanup phase.

## Preconditions

- [ ] `OBS_INSTANCES` repo variable lists the labs instance with `name`, `apiurl`, `rootprj` and `pr_rootprj`: `gh variable get OBS_INSTANCES | jq '.[] | {name, apiurl, rootprj, pr_rootprj}'`. Expect: every entry has all four keys; `pr_rootprj` differs from `rootprj`.
- [ ] Per-instance secrets exist: `gh secret list | grep OBS_PASSWORD_` and `gh variable list | grep -E 'OBS_WEB_URL|OBS_USER|JENKINS'`. Expect: one `OBS_PASSWORD_<instance>` per instance, `OBS_WEB_URL` set, and the Jenkins variables/secrets the QA lanes use are present.
- [ ] Local `gh` works and tags are fetched: `gh auth status && git fetch percona --tags && git tag -l 'ppg/18.*' | tail -3`. Expect: logged in with repo and workflow scope; latest real `ppg/18.*` tag listed.
- [ ] Staging is green on labs and main is synced: `venv/bin/python -m percona_obs -P labs build status ppg:staging:18` and open the latest `sync-main` run in the Actions tab. Expect: no failed/broken packages; the last sync-main run has successful sync jobs.
- [ ] No other open release PR for major 18: `gh pr list --state open --search 'releases/18 in:files'`. Expect: none (one in-flight release PR per major).

## Cut

- [ ] From a clean branch off `percona/main`: `git switch -c rehearsal-18-99 percona/main && venv/bin/python -m percona_obs -P labs project release ppg:staging:18 --release-id 18.<minor>-99`. Expect: exits 0; one local commit; `root/ppg/releases/18/release.yaml` has a new `18.<minor>-99` entry with `source_commit` set to the synced main SHA; `CHANGELOG.md` has a `[18.<minor>-99]` section; only files under `root/*/releases/` changed (`git show --stat HEAD`).
- [ ] Optional hop-1 dry run: `venv/bin/python -m percona_obs -P pr-N sync prerelease ppg:releases:18 --branch-from labs --dry-run`. The production profile (`labs`) points at the staging root; the PR profile (`pr-N`) at `<pr_rootprj>:pr-N`, created with `venv/bin/python -m percona_obs -A <apiurl> -R <pr_rootprj>:pr-N -e REMOTE_OBS_ORG_INTERCONNECT: -e PERCONA_OBS_PACKAGING_BRANCH:main -e PERCONA_OBS_PACKAGING_REPO:<repo url> profile create pr-N`. Expect: record check, mirror/changelog/tag checks and the green check pass; nothing is written. (`sync release --from ... --dry-run` only runs the entry and marker checks and lists the pairs; it does not check staging.)
- [ ] Push the branch to `percona` (not a fork) and open the PR: `git push percona rehearsal-18-99 && gh pr create --repo percona/obs-packaging --title 'REHEARSAL 18.<minor>-99 (do not ship)' --body 'Labs rehearsal'`. Expect: PR opens; note `N`.

## Populate

- [ ] Open the PR's Checks tab, workflow "OBS Release PR". Expect: job `Resolve release PR` green (release-only, no conflicting PR, non-empty), then one job `Populate pre-release (<instance>)` per instance, serialized per instance; `obs-pr-check` does not run the sync for this PR.
- [ ] Read the PR comment headed "## OBS Release PR — ✅ Pre-release populated (<instance>)" and download artifact `prerelease-report-<instance>` (`gh run download <run-id> -n prerelease-report-<instance>`). Expect: one comment per instance listing the pre-release projects (`ppg:releases:18` among them); the report lists no failed package.
- [ ] Open `<web>/project/show/<pr_rootprj>:pr-N:ppg:releases:18` and check the project description. Expect: project exists, binaries present for the staging package set, description ends with `source_commit: <sha>` equal to the entry in `release.yaml`.
- [ ] Watch the check runs named `Release / OBS QA / …` (caller job `Release`; lanes are prefixed `OBS QA / ppg:releases:18 / …`). Expect: they start only after every populate leg succeeded and run against the pre-release repos; a failed lane can be re-run from the PR UI.
- [ ] Check the QA lane list. Expect: package-level lanes are present (the cut copies them into the mirrors as `<package>.<segment>` project-level entries) next to the project-level lanes.
- [ ] Known limitation: `EXPECTED_VERSIONS` is empty on every release-mirror lane (mirrors have no package directories, so there are no versions to compute). Expect: the parameter is empty in the triggered Jenkins builds. Do not treat this as a failure.
- [ ] Populate while a `sync-main` poll is still running: merge a trivial staging change into main, and as soon as its `sync-main` run's `percona-obs sync push (<instance>)` jobs are green (the `Wait for OBS builds` jobs still running), re-run `project release` on the rehearsal branch and push, or dispatch `gh workflow run obs-release-pr.yml -f pr_number=N` if the cut already carries that commit. Expect: the populate log's "synced main commit" equals that in-progress run's head SHA (`gh run list --workflow sync-main.yml --limit 1 --json headSha,status`), not the previous completed run's.

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
- [ ] Pre-release already deleted but the release must be redone. The recovery is to cut a NEW release (`project release ppg:staging:18` on a fresh branch off `percona/main`, new PR, then Populate and Merge again); do not ship a second throwaway in the rehearsal. Repopulating the merged PR is NOT a recovery: it is refused by the record check, because main's `release.yaml` changed at the merge (`PPG_RELEASE` bumped). Check the refusal once with `gh workflow run obs-release-pr.yml -f pr_number=N`. Expect: `Populate pre-release (<instance>)` fails with "staging changed since the cut" listing `root/ppg/releases/18/release.yaml`.
- [ ] Re-run obs-pr-cleanup after a forced partial tag failure: force the `Tag release and dispatch obs-release` step to fail after it created the tag (e.g. cancel the run right after its "Creating tag" line, before the dispatch), then `gh run rerun <cleanup-run-id>`. Expect: the step logs "Tag ppg/18.<minor>-99 already points at this merge (re-run); dispatching" and exactly one new `OBS Release` run is dispatched with that tag.
- [ ] A queued populate that was displaced by a newer pending run in the same per-instance group (nothing frozen, nothing copied; known limitation): `gh workflow run obs-release-pr.yml -f pr_number=N`. Expect: the displaced run's pre-release is populated by the dispatched run.

## Cleanup

- [ ] Delete the throwaway GitHub release and tag: `gh release delete ppg/18.<minor>-99 --cleanup-tag --yes && git tag -d ppg/18.<minor>-99`, then `git push percona :refs/tags/ppg/18.<minor>-99` if the tag still exists remotely. Expect: `gh release list` and `git ls-remote --tags percona 'ppg/18.<minor>-99'` show nothing.
- [ ] Revert the release.yaml and CHANGELOG entry through a normal PR: `git switch -c revert-rehearsal-18-99 percona/main && git revert -s <merge-or-commit-sha> && git push percona revert-rehearsal-18-99 && gh pr create`. Expect: the PR changes only `root/ppg/releases/18/release.yaml` and `CHANGELOG.md`, so it counts as release-only: `obs-release-pr.yml` runs and its populate is EXPECTED to fail the record check ("staging changed since the cut") or the one-in-flight guard; that check is not required, merge anyway. After merge `obs-pr-cleanup.yml` finds the previous real tag already exists and dispatches nothing: the Tag step log shows "already exists at <sha>, not this PR's tag; not dispatched" and there is no new `OBS Release` run. Confirm `sync-main` is green so the `PPG_RELEASE` counter is back to its real value.
- [ ] Remove throwaway binaries from the production release project if any landed: `osc -A <apiurl> ls <rootprj>:ppg:releases:18 | head`, then for each throwaway package `osc -A <apiurl> rdelete -m 'remove rehearsal 18.<minor>-99' <rootprj>:ppg:releases:18 <package>`. Expect: the release project contains only real releases. Careful: delete only packages copied by the rehearsal, never the project; if unsure, compare against the previous real release's package list.
- [ ] Manual pre-release delete, only when the PR merged but `obs-release.yml` never ran or failed (a merged release PR's tree is kept on purpose: `obs-release.yml` deletes it after a successful hop 2; a closed-unmerged PR is cleaned automatically). Create the PR profile: `venv/bin/python -m percona_obs -A <apiurl> -R <pr_rootprj>:pr-N -e REMOTE_OBS_ORG_INTERCONNECT: -e PERCONA_OBS_PACKAGING_BRANCH:main -e PERCONA_OBS_PACKAGING_REPO:<repo url> profile create pr-N`, then `venv/bin/python -m percona_obs -P pr-N sync delete --yes --recursive --from-obs`. Expect: the tree `<pr_rootprj>:pr-N:...` is gone on that instance; repeat per instance.
- [ ] Final check: `gh pr list --state open --search 'releases/18 in:files'` and `git tag -l 'ppg/18.*-99'`. Expect: no open rehearsal PR and no throwaway tag; the next real cut derives the correct counter.
