# Release flow contract for the dashboard's Release tab

Date: 2026-11-11
Status: draft design, not yet implemented

The OBS dashboard (`Percona-Lab/obs-dashboard`) is gaining a Release tab that
drives a whole release without the CLI or the GitHub UI: select units, edit
and approve changelogs, watch the pre-release sync, approve and review QA,
release, watch the final sync. Its design is
`docs/superpowers/specs/2026-11-11-release-tab-design.md` in that repository
(§ 6 lists what it needs from here).

The dashboard holds no release logic and no release state. Each wizard step
is one GitHub action on this repository, performed with a personal access
token, and everything it shows is read back from GitHub: pull requests,
labels, branches, workflow runs, job names, annotations and artifacts. This
spec defines the changes here that make that possible, and the names the
dashboard depends on.

The two-hop release flow, release units, records, tags and the record check
stay exactly as they are (`2026-10-13-prerelease-project-release-flow-design.md`,
`2026-11-10-independent-release-units-design.md`).

## Goals

1. A release can be cut by dispatching a workflow, with no local checkout.
2. The pre-release sync starts only when someone asks for it, by adding the
   `obs-sync` label to the release PR.
3. The dashboard can link every QA lane to its Jenkins build.
4. The dashboard can find the runs, jobs and data it shows by stable names.
5. The dashboard can list the release units without re-implementing the
   unit rule.

## Non-goals

- Any change to what a release contains, to ids, tags, the freeze, the
  record check or hop 2.
- Phase-level progress of `sync prerelease` / `sync release` (the dashboard
  shows per-instance job status only).
- Webhooks, a GitHub App, or any credential handling here. The dashboard
  acts with a user's personal access token; events it causes trigger
  workflows like any user's.
- Removing the CLI flow. `project release` on a laptop, a hand-pushed branch
  and a hand-opened PR keep working.

## How the dashboard drives a release

For orientation; only the workflow behaviour below is in scope here.

| Dashboard step | What it does on GitHub |
|---|---|
| Cut | dispatches `obs-release-cut.yml` (`units`, `branch`); when the run succeeds, opens a PR from `branch` to `main` |
| Edit changelog | amends the single release commit on `branch` (force-push) |
| Approve changelog | adds label `obs-sync` |
| Retry sync | removes and re-adds `obs-sync` |
| Approve QA | adds label `qa-release` |
| Update to latest main | removes both labels, dispatches `obs-release-cut.yml` again with the same `units` and `branch` |
| Release | merges the PR (rebase), then deletes `branch` |
| Retry final sync | dispatches `obs-release.yml` (`pr_number`, `tags`) |
| Abandon | deletes `branch` (GitHub closes the PR) |

## Design

### 1. Cut workflow: `obs-release-cut.yml`

New workflow. Sole trigger `workflow_dispatch`.

Inputs:

| Input | Required | Meaning |
|---|---|---|
| `units` | yes | Space-separated unit roots, e.g. `ppg:staging:18 ppg:staging:17:extras` |
| `branch` | yes | Release branch to create or reset, e.g. `release/20261111T143210`. Must match `^release/[A-Za-z0-9._-]+$`; anything else fails the run before any work |

`run-name: Cut ${{ inputs.branch }}`. The dashboard finds a release's cut run
by this exact name.

Concurrency group `obs-release-cut-<branch>`, no cancel-in-progress.

Steps:

1. Check out `main` with full history and tags (`project release` reads tags
   for the open-release detection and needs the source commit to be an
   ancestor of HEAD).
2. Create the local branch `<branch>` at `main`'s head. An existing remote
   branch of that name is ignored: a re-cut always starts from current
   `main`, which is what refreshes `source_commit`, the mirrors and the
   changelog.
3. For each unit, in the order given, run
   `percona-obs -P <main profile> project release <unit> --also-profile …`
   with one `--also-profile` per further entry of `OBS_INSTANCES`, so the
   changelog is built from every instance (as documented for the manual
   flow). `gh` is authenticated with the workflow token for the
   source-commit lookup. The CVE scan runs as in the manual flow.
4. If any unit fails, the run fails and **nothing is pushed**. A partial
   release branch must never exist.
