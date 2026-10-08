# PG-independent tools built once: `ppg:staging:tools`, cross-version images and their release

**Date:** 2026-10-08
**Status:** approved by the user in brainstorming (2026-10-07/08); plan pending approval
**Scope:** three PRs. PR A adds `ppg:staging:tools` and the tool changes. PR B
switches the five per-major packages to aggregates, moves the pgbouncer and
pgbackrest images to `ppg:staging:containers`, and adds the cross-version
containers release flow. The first `ppg:releases:containers` release is a
normal release PR produced by `project release` afterwards.

## Background

Every per-major staging project (`ppg:staging:14` … `18`) builds its own copy
of five components whose binaries do not depend on the PostgreSQL major:
`percona-pgbouncer`, `percona-pgbadger`, `percona-haproxy`,
`percona-pgbackrest` and `percona-patroni`. The sources are already shared in
git (`root/ppg/staging/_shared/<pkg>` plus per-major symlinks), so the five
builds per component are byte-for-byte different but functionally identical,
and each major publishes its own copy under the same NEVR. PGDG builds the
same components once, in `rpm/redhat/main/common`, and ships them to every
major's repository.

The per-major `ppg:staging:<V>:containers` projects likewise build five
identical `percona-pgbouncer` and `percona-pgbackrest` images each.

The repository already has the mechanism this design extends: `etcd`,
`ydiff`, `geos`, `proj`, `sfcgal` and the python3 stack are built once in
`ppg:common:deps` and reach every major through an `obs/_aggregate` file;
release snapshots copy aggregated binaries with `osc release`, which the
17.11-1 and 18.6-1 releases proved. `ppg:staging:containers` already exists
as the cross-version image project (upgrade image) but has no release
counterpart.

## Decisions taken in brainstorming

1. **Candidate rule: PGDG's.** A package moves when its binary package name
   carries no PG major. That is the five listed above. pgbackrest links libpq
   and patroni's Debian package depended on a server; both move.
   `pgpool-II` (`-pgNN` package, server extensions), `pg_gather`,
   `pg-telemetry`, `postgresql-common` and the `ppg-server*` meta packages
   stay per-major.
2. **PG major for the tools project: explicit pin.** `PG_MAJOR_VERSION: 18`
   in `root/ppg/staging/tools/macros.yaml`, bumped by hand in the PR that
   adds a new GA major to staging. No derivation from the tree.
3. **Release coupling: tools joins the freeze.** `sync release` extends its
   quiesce / green / build-freeze scope to the local aggregate sources of the
   release source tree, restricted to the aggregated packages. The gap between
   QA sign-off and the `osc release` copy is not tooled today for anything
   (including `ppg:common:deps`) and stays a process rule.
4. **Where the single build lives: a new `ppg:staging:tools`**, not
   `ppg:common:deps` (that project is `publish: false`, has no PG path and
   mixes third-party libraries with shipped components).
5. **patroni Debian: drop the server Depends**, matching upstream Debian and
   our own RPM spec.
6. **Images move too**, to the existing `ppg:staging:containers`, and that
   project gets a release counterpart `ppg:releases:containers` in this
   effort, tagged with a plain counter.
7. **Two content PRs** (A then B) so the published staging repos never go
   through a window with the five packages missing while tools builds.

## 1. Tree layout and project config

New directory `root/ppg/staging/tools/` → OBS project `ppg:staging:tools`, a
direct child of staging. `root/ppg/staging/subprojects.yaml` therefore folds
in the shared repository set (all majors share the root `project.yaml`
repositories), the debuginfo map, the `ppg:common:deps` path-prefix and the
PPG-wide project config. The project's own files:

- `project.yaml`: title, description, and one extra `path-prefix` entry
  `subproject: ppg:staging:18`, `repository: "%_repository"`, so pgbackrest
  resolves `percona-postgresql18-devel` (RPM) and `libpq-dev` (Debian) from
  our own packages. No `qa:` block. `project-config` additions only if a
  moved package turns out to need one on a given repository (decided during
  PR A from the first build results; none is expected).
- `macros.yaml`: `PG_MAJOR_VERSION: 18` with the bump rule as a comment.
  No `PG_VERSION`, so no computed `PPG_RELEASE` counter (none of the five
  packages references it).
- The five package directories with `rpm/`, `debian/` and `obs/_service`
  exactly as in `_shared` today.

In `root/ppg/staging/_shared/`, each of the five directories shrinks to a
single file, `obs/_aggregate`:

```xml
<aggregatelist>
  <aggregate project="${OBS_ROOTPRJ}:ppg:staging:tools">
    <package>percona-pgbouncer</package>
  </aggregate>
</aggregatelist>
```

The per-major symlinks (`root/ppg/staging/<V>/<pkg> -> ../_shared/<pkg>`)
stay, so every major still lists the package and its published repositories
stay self-contained. The devel tier does not build any of the five and needs
nothing. `ppg:staging:19` is not touched either: it is a devel-only major
today and gets the aggregates when it enters staging.

## 2. percona-obs changes

One behavioural change, the rest is verification of paths that already exist.

### 2.1 Release freeze scope

`cmd_sync_release` builds `freeze_scope = [source] + source_subprojects`.
It will additionally include two kinds of extra sources:

- **Aggregate sources**, package-scoped: every *local* aggregate source
  referenced by an `_aggregate` file under the release source tree (resolved
  with the existing `_resolve_aggregate_source`; external aggregates
  ignored). For these, `wait_for_quiesce` and `assert_all_green` consider only
  the aggregated packages (an unrelated red package in `ppg:common:deps` must
  not block a release) and `freeze_builds` / `restore_builds` disable only
  those packages (package meta `build disable`, restored to the exact prior
  meta).
- **Path-prefix sources**, whole-project: when the release source is a
  container project, the `subproject:` entries of its repository paths
  (`ppg:staging:tools`, `ppg:common:deps`, the majors) are treated exactly
  like the release source project itself today, since an image may consume
  any package of those projects. The containers release is short and the
  per-major projects are build-frozen only for the copy.

The derivation is a pure function over the tree (`list[(obs_project,
package)]`) so it is unit-testable without OBS. `--dry-run` prints the
extended scope.

### 2.2 Cross-version release support in `project release`

`cmd_project_release` currently derives `release_id` from the built
`percona-postgresql` version. For a source project without that package it
derives the next counter from `release.yaml`: `release_id = N+1` where N is
the number of existing entries, tag `ppg/containers-<N+1>`. Everything else
(materialised standalone `project.yaml` with `build: false`, CHANGELOG,
release PR) is reused unchanged. The materialised `project.yaml` registry
paths render to `ppg/releases/containers/<ubi>`.

### 2.3 Workflows

- `obs-release.yml`: the tag validation accepts a second shape,
  `<product>/<name>-<N>`, and maps it to `<product>:releases:<name>`; the
  existing `<product>/<major.minor>-<N>` shape is unchanged. The staging
  lock logic is unchanged.
- `obs-pr-cleanup.yml` tags from any changed `release.yaml`, no change.

### 2.4 Verified unchanged (covered by tests, not code changes)

- `_rewrite_aggregate_for_branch` rewrites an aggregate whose source is a
  sibling subproject (`${OBS_ROOTPRJ}:ppg:staging:tools`) to the PR root
  when that package is promoted in the PR, exactly as it does for
  `ppg:common:deps` today.
- The branch decision promotes a changed `tools/<pkg>` (content check) and
  leaves unchanged ones aggregated.
- `_follow_aggregate` yields the tools package version for CHANGELOG rows.
- `_collect_release_subprojects` does not treat `tools` as a subproject of
  a major, so per-major releases do not try to mirror it.
- `project verify` (offline and live-check) resolves the new path-prefix
  target and the aggregate target.
- sync-main discovers `root/ppg/staging/tools` like any project directory;
  aggregates need no build ordering.

## 3. Package-level changes

- **percona-patroni, Debian**: remove
  `percona-postgresql-%!{PG_MAJOR_VERSION} | postgresql-%!{PG_MAJOR_VERSION}`
  from `Depends`; add `postgresql` to `Suggests` (upstream Debian has exactly
  this). The per-major `percona-ppg-server-ha-NN` meta package keeps pulling
  the matching server, so installs through the meta package are unchanged.
- **percona-pgbackrest**: no file change. The RPM `Requires: postgresql-libs`
  is an unversioned capability every major's libs package provides; a
  pgbackrest linked against libpq 18 installs on any major (what PGDG ships).
- **pgbouncer, pgbadger, haproxy**: no file change.
- **No changelog or Release bump**: OBS overrides spec `Release:` with
  `<CI_CNT>.<B_CNT>` (root prjconf), so nothing in the sources can raise the
  published counter. Counters restart in the tools project; the majors list an
  equal-version, lower-counter build until the next upstream bump. Staging-only
  cosmetic effect, documented in root/README.md.

