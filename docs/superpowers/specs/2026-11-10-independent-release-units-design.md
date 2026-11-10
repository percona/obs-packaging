# Independent release units and release pruning

Date: 2026-11-10
Status: approved design, not yet implemented

Supersedes the "full staging snapshot" release scope of
`2026-09-02-release-process-v2-design.md` and the repository path rewriting
of `2026-10-13-prerelease-project-release-flow-design.md` (§ pre-release meta).
Everything else in those specs (two hops, freeze, record check, tags,
`source_commit`) stays as it is.

## Problem

Releasing `ppg:staging:<major>` releases every subproject below it. For
`ppg:staging:18` that is the top project plus `containers`, `tarballs`,
`extras` and `extras:containers`; a release of `ppg:staging:16` would also
pull in `tde`.

`extras` and `tde` are separate products with their own cadence. Bundling
them means a main release is blocked by an unrelated red extras build, and an
extras-only fix needs a full main release.

Two further problems surface once units are split:

- Release mirrors rewrite `subproject:` repository paths to the release
  namespace. A nested unit would then path to its parent's release project,
  which may not exist (`ppg:releases:16` does not).
- The copy only ever adds. A package or subproject removed from staging stays
  in the release project forever; `warn_orphans` reports stale subprojects
  and stale packages are not detected at all.

## Goals

1. A release of `ppg:staging:<major>` covers the top project, `containers`
   and `tarballs`, and nothing else.
2. `extras` (with `extras:containers`) and `tde` are released on their own,
   with their own record, tag and changelog.
3. A release project has no dependency on any other release project existing.
4. After a release hop, the target holds exactly what the source holds:
   removed packages and removed subprojects are deleted from the target.

## Non-goals

- Checking that a nested unit was built against the released state of its
  parent. That is the releaser's responsibility.
- Removing binaries of a package that still exists but stopped building for
  one repository.
- Moving or renaming existing release projects on OBS.

## Design

### 1. Release unit

A **release unit** is a staging project plus its direct children named
`containers` and `tarballs`. Every other subproject is the root of its own
unit, by the same rule.

| Unit root | Members | Release project |
|---|---|---|
| `ppg:staging:18` | top, `containers`, `tarballs` | `ppg:releases:18` |
| `ppg:staging:18:extras` | `extras`, `extras:containers` | `ppg:releases:18:extras` |
| `ppg:staging:16:tde` | `tde` | `ppg:releases:16:tde` |
| `ppg:staging:common` | per the same rule | `ppg:releases:common` |

The bundled names are a constant in the tool (`BUNDLED_SUBPROJECTS =
("containers", "tarballs")`), not configuration. `release_scope.py` gains
`release_unit_members(source_path, source_project_id)`, which returns the
member projects of a unit. Every place that walks the release source with
`find_projects` uses it instead:

- `collect_release_subprojects` (mirror pairs for both hops),
- freeze, drain and green checks,
- `collect_release_scope` (aggregate and path-prefix sources),
- `tree_has_server_package` (release-id mode),
- changelog and OBS data collection in `project release`,
- the mirror writer.

"A unit member without a mirror is a hard error" is unchanged, now limited to
unit members.

`ppg:staging:common` must be checked during implementation: if it has
subprojects other than `containers`/`tarballs` that its release ships today,
they become units of their own and the plan must list them.

### 2. Records, ids and tags

`project release <unit root>` accepts any unit root under a staging tier,
not only `<product>:staging:<version>`. The release directory mirrors the
source path below `staging`:

    ppg:staging:18         → root/ppg/releases/18/
    ppg:staging:18:extras  → root/ppg/releases/18/extras/
    ppg:staging:16:tde     → root/ppg/releases/16/tde/

Each unit directory holds its own `release.yaml` (`project:` names the unit
root), `CHANGELOG.md`, `project.yaml` and one mirror `project.yaml` per
bundled child. `--release-name` keeps overriding the top directory name only.

Release id of a nested unit: the unit's path below the major, joined with
`-`, as a prefix of the id the unit would otherwise get.

    ppg:staging:18:extras → extras-18.6-1  → tag ppg/extras-18.6-1
    ppg:staging:16:tde    → tde-16.11-1    → tag ppg/tde-16.11-1

Both units carry their own server package, so the `MAJOR.MINOR` part comes
from that package as built in the unit root, and `N` counts the unit's own
releases of that minor. A nested unit without a server package uses counter
mode (`<prefix>-N`). Main ids are unchanged. The tag stays `<product>/<id>`,
so `release_id_from_tag` and the CI tag handling need no format change.

A nested unit can be released whether or not its parent has ever been
released, and nothing compares its state to the parent's.

### 3. Mirror metadata without internal paths

Release and pre-release projects never build (`build: false`), so repository
paths into other projects of the same root are unused. The mirror writer
drops every `subproject:` path and keeps `project:` paths (base distros,
EPEL, UBI) in their original order; OBS still takes the repository's base
configuration and publish type from those.

Every repository in the existing 17/18 mirrors keeps at least one `project:`
path. A repository left with no path at all is a hard error in the mirror
writer, naming the repository.