5. Squash the per-unit commits `project release` made into **one** commit on
   top of `main`: subject `release: <id>, <id>…` (the release ids, in input
   order), signed off, authored by the Actions bot identity. The dashboard
   amends this commit when a changelog is edited, so the release PR must
   stay at exactly one commit.
6. Force-push `<branch>`.
7. Upload the artifact `generated-changelogs`: one file `changelogs.json`,
   a JSON object mapping each unit root to the changelog section the cut
   generated for it (from its `## [<id>]` heading up to, not including, the
   next `## [` heading), e.g.

   ```json
   {"ppg:staging:18": "## [18.6-6] - 2026-11-11\n\n### Changed\n- …\n"}
   ```

   The dashboard uses it for "reset to generated text". It is uploaded only
   by a successful run.

The workflow does **not** open the pull request. A PR opened with the
workflow token would not trigger `pull_request` workflows; the dashboard
opens it with its own token once the run has succeeded.

The push is made with the workflow token. It triggers nothing, which is
intended: after a cut or re-cut the PR carries no `obs-sync` label, so
nothing should run until the changelog is approved.

Re-cut and ids: because a re-cut starts from `main`, where the unit's last
`release.yaml` entry is tagged, `project release` derives the same next id
again. No special handling is needed.

Permissions: `contents: write`, `actions: read`, plus the OBS secrets the
populate job already uses for read access to every instance.

Failure text: each failing unit ends with an `::error::` line naming the
unit and the reason, so the dashboard can show the job's failure
annotations.

### 2. Sync gate on `obs-release-pr.yml`

Today a release PR populates on `opened`, `synchronize` and `reopened`, and
QA runs when the PR carries `qa-release`. Populate becomes label-gated the
same way:

| Event | PR has `obs-sync` | Populate | QA |
|---|---|---|---|
| `opened`, `reopened`, `synchronize` | no | skipped | skipped |
| `opened`, `reopened`, `synchronize` | yes | runs | runs after populate if `qa-release` is present |
| `labeled` with `obs-sync` | (now yes) | runs | runs after populate if `qa-release` is present |
| `labeled` with `qa-release` | either | skipped | runs alone against the existing pre-release (unchanged) |
| `labeled` with any other label | either | whole run skipped (unchanged) | |
| `workflow_dispatch` (`pr_number`) | either | runs (unchanged: an operator asked for it) | as today |

Changes:

- `resolve`'s job-level `if` accepts `obs-sync` as well as `qa-release` for
  `labeled` events.
- `resolve` outputs `run_sync` (the PR carries `obs-sync`), next to `run_qa`.
- `populate` runs when `kind == 'release'` and either the event is
  `workflow_dispatch`, or `run_sync` is true and the event is not
  `labeled`-with-`qa-release`.
- A push that changes only release `CHANGELOG.md` files keeps skipping
  populate (`kind=changelog`), as today.
- `resolve` (release-only check, one-in-flight guard, fork refusal) keeps
  running on every `opened` / `synchronize` / `reopened`, labelled or not,
  so a conflicting or mixed PR fails early.
- The pre-release PR comment says that the sync starts once `obs-sync` is
  added.

"Retry sync" is remove-then-add of `obs-sync`: the `labeled` event re-runs
populate for the PR head. Removing a label triggers nothing (`unlabeled` is
not a subscribed type) and must stay that way.

This changes the manual flow too: after opening a release PR by hand, add
`obs-sync` to populate. Document it.

### 3. Jenkins build annotation

Each QA lane job must expose its Jenkins build URL where the Checks API can
read it while the job is still running.

When `qa run` starts a build (`cmd_qa.py`, where it prints
`> <label> started: <build_url>`) and `GITHUB_ACTIONS` is set, it also
prints a workflow command:

```
::notice title=Jenkins build::<release project> <build_url>
```

- The title is exactly `Jenkins build`.
- The message is two fields separated by one space: the **release** project
  the lane tests, without instance root and without the PR prefix (e.g.
  `ppg:releases:18` or `ppg:releases:18:containers`), then the URL. The
  dashboard groups lanes by unit by matching this project against the unit's
  release project and its subprojects.
- One annotation per lane job. The dashboard uses the first `Jenkins build`
  annotation it reads for a job, so a lane that starts several builds (a
  retry) emits the annotation for the first one only.

Nothing else about `qa run` output changes.

### 4. Stable names the dashboard depends on

