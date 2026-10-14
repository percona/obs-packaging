# Pre-release OBS project release flow

Date: 2026-10-13
Status: approved design, not yet implemented

## Problem

The release pipeline copies binaries from `ppg:staging:<major>` into
`ppg:releases:<major>` at merge time of the release PR. Because the binaries
being released live in staging until that moment, the whole window from
"release cut" to "release copied" has to keep staging immutable:

- QA for the release runs against staging, so any staging change invalidates
  it.
- `obs-release.yml` disables `sync-main.yml` for the duration of the copy (the
  "release lock"), because merging the release PR raises the computed
  `PPG_RELEASE` counter and a staging sync would retag the container images
  the release is still copying.
- `sync release` refuses to run when the staging tree changed since the tag
  (`git diff <tag>..HEAD`).
- Releases dispatched close together displace each other in the
  `sync-main-sync` concurrency group, so a PR cannot safely release more than
  one PG major.

Development on staging is blocked while a release is in flight, and a QA
failure found on the candidate forces a fix-and-redo cycle under that lock.

## Goals

1. Staging stays writable while a release candidate is under QA.
2. QA runs against the exact binaries that will be released, and a QA failure
   is fixed in staging and re-tested without restarting the release.
3. One release PR can release several PG majors (and the `common` tools
   release) at once.
4. The release record in git names the staging tree the binaries were built
   from.
5. No sync-main lock, no counter race, no displaced dispatches.

## Non-goals

- Labelling QA pipelines as release / nightly / PR lanes. Until that exists a
  release runs every lane declared in the staging project and its
  subprojects.
- Changing `sync release-pr`; it stays a manual recovery command.
- Mirroring package sources into the release tier. Release projects remain
  binary-only snapshots described by `project.yaml` mirrors.

## Overview

The release becomes two `osc release` hops with a frozen intermediate project:

```
ppg:staging:18 ──(hop 1, PR open)──▶ <pr-root>:pr-N:ppg:releases:18 ──(hop 2, merge)──▶ ppg:releases:18
                freeze staging             QA runs here                    no staging involvement
```

- `percona-obs project release` cuts the release locally and records the
  staging source commit.
- Opening the release PR makes `obs-release-pr.yml` populate a **pre-release
  project** under the PR namespace (hop 1) and run every QA lane against it.
- Fixes go into staging through normal PRs; the release PR is refreshed and
  repopulated until QA is green.
- Merging tags the release and dispatches `obs-release.yml` once, which copies
  the pre-release into the release project (hop 2), publishes the GitHub
  releases and deletes the pre-release.

## 1. OBS layout and lifecycle

### Naming

For release PR number N and release mirror `ppg:releases:18` the pre-release
project is `<OBS_PR_ROOTPRJ>:pr-N:ppg:releases:18`, with nested subprojects
`…:containers`, `…:extras`, `…:extras:containers`, `…:tarballs`, one per
mirror directory. The name is the ordinary PR-profile resolution (PR rootprj +
project id); there is no new naming rule. A multi-version PR holds one such
tree per `release.yaml` it changes, side by side.

### Meta

Each pre-release project's meta is produced from the mirror `project.yaml` in
the PR branch exactly as the production release project's would be: same
repositories, `build: false`, project-config copied, subproject and
repository paths rewritten to the PR root the way `sync push --branch-from`
rewrites them. The `qa:` blocks carried into the mirrors (section 2) resolve
`${OBS_ROOTPRJ}` to the PR root, so QA lands on the pre-release.

**Publish is forced on** in the pre-release regardless of the mirror's
`publish:` flags, so Jenkins always has repositories to consume. The mirror's
own flags apply only on hop 2.

### Instance slicing

Both hops run once per `OBS_INSTANCES` entry with that instance's profile.
The slice is applied by the primitives both commands share:

- subprojects: only mirror directories `project_in_slice` admits;
- repositories: pruned to the profile's include/exclude globs on meta apply,
  and the copy loop only releases repositories that exist on the target;
- freeze scope: computed from the in-slice source tree.

So on labs the pre-release tree is the container subprojects with the
`ubi*`/`UBI_*`/`images` repositories; on build.opensuse.org it is the top
project, `extras` and `tarballs` with everything else. QA routing is the
existing `resolve_qa_instance` by `qa_types`.

