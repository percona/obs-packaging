# Release unit build freeze

Date: 2026-11-26. Status: design, awaiting approval.

## 1. Intent

When a release is being prepared, an update to an OS base package can start a
wave of rebuilds across a staging unit. The unit stops being green, `sync
release` cannot drain and copy it, and the release slips by hours or days.

A maintainer needs a switch that makes a release unit ignore such waves for the
days around a release, while a late packaging fix merged to `main` still builds
and reaches everything that depends on it.

## 2. Goals, non-goals, anti-goals

Goals

- Freeze and unfreeze a list of release units from a manually dispatched GitHub
  Actions workflow, on every configured OBS instance.
- While frozen, nothing in the unit rebuilds because of a dependency change:
  packages, container images and aggregates alike.
- While frozen, a source change pushed by `sync push` builds, and everything in
  frozen projects that depends on it is rebuilt against the new binaries.
- The freeze survives `sync push` runs (merges to `main`, the nightly run).
- A frozen unit stays visible, so it is not left frozen by accident.

Non-goals

- Freezing automatically as part of the release cut, or unfreezing
  automatically after a release. Both stay manual.
- Avoiding the postponed rebuilds. Unfreezing lets them start; that is accepted.
- Freezing PR projects (`--branch-from` flow). They are never frozen.
- Changing `sync release` / `sync prerelease`. Their short build-disable around
  the copy stays as it is.

Anti-goals (the feature has failed if any of these happen)

- A release ships binaries that were not built against each other, for example
  an image carrying the old build of a package that got a late fix.
- A freeze is lost silently because some other change rewrote the project meta.
- The green check before a release copy is weakened.

## 3. Background: how OBS behaves (verified)

Read from the OBS backend source (upstream master, 2026-11-26) and the
scheduler installed on the labs server (obs-server 2.11 alpha, 2026-10-14);
behaviour confirmed with throwaway projects on labs.

- A project `<repository>` accepts `rebuild="transitive|direct|local"`.
  `local` means "build on source change only".
- rpm/deb packages (`BSSched/BuildJob/Package.pm`): with `local`, an unchanged
  source skips the dependency comparison. A package whose dependency is being
  rebuilt reports done, not `blocked`, when it has a successful build of the
  same source.
- Container and kiwi images (`metacheck` in `BSSched/BuildJob.pm`): with
  `local`, a dependency or base-image change with unchanged source is done.
- Aggregates (`BSSched/BuildJob/Aggregate.pm`): with `local` **and** the
  prjconf line `BuildFlags: aggregate-checklocal`, the aggregate re-copies only
  when its own source changes. Without the flag, aggregates ignore `local`.
- `cmd=rebuild` deletes the package's build record (`:meta/<package>`). After
  that every build type schedules a new build, also under `local`, and waits as
  `blocked` while something it depends on is not ready.
- Dependency expansion runs before the `local` shortcut, so a base update that
  makes a build dependency unresolvable still flips the state to
  `unresolvable`. Binaries are kept. The freeze does not hide this.

Labs test results:

| Run | Outcome |
|---|---|
| `local` set, one package rebuilt on its own | dependents, aggregate, image unchanged |
| source change, then all dependent triggers at once (two runs) | all rebuilt against the new package, also across projects |
| triggers sent 8 s before the source change | dependents rebuilt against the old package and were never corrected |
| source change, wait until pending, trigger same project, wait until pending, trigger other projects | all correct; each wait about 2 s |

Conclusion: a trigger is safe once the scheduler has seen the change it
depends on, and unsafe before. Triggers are therefore sent in stages.

Not verified: that the scheduler deployed on build.opensuse.org behaves the
same (it normally tracks upstream master). See section 8.

## 4. Approaches considered

A. **`rebuild="local"` plus tool-driven propagation (chosen).** The freeze is
   an OBS repository attribute. `sync push` sends explicit rebuild triggers for
   the dependents of whatever it changed in a frozen unit. Late fixes work, the
   green check stays meaningful, and propagation cannot be forgotten.

B. **`rebuild="local"` plus manual propagation.** Same freeze, but a person
   runs a "rebuild dependents" command after a late fix. Less code in `sync
   push`; a forgotten run ships images with the old package. Rejected.

C. **`rebuild="direct"`.** OBS propagates one level itself, but direct OS
   dependencies (compiler, openssl-devel) still trigger rebuilds, so the wave
   gets through. Rejected.

D. **Build-disable the unit** (what `sync release` does for the minutes around
   the copy). Blocks late fixes and makes every package report `disabled`,
   which blinds the green check. Rejected for a freeze that lasts days.