These become a contract. A comment next to each says so, and a test pins the
strings (§ Testing).

| What | Value |
|---|---|
| Workflow files | `obs-release-cut.yml`, `obs-release-pr.yml`, `obs-release.yml` |
| Labels | `obs-sync`, `qa-release` |
| Cut run name | `Cut <branch>` |
| Final sync run name | `Release PR #<pr_number>` (new: `run-name` on `obs-release.yml`) |
| Populate job | `Populate pre-release (<instance>)` |
| CDN wait job | `Wait for download CDN (<instance>)` |
| QA lane jobs | name starts with `Release / OBS QA / ` |
| Hop-2 copy job | `Release to OBS (<instance>)` |
| Hop-2 finalize job | `Publish GitHub releases and delete the pre-release` |
| Hop-2 delete job | `Delete the pre-release (<instance>)` |
| Populate report artifact | `prerelease-report-<instance>` |
| Cut artifact | `generated-changelogs` |
| Jenkins annotation title | `Jenkins build` |
| Unit list file | `docs/versions/release-units.json` |

`obs-release-pr.yml` runs are found by the PR head SHA (they are
`pull_request` runs), so they need no run name. The dashboard never
dispatches that workflow.

`obs-release.yml` gets `run-name: Release PR #${{ inputs.pr_number }}`. It is
dispatched by `obs-pr-cleanup.yml` on `main`, so its head SHA says nothing
about the PR; the run name is the only link.

### 5. Populate report format

`prerelease-report-<instance>` already exists. Its format becomes
documented and stable: one file, a JSON list with one object per release
project of the PR:

```json
[{"project": "ppg:releases:18",
  "prerelease": "isv:percona:PR:pr-415:ppg:releases:18",
  "outcome": "success",
  "source_commit": "9e9d973…",
  "removals": ["package python3-six", "project ppg:releases:18:old"]}]
```

- `outcome` is `success`, `failure` or `skipped`. `skipped`: the instance's
  slice holds no package of the release unit (it lives on another
  instance); nothing was populated there, the `prerelease` project does not
  exist on it, and it is not a failure.
- `removals` lists what hop 2 would delete, one string per item, prefixed
  `package ` or `project ` (the dry-run lines, as today).
- Fields may be added; these five keep their names and meaning.

The dashboard reads the failed projects and the removals from it, and the
failure text from the populate job's `::error::` annotations. Every failure
path of `sync prerelease` and of the hop-2 dry-run must therefore end with an
`::error::` line that states the reason (staging not green: name the
packages; staging changed since the cut; dry-run failed).

### 6. Unit list: `docs/versions/release-units.json`

A machine-readable list of every releasable unit, so the dashboard never
applies the `containers` / `tarballs` bundling rule itself.

```json
[{"unit": "ppg:staging:18",
  "members": ["ppg:staging:18", "ppg:staging:18:containers", "ppg:staging:18:tarballs"],
  "release_project": "ppg:releases:18",
  "release_dir": "root/ppg/releases/18"},
 {"unit": "ppg:staging:18:extras",
  "members": ["ppg:staging:18:extras", "ppg:staging:18:extras:containers"],
  "release_project": "ppg:releases:18:extras",
  "release_dir": "root/ppg/releases/18/extras"}]
```

- `unit`: the unit root, exactly the value `project release` accepts and the
  `project:` value its `release.yaml` carries.
- `members`: the unit's member projects from `release_unit_members`, root
  first. Project names are instance-agnostic (no instance root).
- `release_project`: the release project of the unit root.
- `release_dir`: repository path of the unit's release directory (where its
  `release.yaml` and `CHANGELOG.md` live or will live).
- Units with nothing to release (package-less namespace roots such as
  `ppg:staging` and, after the tree move, `ppg:staging:common`) and bundled
  children are not listed. A unit that has never been released is listed.
- Sorted by `unit`, two-space indented, trailing newline, so regeneration is
  byte-stable.

Generation: a new subcommand `percona-obs project release-units` prints the
JSON for the tree (reads git only, no OBS). The file is committed. Because
`update-version-lists.yml` is disabled, the file is kept current by a check:
`python-tests.yml` (or `project-config-check.yml`) fails when the committed
file differs from the generated output, with a message naming the command to
run. Any PR that adds, removes or moves a staging project therefore updates
the file in the same PR.