Side effect worth recording: the five packages become byte-identical across
majors, removing a latent file-conflict risk when two majors' repositories
are enabled on one host.

## 4. Container images

- `root/ppg/staging/_shared/containers/percona-pgbouncer` and
  `percona-pgbackrest` move to `root/ppg/staging/containers/`; the per-major
  symlinks under `root/ppg/staging/<V>/containers/` are deleted.
- `ENV PG_VERSION` / `ARG PG_VERSION` are dropped from both Dockerfiles;
  neither tool uses them. `LABEL release="1"` and the `#!BuildTag` lines stay.
- `ppg:staging:containers` keeps `PG_MAJOR_VERSION: 18` (upgrade target and
  the `Prefer: percona-postgresql18-libs` pick that pgbackrest's libpq
  resolves through). Its repository paths already list every major,
  `ppg:common:deps` and the UBI projects; `ppg:staging:tools` is added after
  the majors so `percona-pgbouncer` / `percona-pgbackrest` resolve from the
  tools build (the majors only hold aggregates of it).
- Registry path changes from `ppg/staging/<V>/containers/<ubi>/<image>` to
  `ppg/staging/containers/<ubi>/<image>`: one image per UBI flavour instead
  of five identical ones. The existing `qa:` block of the containers project
  is unchanged.

## 5. Cross-version containers release

- **Tree**: `root/ppg/releases/containers/` with `release.yaml`
  (`project: ppg:staging:containers`, `releases: [ppg/containers-1, …]`),
  `CHANGELOG.md` and a standalone `project.yaml` (`build: false`, three ubi
  repos) written by the first `project release ppg:staging:containers` run (the
  release PR), not by PR B. OBS project
  `ppg:releases:containers`.
- **Contents**: the upgrade image, `percona-pgbouncer`, `percona-pgbackrest`.
- **Tag**: `ppg/containers-<N>`, N a plain counter (user decision).
- **Freeze**: Section 2.1 covers the path-prefix sources.
- **Release QA**: the project's `qa:` block runs against
  `ppg/releases/containers/<ubi>` as per-major release QA does today.
- **Per-major releases**: `ppg:releases:17:containers` and `18:containers`
  stop carrying the two images from their next release; their CHANGELOG gets
  a one-line pointer to the containers release. Already-released snapshots
  are untouched.

## 6. Migration order

**PR A — add the tools project.** `root/ppg/staging/tools/` with the five
packages copied from `_shared`, the patroni Depends change, the freeze-scope
and `project release` changes, the workflow tag shape, tests and docs. The
majors are untouched. After merge, sync-main creates and builds
`ppg:staging:tools`; compare its binaries against a major's current build
(`rpm -qp --requires --provides`, `dpkg-deb -I`) to confirm only the libpq
linkage can differ.

**PR B — switch consumers.** The five `_shared` directories become
aggregate-only; the image move (Section 4); the containers
project path addition (Section 5). OBS swaps each major's built package for the aggregate
and republishes; old per-major build results are dropped by OBS.

**Release PR** — `project release ppg:staging:containers` produces the first
`ppg/containers-1` release PR; merging it dispatches obs-release as usual.

Both content PRs go through the normal flow on the `percona` remote with the
`obs-sync` label: PR A builds tools in `pr-N:ppg:staging:tools`; PR B's
aggregates and images are rewritten to the PR root and `qa-packages` runs
on every major from the tools binaries.

## 7. Testing

- **Unit tests** (`tests/`): freeze-scope derivation on a fixture tree
  (aggregate and non-aggregate packages, an external aggregate to ignore, a
  container project with path-prefix sources); `release_id` counter
  derivation for a project without `percona-postgresql`; tag-shape parsing.
- **Offline checks**: `project verify --offline`, the project-config check
  workflow, `black` and `pyright` on both PRs.
- **PR OBS root**: PR A, all tools packages green on every repository; PR B,
  every major's five packages show as aggregates pointing at the PR tools
  project, both images build in the PR containers project, `qa-packages`
  green on all majors.
- **Release dry-run** after PR B merges: `sync release --dry-run
  ppg:releases:18` lists `ppg:staging:tools` and `ppg:common:deps` with the
  aggregated package names; `sync release --dry-run ppg:releases:containers`
  lists the path-prefix sources.

## Out of scope / follow-ups

- The open package-level QA blocks PR (#119) must treat aggregate packages as
  present in the consuming major; noted there, not changed here.
- `ppg:staging:19` gets the aggregates when it enters staging.
- Moving `percona-pgbadger`, `percona-haproxy` or `patroni` images (none
  exist today).