Removed as a consequence:

- `_rewrite_subproject_paths` and its call in `_write_release_tree`,
- `branch_rootprj` / `active_projects` / `branch_fallbacks` in
  `apply_mirror_meta` and `release_tree`,
- the second `_apply_project_config` pass for paths OBS stripped.

Consumers checked: release QA `EXPECTED_VERSIONS` reads the staging
structure for a mirror, and `project install` uses repository names only.
Mirror `qa:` block rewriting is unaffected.

Existing mirrors are rewritten the next time their unit is released.

### 4. A unit leaves other units alone

- `project release ppg:staging:18` neither rewrites nor deletes
  `root/ppg/releases/18/extras/`; the mirror writer's stale-directory cleanup
  is limited to directories that are not themselves a mirror of another unit
  (see § 5 for how those are recognised).
- The main `CHANGELOG.md` no longer lists extras packages or extras images;
  they are listed in the nested unit's changelog.

### 5. Prune after copy

`release_tree` (shared by `sync prerelease` and `sync release`) prunes the
target once the copy of the whole unit has been verified.

**Subprojects.** A target OBS subproject is stale when the local release tree
has no `project.yaml` for it. Stale subprojects are deleted recursively,
deepest first. This replaces `warn_orphans`.

A nested unit keeps its mirror directory, so it is never stale from its
parent's point of view; this also covers `releases/{17,18}/extras`, which
exist today without a `release.yaml`. Retiring a nested unit is `git rm` of
its release directory: the parent's next release removes the OBS project.

**Packages.** For the top project and each bundled child: packages listed in
the target OBS project but not in the hop's source OBS project are deleted
(staging for hop 1, the pre-release for hop 2). The source listing reflects
the instance slice, so no slice logic is needed, and hop 2 still does not
read the staging tree.

**Guards.**

- Nothing is deleted unless `verify_release_landed` passed for every project
  of the unit. With `--verify-timeout 0` the prune is skipped with a warning.
- An empty source package list, or a failed listing, aborts the prune with an
  error.
- `--dry-run` prints every deletion and performs none.
- Hop 1 writes the packages and subprojects that hop 2 will delete from the
  release project into its report, and the PR comment lists them, so removals
  are reviewed before merge.

Deleting a package from a release project removes its binaries from the
published repository. That is the intent; it cannot be undone other than by
releasing the package again.

### 6. Migration

No one-off step.

- `ppg:releases:{17,18}:extras` keep their content. The first
  `project release ppg:staging:<V>:extras` adds `release.yaml` and
  `CHANGELOG.md` to the existing mirror directory and yields
  `extras-<minor>-1`. Its changelog baseline is what the release project
  holds on OBS at that time.
- The next main release of 17/18 rewrites the main mirrors without internal
  paths, drops extras from its changelog, and prunes the packages that are
  stale in `ppg:releases:17` and `ppg:releases:18` today.
- `root/ppg/releases/16/tde/` is created by the first `tde` release.

### 7. CI

- `obs-release-pr.yml` path filter and `release_pr.py classify` match
  `release.yaml` at any depth below `root/*/releases/`. A PR may carry
  several units; each gets its own populate, tag and hop 2. "One in-flight
  release PR per `release.yaml`" is unchanged.
- "Release-only PR" detection is path-prefix based already and needs no
  change.
- `obs-pr-cleanup.yml` reads the last entry of every changed `release.yaml`,
  nested ones included.
- Release QA fan-out discovers lanes from the pre-release subprojects, so a
  unit's PR runs that unit's lanes only.
- `update_version_lists.py` and any script that globs
  `releases/*/release.yaml` must be checked for the nested depth.

## Error handling

| Situation | Behaviour |
|---|---|
| `project release` on a bundled child (`ppg:staging:18:containers`) | Error: not a unit root, names the unit it belongs to |
| Unit member without a mirror | Hard error (unchanged) |
| Mirror repository left without any path | Hard error in the mirror writer |
| Source package listing empty or failing | Prune aborted, non-zero exit; the copy itself has already succeeded and is safe to re-run |
| Package delete fails | Reported, remaining deletes still attempted, non-zero exit |

## Testing

pytest, no OBS traffic (listing and delete calls stubbed):

- unit membership for a major, `extras`, `tde` and `common`;
- release directory and id derivation for nested units, including the
  per-unit counter and counter mode;
- mirror writer: `subproject:` paths dropped, order of the rest kept,
  path-less repository rejected, nested unit directory untouched by the
  parent release;
- prune: stale packages and subprojects computed, nested unit protected,
  guards (verify skipped, empty source list, dry-run);
- `release_pr.py classify` with nested and mixed `release.yaml` changes.

End to end: `sync prerelease --dry-run` and `sync release --dry-run` for
`ppg:releases:18` and `ppg:releases:18:extras`, then a labs rehearsal before
the first production release (existing runbook).

## Documentation

`docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md` (release hops,
workflows 3 and 6), `root/README.md` and `root/ppg/releases/README.md`.