### 7. Behaviour to confirm, not change

The dashboard relies on these; the plan verifies each and adds a test or a
comment where one is missing.

- **Abandon.** Deleting the release branch closes the PR; `obs-pr-cleanup.yml`
  then deletes the pre-release project tree of an unmerged release PR.
- **Branch deleted after merge.** The dashboard deletes `release/*` after
  merging. `obs-pr-cleanup.yml` and `obs-release.yml` must not need the
  branch after the merge (they use `merge_commit_sha`, the PR number and
  `main`).
- **Amended commit.** A force-push that only changes a release
  `CHANGELOG.md` arrives as `synchronize`. `release_pr.py classify` compares
  with a three-dot compare, so for an amended commit the diff is the whole
  release commit, not changelog-only. With the sync gate this is harmless
  before approval (no `obs-sync`, nothing runs). After approval the
  dashboard does not allow changelog edits. No change to `classify` is
  required; optionally compare the two trees directly so an amended
  changelog-only commit is recognised.
- **QA-only run.** Adding `qa-release` runs QA against the existing
  pre-release. The dashboard adds it only after the populate for the current
  head succeeded.
- **Rebase merge.** The dashboard merges with the rebase method (the only
  one enabled). `obs-pr-cleanup.yml` tags `merge_commit_sha`, as today.

## Error handling

| Situation | Behaviour |
|---|---|
| `branch` input not `release/…` | Cut run fails before checkout work |
| A unit is not a unit root, is empty, or cannot be cut (OBS listing empty, source commit not found) | Cut run fails with `::error::` naming the unit; nothing pushed; no artifact |
| Cut dispatched while another cut for the same branch runs | Queued behind it (concurrency group) |
| Re-cut while the PR is open | Branch force-pushed; PR updates; no populate (no label) |
| `obs-sync` added to a PR that is not release-only or conflicts with an older release PR | `resolve` fails as today; populate does not run |
| `obs-sync` added to a fork PR | Refused in `resolve` as today |
| `release-units.json` out of date | CI check fails, naming `percona-obs project release-units` |

## Testing

pytest, no OBS or GitHub traffic:

- `project release-units`: membership for a major, `extras`, `tde`,
  `common:tools`; namespace roots and bundled children omitted; never-released
  unit included; output byte-stable; the committed file equals the generated
  one.
- `qa run`: the notice line is printed with `GITHUB_ACTIONS` set and not
  otherwise; project is the release project without root or PR prefix.
- A test that reads the three workflow files and asserts the contract
  strings of § 4 (job `name:` values, `run-name`, artifact names, label
  names), so a rename fails CI here instead of silently breaking the
  dashboard.
- `release_pr.py`: unchanged behaviour for `classify`.

Workflow logic (`run_sync`, the populate condition): the label/event table
of § 2 as a unit-tested helper if the condition is moved into
`release_pr.py`, otherwise exercised in the rehearsal.

End to end, on the labs instance (existing rehearsal runbook), driven by
hand with `gh` exactly as the dashboard will:

1. `gh workflow run obs-release-cut.yml -f units=… -f branch=release/test1`;
   check one commit, the artifact, no PR, no populate.
2. Open the PR; check `resolve` runs and populate does not.
3. Amend the changelog and force-push; check nothing populates.
4. Add `obs-sync`; check populate runs, report artifact present.
5. Remove and re-add `obs-sync`; check populate re-runs.
6. Add `qa-release`; check QA-only run, each lane has a `Jenkins build`
   annotation.
7. Dispatch the cut again for the same branch; check the branch is reset on
   `main` with the same release id.
8. Merge; check the `Release PR #N` run name, then delete the branch.
9. Separately: cut, open PR, delete the branch; check the PR closes and the
   pre-release tree is deleted.

## Documentation

`docs/PERCONA_OBS_TOOL.md` (release section: the cut workflow, the
`obs-sync` gate, the manual flow now needing the label),
`.github/copilot-instructions.md` (workflows), `root/ppg/releases/README.md`.

## Delivery order

1. § 6 unit list and § 3 annotation (tool changes, independent).
2. § 4 run name and contract test, § 5 report documentation.
3. § 2 sync gate (changes the manual flow; announce it).
4. § 1 cut workflow.
5. Rehearsal.