### Lifecycle

- Created or re-applied on every push to the release PR by `obs-release-pr.yml`,
  and on demand through a `workflow_dispatch` entry of the populate job that
  takes a PR number.
- Repopulated on every push and on every dispatch; repopulation is the
  update-in-place `osc release` path, idempotent.
- Deleted by `obs-release.yml` after hop 2 succeeded on every instance, not by
  `obs-pr-cleanup.yml`. A failed hop 2 leaves the pre-release in place for
  re-dispatch. `obs-pr-cleanup.yml` still deletes it for a release PR closed
  unmerged; `obs-stale-cleanup.yml` still covers abandoned PRs.

### One in-flight release PR per major

`obs-release-pr.yml`'s `resolve` job fails for a release PR when another open PR
(found through the GitHub search API) changes the same `release.yaml`. The
first one opened wins. Two PRs releasing the same major would race on the
release counter and on hop 2.

## 2. Tool changes

### `release.yaml` format

Entries gain a mapping form; plain strings remain accepted for history:

```yaml
project: ppg:staging:18
releases:
  - ppg/18.4-1
  - ppg/18.6-1
  - tag: ppg/18.7-1
    source_commit: 9e9d9738c0…   # full SHA of main
```

The last entry is the current release, as today. `source_commit` is the SHA
of `main` whose staging tree the pre-release was built from.

### `project release` (existing command, three changes)

1. **Open-release refresh.** If the last entry's tag does not exist in git,
   the release id is still open: the command keeps that entry, regenerates
   the mirror tree, replaces the existing `CHANGELOG.md` section for that id
   instead of prepending a new one, and updates `source_commit`. Only when
   the last tag exists does it derive the next id and append.
   `--release-id` still overrides. This is what makes the fix loop (section
   5) a re-run of the same command.
2. **Source commit.** Resolved as the head SHA of the last successful
   `sync-main.yml` run on `main`, read through the GitHub API (`gh api`),
   overridable with `--source-commit <sha>`. The command fails if the SHA is
   not an ancestor of HEAD, so the branch always contains the tree it claims
   to release.