The user chose A after the labs test.

## 5. Design

### 5.1 What "frozen" means

A project is frozen when every one of its repositories carries
`rebuild="local"`. A release unit is frozen when its root project and its
bundled children (`common.BUNDLED_SUBPROJECTS`: `containers`, `tarballs`) that
exist on the instance are frozen.

The state lives only in OBS project meta. Nothing is committed to git to
freeze or unfreeze. Each OBS instance holds its own state.

### 5.2 Commands

Two new `project` subcommands (author's call on naming):

```
percona-obs project freeze   <unit> [<unit> ...]
percona-obs project unfreeze <unit> [<unit> ...]
```

- `<unit>` is a release unit root in the form the release-cut workflow takes
  (`ppg:staging:18`, `ppg:staging:17:extras`). Anything that is not a unit root
  is an error before any change is made.
- `freeze` sets `rebuild="local"` on every repository of each project in the
  unit; `unfreeze` removes the attribute. Only that attribute changes; the rest
  of the live meta is written back as fetched.
- Both are idempotent and print one line per project: changed, already in that
  state, or not present on this instance (instances build a slice of the tree).
- `--dry-run` prints what would change.

### 5.3 Keeping the freeze through `sync push`

Today `sync push` rewrites project meta from `project.yaml` whenever the
managed subset differs. Repository attributes are not part of that comparison,
so an unrelated meta change would drop the attribute.

Change: when `sync push` writes project meta, each repository in the new meta
takes over the `rebuild` attribute of the live repository with the same name.
A repository that is new in a project whose existing repositories are all
`local` is created with `rebuild="local"` too, so the project stays frozen.
`rebuild` stays out of the "is the meta different" comparison.

### 5.4 Aggregates

`BuildFlags: aggregate-checklocal` is added permanently to the prjconf of every
project that can be part of a frozen unit and holds `_aggregate` packages. It
has no effect unless a repository is `local`. Where exactly the line goes in
the prjconf composition is the builder's call.

### 5.5 Late fixes: staged propagation in `sync push`

After `sync push` has uploaded sources, for the packages it actually changed:

1. **Seeds.** Every package this sync changed, in any project, frozen or not
   (author's call). A fix in `common:deps`, or in `ppg:staging:18` while only
   `ppg:staging:18:extras` is frozen, must reach the frozen unit the same way
   as a fix inside it.
2. **Closure.** Everything that depends, directly or indirectly, on a seed:
   build dependencies between packages, packages installed into images, and
   aggregates (edges from the local `_aggregate` files). The closure is
   followed through non-frozen projects too, but only members in frozen
   projects are triggered; OBS rebuilds the non-frozen ones itself. Non-frozen
   members on the way to a frozen one are still waited for in step 3.
   The graph must be exact here (author's call): the PR flow's helpers
   (`_fetch_combined_depinfo`, `_fetch_image_pkg_deps`) read one repository and
   architecture per project and swallow fetch errors, which is harmless there
   but would ship a stale binary here. For propagation, take the union over
   every repository and architecture, and when dependency data for a frozen
   project cannot be fetched, trigger every package in that project instead.
3. **Stages.** Group the closure by project and order the projects by their
   dependencies (unit root before its `tarballs` and `containers` children).
   - Wait until every seed (and every non-frozen closure member ahead of the
     stage) is seen by the scheduler: its status is pending
     (scheduled, blocked, dispatching, building, finished, signing) or it has
     already been rebuilt, on every repository and architecture where it
     builds. Each architecture has its own scheduler.
   - Trigger the dependents in the first project with `cmd=rebuild`. Within one
     project they can go at once; the scheduler orders them.
   - Wait until those are seen the same way, then trigger the next project.
4. **Timeout.** If a wait does not complete within a short timeout, print a
   warning and continue with the next stage. That falls back to the
   all-at-once behaviour, which passed in testing, rather than leaving
   dependents untouched.
5. `--dry-run` prints the seeds and the staged plan and triggers nothing.
6. **Recovery** (author's call). The propagation is also available on its own:
   `percona-obs build propagate <project> <package> [...]` runs steps 2 to 4
   for the given seeds. If `sync push` fails after uploading and before
   propagation finishes, the failed CI run is the signal, and its log prints
   the exact `build propagate` command to run. A later `sync push` would see
   nothing changed and would not repeat the propagation by itself.

**Project meta and prjconf changes** (author's call). A sync that changes the
prjconf or repository paths of a frozen project rebuilds nothing, as under a
normal OBS prjconf macro change. `sync push` prints a warning naming the
project, so the maintainer can run `build propagate` or unfreeze if the change
needs a rebuild.

A sync that changes nothing in a frozen project, or touches no frozen project,
does no extra work beyond reading the freeze state from meta it already fetches.

### 5.6 Visibility

- `sync push` prints a notice for every frozen project it touches.
- The nightly `sync-main` run emits a GitHub warning annotation listing frozen
  units, so a forgotten freeze shows up every day.

### 5.7 Workflow

`.github/workflows/obs-freeze.yml`, `workflow_dispatch` only:

- `units`: release unit roots, space-separated (same form and validation as
  `obs-release-cut.yml`).
- `action`: choice, `freeze` or `unfreeze`.

It runs one leg per entry of `vars.OBS_INSTANCES` with that instance's profile
and credentials, like `sync-main.yml`, and calls the command from 5.2. The job
summary shows the per-project result for each instance. It has its own concurrency group per instance
(author's call). Sharing `sync-main`'s group was rejected: GitHub keeps one
pending run per group, so a freeze and a sync would cancel each other's queued
runs. Instead the command re-reads the meta after writing and fails if the
attribute is not as requested, and `sync push` takes the attribute from the
live meta it reads immediately before its own write. The remaining window is
the time between that read and write; the nightly annotation (5.6) would show
a freeze lost that way.

### 5.8 Interaction with the release flow

- `sync release` on a frozen unit: drain and green check behave as today
  (packages report real states). Its build-disable and restore rewrite only
  `<build>`, so the `rebuild` attribute is untouched.
- Release mirrors and pre-release projects are not part of a unit's freeze.

## 6. Constraints

- `isv` is production: no write with `-P isv` outside the workflow without
  `--dry-run`.
- After every code change: `venv/bin/black percona_obs/` and `venv/bin/pyright`.
- Commits use `git commit -s`, no AI attribution.

## 7. Left to the builder

- Module layout (a new module beside `release_freeze.py` is suggested, since
  that one is specific to the `sync release` copy).
- Where the `aggregate-checklocal` line enters the prjconf composition.
- Exact timeout and polling interval for the stage waits.
- How the nightly annotation obtains the list of frozen units.
- Unit tests: the meta transform, attribute carry-over on meta writes, closure
  and stage computation, the wait/timeout logic, all against fakes.

## 8. Verification before first production use

- Labs rehearsal on a real unit: freeze, confirm an upstream rebuild does not
  propagate, merge a trivial fix and confirm packages, images and aggregates
  pick it up, run `sync release --dry-run`, unfreeze.
- Confirm that adding `BuildFlags: aggregate-checklocal` to a prjconf does not
  itself start rebuilds.
- build.opensuse.org: freeze one low-traffic unit and confirm an upstream
  rebuild does not propagate, before relying on it for a release.

## 9. Changes made during implementation

Status: implemented on branch `unit-build-freeze`. Where this section and the
text above disagree, this section describes the code.

- **Stage order (5.5 step 3).** Stages follow the real dependency graph;
  projects that depend on each other are triggered in one stage. The project
  order from repository paths is only a tie-break, and an aggregate that copies
  a package from its own project is triggered after that package.
- **Changed packages (5.5 step 1).** A changed package in a frozen project that
  depends on another changed package is itself re-triggered after the other one
  is seen, because its own upload may have built against the old binaries.
- **Partly frozen projects (5.1).** A project where only some repositories
  carry `rebuild="local"` is propagated into like a frozen one.
  `project freeze-status` reports it as `partial`.
- **"Seen by the scheduler" (5.5 step 3)** has one rule per kind of package: a
  changed package when its newest job was built from the current source; a
  package the tool triggered when its job record moved since just before the
  trigger (for aggregates, which have no job, when its binary list changed); a
  package OBS rebuilds by itself when its newest job became ready after the
  newest changed-package commit. In doubt the answer is "not seen".
- **Early exit.** Dependency data is not fetched when no changed package's
  project is a frozen project, one of their repository-path projects, or an
  `_aggregate` source of those.
- **Commands.** `project freeze-status [--github-warning]` lists frozen units.
  `build propagate` takes `<obs_project>/<package>` arguments with full OBS
  project names. The recovery command printed in logs carries the profile and
  the resolved `-A`/`-R`.
- **Known gap.** A frozen unit that aggregates from a project that is not also
  one of its repository paths is not triggered when that project is rebuilt
  because of a change elsewhere.
- **Not done.** Rebuilds the tool triggers are not listed in the sync report.
  Release projects created from a frozen unit carry a copied `rebuild`
  attribute; builds are disabled there, so it has no effect.
