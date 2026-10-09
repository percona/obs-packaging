# PG-independent tools built once: `ppg:staging:common:tools`, cross-version images and their release

**Date:** 2026-10-08, revised 2026-10-09
**Status:** approved by the user in brainstorming (2026-10-07/08, revision 2026-10-09); plan being revised
**Scope:** three PRs. PR A adds `ppg:staging:common:tools` and the tool changes
(PR #123, reworked in place). PR B switches the five per-major packages to
aggregates, moves the cross-version image projects under `common/`, and puts
the pgbouncer/pgbackrest images in `common/tools/containers`. The first
`ppg:releases:common` release is a normal release PR produced by
`project release ppg:staging:common` afterwards.

**Revision 2026-10-09.** The first version placed the tools project at
`ppg:staging:tools` and released the cross-version images from a
`ppg:releases:containers` unit. The user proposed a tier-level `common`
parent for every cross-version product piece; Sections 1, 2.1, 2.2, 4, 5, 6
and 7 were rewritten for it. `ppg:common:deps` is unaffected.

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
17.11-1 and 18.6-1 releases proved. Two cross-version image projects already
exist (`ppg:staging:containers` with the upgrade image,
`ppg:staging:extras:containers` with the custom upgrade image) but neither
has a release counterpart.

## Decisions taken in brainstorming

1. **Candidate rule: PGDG's.** A package moves when its binary package name
   carries no PG major. That is the five listed above. pgbackrest links libpq
   and patroni's Debian package depended on a server; both move.
   `pgpool-II` (`-pgNN` package, server extensions), `pg_gather`,
   `pg-telemetry`, `postgresql-common` and the `ppg-server*` meta packages
   stay per-major.
2. **PG major for the tools project: explicit pin.** `PG_MAJOR_VERSION: 18`
   in `root/ppg/staging/common/macros.yaml` (the tier prjconf references it at
   the `common` level; `tools` inherits it) (amended 2026-10-09 during
   execution), bumped by hand in the PR
   that adds a new GA major to staging. No derivation from the tree.
3. **Release coupling: tools joins the freeze.** `sync release` extends its
   quiesce / green / build-freeze scope to the local aggregate sources of the
   release source tree, restricted to the aggregated packages. The gap between
   QA sign-off and the `osc release` copy is not tooled today for anything
   (including `ppg:common:deps`) and stays a process rule.
4. **Where the single build lives: the product tier**, not `ppg:common:deps`
   (that project is `publish: false`, has no PG path and mixes third-party
   libraries with shipped components).
5. **patroni Debian: drop the server Depends**, matching upstream Debian and
   our own RPM spec.
6. **Images move too**, into the tools project's own image subproject, and
   the cross-version pieces get one release unit tagged with a plain counter.
7. **Two content PRs** (A then B) so the published staging repos never go
   through a window with the five packages missing while tools builds.
8. **(2026-10-09) Tier-level `common` parent.** Every cross-version product
   piece of a tier lives under `ppg:<tier>:common:` — `containers`, `tools`,
   `tools:containers`, `extras:containers`. `ppg:common:deps` (and
   `common:deps:*`) stay tier-less and shared.
9. **(2026-10-09) One release unit** `ppg:releases:common`, tag
   `ppg/common-<N>`, covering all four subprojects at once.
10. **(2026-10-09) `devel/common` only when needed**: the layout allows it and
    the docs describe it, but no directory is created until a devel package
    or image needs a devel-tier tool or cross-version image.

## 1. Tree layout and project config

```
root/ppg/staging/
├── 14 … 19/                 unchanged (containers, extras, tarballs per major)
├── common/
│   ├── project.yaml         package-less parent; does NOT opt out of inherited repositories
│   │                        (amended 2026-10-09 during execution, see below)
│   ├── macros.yaml          PG_MAJOR_VERSION: 18
│   ├── subprojects.yaml -> ../subprojects.yaml
│   ├── tools/               ppg:staging:common:tools                 (PR A)
│   │   ├── project.yaml     path-prefix to ppg:staging:%!{PG_MAJOR_VERSION} only
│   │   ├── macros.yaml      bump-rule comment only
│   │   ├── percona-pgbouncer/ … percona-patroni/   five real package dirs
│   │   └── containers/      ppg:staging:common:tools:containers      (PR B)
│   ├── containers/          ppg:staging:common:containers            (PR B, from staging/containers)
│   └── extras/
│       └── containers/      ppg:staging:common:extras:containers     (PR B, from staging/extras/containers)
└── extras/                  removed in PR B (its only child moved)
```

- `common/project.yaml` is a package-less parent that does NOT opt out of
  inherited repositories (amended 2026-10-09 during execution). An opt-out
  would reset the repository list before `common/subprojects.yaml`, which
  declares none, leaving `tools` with zero repositories. So
  `ppg:staging:common` renders the root repositories with no packages, like
  `ppg:staging` itself.
- `common/subprojects.yaml` is a symlink to `../subprojects.yaml` (the
  pattern `devel/subprojects.yaml` already uses). A `subprojects.yaml`
  applies to the direct children of its directory only, so without the link
  `common/tools` would miss the PPG repository set, the debuginfo map, the
  `ppg:common:deps` path and the PPG-wide prjconf. The image projects under
  `common/` opt out of inheritance as every image project does, so the link
  does not affect them.
- `common/tools/project.yaml`: title, description, one `path-prefix` entry
  `subproject: ppg:staging:%!{PG_MAJOR_VERSION}`, `repository: "%_repository"`,
  so pgbackrest resolves `percona-postgresql18-devel` (RPM) and `libpq-dev`
  (Debian) from our own packages. No `qa:` block. `project-config` additions
  only if a moved package turns out to need one on a given repository
  (decided from the PR A build results; none is expected).
- `common/macros.yaml`: `PG_MAJOR_VERSION: 18` (amended 2026-10-09 during
  execution); `common/tools/macros.yaml` holds only the bump-rule comment. No `PG_VERSION`, so no computed `PPG_RELEASE` counter.
- The five package directories with `rpm/`, `debian/` and `obs/_service`
  exactly as in `_shared` today — without `package.yaml`: the `qa:` lanes it
  holds (component-generic-parallel, PG-2830) test the component against
  each major's repository and stay per-major in `_shared/<pkg>/package.yaml`
  next to the aggregate (amended 2026-10-09 during execution).

In `root/ppg/staging/_shared/`, each of the five directories shrinks to
`obs/_aggregate` plus its existing `package.yaml` (QA lanes):

```xml
<aggregatelist>
  <aggregate project="${OBS_ROOTPRJ}:ppg:staging:common:tools">
    <package>percona-pgbouncer</package>
  </aggregate>
</aggregatelist>
```

The per-major symlinks (`root/ppg/staging/<V>/<pkg> -> ../_shared/<pkg>`)
stay, so every major still lists the package and its published repositories
stay self-contained. The devel tier does not build any of the five and gets
no `common/` (decision 10). `ppg:staging:19` keeps building the five tools from the same sources (its
links point at `common/tools/<pkg>` and render with 19's macros, e.g. haproxy
2.8.28) and gets the aggregates when it enters the aggregate scheme.

`root/ppg/releases/common/` mirrors `root/ppg/staging/common/` the way
`releases/17/` mirrors `staging/17/`: `release.yaml`, `CHANGELOG.md`,
`project.yaml` and one mirror per subproject, all written by
`project release ppg:staging:common` (Section 5).

## 2. percona-obs changes

### 2.1 Release freeze scope

`cmd_sync_release` builds `freeze_scope = [source] + source_subprojects`.
It additionally includes two kinds of extra sources (module
`percona_obs/release_scope.py`, a pure function over the tree):

- **Aggregate sources**, package-scoped: every *local* aggregate source
  referenced by an `_aggregate` file under the release source tree (external
  aggregates ignored; targets whose package directory is missing or out of
  the active instance slice ignored). For these, `wait_for_quiesce` and
  `assert_all_green` consider only the aggregated packages (an unrelated red
  package in `ppg:common:deps` must not block a release; a scoped package
  with no build results at all is a problem, so dry-run and the real freeze
  agree) and `freeze_packages` / `restore_packages` disable only those
  packages (package meta `build disable`, restored to the exact prior meta).
- **Path-prefix sources**, whole-project (amended 2026-10-09 during
  execution: applies only to a release source without a server package;
  PG-major releases keep the aggregate-only scope): for every project under the
  release source (the source itself and its subprojects) that holds
  container images, the `subproject:` entries of its repository paths that
  are in slice, minus the source and its own subprojects, are treated like
  the release source project itself, since an image may consume any package
  of those projects. For a `ppg:releases:common` release that is the five
  majors and `ppg:common:deps` (`tools` is a subproject of the source and is
  already whole); the release is short and those projects are build-frozen
  only for the copy.

`--dry-run` prints the extra sources as `+ <project>  (whole)` /
`+ <project>  (<pkg>, …)`.

### 2.2 Cross-version release support in `project release`

`cmd_project_release` derives `release_id` from the built `percona-postgresql`
version. **Counter mode**: when no `percona-postgresql*` package directory
exists anywhere under the source project tree (project and subprojects, read
from git, not OBS), `release_id = <release_name>-<N+1>` where N is the number
of existing `releases:` entries, so `project release ppg:staging:common` tags
`ppg/common-1`, `ppg/common-2`, …. A PG major whose OBS listing is
transiently empty still fails with the old hard error. Everything else
(subproject mirrors, CHANGELOG with container and non-container subprojects,
release PR) is reused unchanged; `ppg:staging:common` is a plain parent with
subprojects, which is the shape the code already handles. The "source itself
holds images" routing that PR #123 added for a `ppg:staging:containers`
release source is removed.

### 2.3 Workflows

- `obs-release.yml`: the tag validation accepts a second shape,
  `<product>/<name>-<N>`, and maps it to `<product>:releases:<name>`; the
  existing `<product>/<major.minor>-<N>` shape is unchanged. `ppg/common-3`
  therefore releases `ppg:releases:common`. The staging lock logic is
  unchanged.
- `obs-pr-cleanup.yml` tags from any changed `release.yaml`, no change.
- `obs-stale-cleanup.yml` deletes stale **PR** projects only; the orphaned
  production projects of Section 6 are deleted automatically by sync-main's
  orphan cleanup (full-tree sync push), with no manual `osc rdelete`.

### 2.4 Verified unchanged (covered by tests, not code changes)

- `_rewrite_aggregate_for_branch` rewrites an aggregate whose source is a
  sibling subproject (`${OBS_ROOTPRJ}:ppg:staging:common:tools`) to the PR
  root when that package is promoted in the PR, exactly as it does for
  `ppg:common:deps` today.
- The branch decision promotes a changed `common/tools/<pkg>` (content
  check) and leaves unchanged ones aggregated.
- `_follow_aggregate` yields the tools package version for CHANGELOG rows.
- `_collect_release_subprojects` mirrors nested subprojects
  (`tools:containers`, `extras:containers`) as it does `extras:containers`
  under a major today; the changelog label for images in
  `common:tools:containers` is `tools/<flavor>`, distinct from
  `common:containers` images.
- `project verify` (offline and live-check) resolves the new path-prefix
  target and the aggregate target.
- sync-main discovers `root/ppg/staging/common/*` like any project
  directory; aggregates need no build ordering. PR QA discovery iterates the
  PR root's subprojects at any depth.

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

## 4. Container images (PR B)

- `root/ppg/staging/containers/` → `root/ppg/staging/common/containers/`
  (upgrade image) and `root/ppg/staging/extras/containers/` →
  `root/ppg/staging/common/extras/containers/` (custom upgrade image), by
  `git mv`; `root/ppg/staging/extras/` is removed. Their `project.yaml`
  files change only in registry paths and the `qa:` `REPOSITORY` values.
- `root/ppg/staging/_shared/containers/percona-pgbouncer` and
  `percona-pgbackrest` move to `root/ppg/staging/common/tools/containers/`;
  the per-major symlinks under `root/ppg/staging/<V>/containers/` are
  deleted. `ENV PG_VERSION` / `ARG PG_VERSION` are dropped from both
  Dockerfiles; `LABEL release="1"` and the `#!BuildTag` lines stay.
- `common/tools/containers/project.yaml` is a copy of the cross-version
  containers project config (ubi8/ubi9/ubi10, registry base, majors,
  `ppg:common:deps`, UBI projects) with `ppg:staging:common:tools` FIRST among
  the subproject paths (amended 2026-10-09 during execution): OBS takes the
  first path that provides a binary and the majors only aggregate these
  packages, so a tools-only PR would otherwise install production's old copy.
  `percona-pgbouncer` / `percona-pgbackrest` therefore resolve from the tools
  build. It has no `qa:` block (the server-image pipeline does not apply) and
  no `macros.yaml` (`PG_MAJOR_VERSION` is inherited from `common/macros.yaml`).
- Registry paths: `ppg/staging/common/containers/<ubi>/<image>`,
  `ppg/staging/common/tools/containers/<ubi>/<image>`,
  `ppg/staging/common/extras/containers/ubi9/<image>`. One tool image per
  UBI flavour instead of five identical ones.

## 5. Cross-version release

- **Unit**: `ppg:releases:common` with subprojects `containers`, `tools`,
  `tools:containers`, `extras:containers`; `root/ppg/releases/common/`
  (`release.yaml` with `project: ppg:staging:common`, `releases:
  [ppg/common-1, …]`, `CHANGELOG.md`, standalone `project.yaml` and one
  mirror per subproject) written by the first `project release
  ppg:staging:common` run (the release PR), not by PR B.
- **Tag**: `ppg/common-<N>`, N a plain counter (user decision).
- **Freeze**: Section 2.1.
- **Release QA**: each image subproject's `qa:` block runs against its
  `ppg/releases/common/...` registry path as per-major release QA does today.
- **Per-major releases**: `ppg:releases:17:containers` and `18:containers`
  stop carrying the two tool images from their next release; their CHANGELOG
  gets a one-line pointer to the `common` release. Already-released
  snapshots are untouched.

## 6. Migration order

**PR A — add the tools project (PR #123, reworked in place).**
`root/ppg/staging/common/{project.yaml,subprojects.yaml}` and
`common/tools/` with the five packages copied from `_shared`, the patroni
Depends change, the freeze-scope and `project release` changes, the workflow
tag shape, tests and docs. The majors and the existing image projects are
untouched. After merge, sync-main creates and builds
`ppg:staging:common:tools`; compare its binaries against a major's current
build (`rpm -qp --requires --provides`, `dpkg-deb -I`) to confirm only the
libpq linkage can differ.

**PR B — switch consumers and move the images.** The five `_shared`
directories become aggregate-only; the image moves of Section 4. OBS swaps
each major's built package for the aggregate and republishes; old per-major
build results are dropped by OBS. sync-main creates the three moved image
projects at their new names; the old `ppg:staging:containers` and
`ppg:staging:extras:containers` and the per-major `percona-pgbouncer` /
`percona-pgbackrest` image packages become orphans and are deleted
automatically by sync-main's orphan cleanup (full-tree sync push); no manual
`osc rdelete`. Images under the old registry paths disappear on merge; the new
paths are listed in Section 4.
`ppg:staging:16:tde` holds `_link`s to the five staging:16 packages, which are
now aggregates: the PR OBS root must show the tde packages as aggregates with
binaries; if OBS rejects a link to an aggregate, replace the five `_link`s
with `_aggregate` files pointing at tools.

**Release PR** — `project release ppg:staging:common` produces the first
`ppg/common-1` release PR; merging it dispatches obs-release as usual.

Both content PRs go through the normal flow on the `percona` remote with the
`obs-sync` label: PR A builds tools in `pr-N:ppg:staging:common:tools`;
PR B's aggregates and images are rewritten to the PR root and `qa-packages`
runs on every major from the tools binaries.

## 7. Testing

- **Unit tests** (`tests/`): freeze-scope derivation on a fixture tree
  (aggregate and non-aggregate packages, an external aggregate to ignore,
  out-of-slice and missing targets, image subprojects contributing
  path-prefix sources); counter mode derived from the tree (a `common`-shaped
  fixture without a server package, a major-shaped one with it); tag-shape
  parsing.
- **Offline checks**: `project verify --offline`, the project-config check
  workflow, `black` and `pyright` on both PRs.
- **PR OBS root**: PR A, all tools packages green on every repository (watch
  pgbackrest on openSUSE: tools inherits no per-major `Ignore:
  postgresqlNN-server`); PR B, every major's five packages show as aggregates
  pointing at the PR tools project, the three image projects build at their
  new names, `qa-packages` green on all majors.
- **Release dry-runs** after PR B merges: `sync release --dry-run
  ppg:releases:18` lists `ppg:staging:common:tools` and `ppg:common:deps`
  with the aggregated package names; `sync release --dry-run
  ppg:releases:common` lists the majors and `ppg:common:deps` whole.

## Out of scope / follow-ups

- The package-level QA blocks (PR #119, merged) must treat aggregate packages
  as present in the consuming major; follow-up there, not changed here.
- `ppg:staging:19` gets the aggregates when it enters the aggregate scheme.
- A tools-only PR promotes no per-major aggregate, so the present-only
  per-major QA lanes are skipped and tools has no `qa:` block: such a PR gets
  no package QA; follow-up with the package-QA work.
- `devel/common` is created only when a devel package or image needs it.
- Moving `percona-pgbadger`, `percona-haproxy` or `patroni` images (none
  exist today).