3. **QA blocks in mirrors.** The mirror writer carries each staging
   project's `qa:` block into the corresponding mirror. Release mirrors are
   `standalone` and have no `macros.yaml`, so the writer renders `%!{…}`
   macros with the staging chain at write time (e.g.
   `OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:releases:18`, `VERSION: ppg-18.6`);
   `ppg:staging:<major>` inside parameter values is rewritten to
   `ppg:releases:<major>` the same way subproject paths are. Only `${…}` env
   tokens survive, resolved per profile at QA time. Package-level `qa:` entries
   (from each direct package's `package.yaml`, `_shared/` links followed) are
   appended to the mirror's list as project-level entries named
   `<package>.<segment>` (segment = the entry's `name` or its `pipeline`),
   because mirrors have no package directories; on the pre-release they run as
   project lanes; when the mirror has more than one entry, the entry name
   becomes the check-name segment (`OBS QA / <project> / <package>.<segment>`).
   A duplicate name fails the cut.

### `sync prerelease <releases-project>` (new command)

Runs with the PR profile. Steps:

1. Read `release.yaml`; require a mapping entry with `source_commit`.
2. **Record check**: diff the freeze-scope paths between `source_commit` and
   the head of the last successful sync-main run; any difference aborts with
   "staging changed since the cut, re-run `project release`". Runs before
   anything is frozen.
3. Create or re-apply the pre-release project tree from the mirror
   `project.yaml` files, publish forced on, builds disabled.
4. Drain, assert green, freeze staging plus the aggregate sources,
   `osc release` into the pre-release for the top project and every in-slice
   subproject, verify binaries landed, restore. This is today's
   `_freeze_and_run` path, moved into the shared module.
5. Write `source_commit` into each pre-release project's description so hop 2
   can re-check it without git.

`--dry-run` keeps today's checks (mirrors complete, changelog section
present, tag unused, source reachable, staging green) and performs steps 1–2.

### `sync release <releases-project> --from <pre-release-project>` (changed)

With `--from` the command loses the freeze and the git divergence check:

1. Re-check that the pre-release description's `source_commit` equals the
   tagged `release.yaml` entry's.
2. Apply the release project meta from the mirror (repo additions, publish
   flags, prjconf), builds disabled.
3. `osc release --no-delay` from the pre-release for the top project and every
   in-slice subproject, with the same temporary `<releasetarget>` entries
   (added before, removed in a `finally`) that hop 1 and the legacy path use;
   OBS requires release targets for a project-level release, so the
   pre-release meta carries them only during the copy.
4. Verify binaries landed (bounded by `--verify-timeout`).

Without `--from` the command keeps its current staging-sourced behaviour as a
recovery path.

### Shared module `percona_obs/release_copy.py`

Holds what both hops use: subproject pair collection
(`_collect_release_subprojects`), meta apply, the copy loop, and verify.
`release_freeze.py` keeps the freeze primitives, `release_scope.py` the scope
computation. `cmd_sync_release` and the new `cmd_sync_prerelease` become thin
orchestration.

## 3. Workflows

### `obs-pr-check.yml`

As implemented, release PRs are **not** handled in `obs-pr-check.yml`: its `sync`
job is gated out for them (`resolve` still detects release-only PRs). The `resolve`
guard (release-only, one in flight per major, non-empty release), the `populate` job
(one leg per `OBS_INSTANCES` entry, serialised on that instance's
`sync-main-sync-<name>` concurrency group without cancel-in-progress, running
`sync prerelease` per changed `release.yaml`), the per-instance PR comment, the
`workflow_dispatch` repopulate (`pr_number` input) and the release QA live in the new
`obs-release-pr.yml`, because `obs-pr-check.yml` cancels superseded runs and a
cancelled populate would leave production staging frozen. The QA fan-out
(`detect-qa-matrix`, `merge-qa-matrix`, `qa`) is the reusable `qa-fanout.yml`
(inputs `pr_number`, `qa_types`), called by `obs-pr-check.yml` (job `PR`, labelled
PRs after the builds) and by `obs-release-pr.yml` (job `Release`, with no trigger label
after every populate leg succeeded); check names are prefixed by the caller's job name.
The matrix is discovered from the PR project's subprojects on each instance, so every
lane of every released major is included.

### `obs-pr-cleanup.yml`

- Merged release PR: create one tag per changed `release.yaml` on
  `merge_commit_sha` (the last rebased commit), then dispatch
  `obs-release.yml` exactly once with `pr_number` and the list of tags. No
  lock, no per-tag dispatch loop.
- The `delete` job is skipped for a merged release PR. It still runs for a
  release PR closed unmerged and for every other PR.

### `obs-release.yml`

- Inputs: `pr_number`, `tags` (space separated). Manual recovery:
  `gh workflow run obs-release.yml -f pr_number=N -f tags="ppg/17.12-1 ppg/18.7-1"`.
- Per `OBS_INSTANCES` leg, checked out at the first tag (all tags share the
  commit): `sync release <releases-project> --from <pr-root>:pr-N:<releases-project>`
  for every tag in order. The `lock` job, the sync-main disable/enable and
  the lock-state reporting are deleted. The per-instance concurrency group
  stays (hop 2 writes release project meta).
- `finalize` after all legs: one GitHub release per tag from its `CHANGELOG.md`
  section, then `sync delete --yes --recursive` of the PR project tree on
  every instance. Runs only when every leg succeeded.

### `sync-main.yml`

The release-only push skip is removed. Merging a release PR raises
`PPG_RELEASE`; staging images are retagged on the next sync and nothing races
it, because the released images already sit in the pre-release.

### `obs-stale-cleanup.yml`

Unchanged.

## 4. Error handling and recovery

### Hop 1 (PR open)

| Failure | Behaviour | Recovery |
|---|---|---|
| Staging not green / drain timeout | `sync prerelease` fails before copying; freeze restored in `finally`; PR comment names the packages | Fix staging, repopulate |
| Staging moved since the cut | Record check fails before any freeze, printing the staging-path diff | Re-run `project release`, push |
| Partial copy (OBS error mid `osc release`) | Freeze restored; pre-release holds a mix; verify fails loudly | Repopulate (update-in-place, idempotent) |
| Push during population | Second run queues behind the first in the per-instance group | None needed |

Nothing writes to the PR branch, so there is no bot commit, no trigger loop
and no orphan head commit.

### Hop 2 (after merge)

| Failure | Behaviour | Recovery |
|---|---|---|
| A leg fails | `finalize` skips GitHub releases and the delete; tag exists; pre-release intact; staging untouched | Re-dispatch with the same `pr_number` and `tags` (idempotent) |
| Record mismatch (pre-release description ≠ tagged entry) | Leg refuses | The merged record is wrong: open a new release PR |
| Pre-release already deleted | Leg fails on missing source project | Repopulate via `workflow_dispatch` of obs-release-pr.yml with the PR number (works while the PR head ref resolves), then re-dispatch obs-release |
| Dispatch failure in obs-pr-cleanup | Tags exist, nothing copied | Manual dispatch |

### What disappears

The sync-main lock, the "sync-main is DISABLED" annotations, the
pending-cancellation race, the release-only push skip in sync-main, and the
`git diff <tag>..HEAD` divergence check.

## 5. User process

1. `project release ppg:staging:18` (and `ppg:staging:17`, `ppg:staging:common`
   on the same branch for a combined release). Push the branch, open the PR.
2. `obs-release-pr.yml` populates the pre-release per instance and runs every
   staging QA lane against it.
3. QA fails: fix the package in staging through a normal PR; once merged and
   synced, rebase the release branch, re-run `project release` (refreshes the
   open id, the changelog section and `source_commit`), push. When only
   staging changed and the changelog is unaffected,
   `gh workflow run obs-release-pr.yml -f pr_number=N` repopulates instead.
4. Everything green: merge. `obs-pr-cleanup.yml` tags and dispatches
   `obs-release.yml` once; it copies the pre-release into the release
   projects, creates the GitHub releases, deletes the pre-release.

## 6. Testing

Unit tests in `tests/`:

- `release.yaml` parsing of string and mapping entries; last-entry selection.
- `project release` open-release refresh rule (tag absent → refresh in place;
  tag present → next id appended); CHANGELOG section replacement.
- QA block rewrite in the mirror writer (macro rendering, project path
  rewrite, env tokens preserved).
- Record check diff logic in `sync prerelease`.
- `sync release --from` argument plumbing and the description re-check.

Workflow logic is validated by a rehearsal on labs with a throwaway release
id through the whole loop: populate, deliberate repopulate, merge, manual
re-dispatch of hop 2.

## 7. Documentation

- `docs/PERCONA_OBS_TOOL.md`: "Releasing packages" rewritten around the two
  hops, the `release.yaml` mapping form, the refresh rule, recovery recipes.
- `.github/copilot-instructions.md`: workflow descriptions for
  `obs-pr-check`, `obs-pr-cleanup`, `obs-release`, `sync-main`.
- `root/README.md`, `root/ppg/releases/README.md`: tier description mentions
  the pre-release.

## 8. Rollout

1. **Tool PR**: `release_copy.py`, `sync prerelease`, `sync release --from`,
   `project release` changes, tests. Mergeable on its own; `sync release`
   without `--from` is unchanged so the old flow keeps working.
2. **Workflows PR**: obs-pr-check populate path, obs-pr-cleanup single
   dispatch, obs-release rewrite, sync-main skip removal, docs. One PR, since
   they only make sense together.
3. **Rehearsal** on labs before the next real release train.

## Decisions log

- Pre-release lives under the PR namespace (not a fixed `ppg:prerelease:<major>`
  nor a per-release-id project): reuses PR lifecycle, cleanup and QA fan-out.
- Release QA = all staging lanes, until pipeline labelling exists.
- Population and QA are fully automatic on a release PR, no labels.
- `source_commit` is recorded by `project release` on the developer's
  machine, not committed back by CI: a workflow-token push would become an
  untested PR head and block required checks.
- Hop 2 uses `osc release --no-delay` with temporary `<releasetarget>`
  entries (removed in a `finally`), as hop 1 does; OBS requires release
  targets for a project-level release, so the pre-release meta carries them
  only during the copy.
- Package-level `qa:` lanes reach the mirrors as `<package>.<segment>`
  project-level entries (mirrors have no package directories); duplicates
  fail the cut.
