# UBI 10 RPM build repository (`UBI_10`)

**Date:** 2026-09-28
**Status:** approved 2026-09-28
**Scope:** PR 1 of 3. Adds the `UBI_10` RPM repository to every project that
already builds for `UBI_8` and `UBI_9`. Container images on UBI 10 (PR 2) and
dropping the kiwi-built `percona-ubi-minimal` base image (PR 3) are separate
efforts that build on this one.

## Background

Percona PostgreSQL packages are built for Red Hat UBI 8 and UBI 9 on the
internal labs OBS (`obs.pg.labs.percona.com`, root `isv:percona`). The UBI
repositories (`UBI_8`, `UBI_9`) are declared once in `root/project.yaml` and
inherited by every project under `root/`; the `labsmain` profile slices them
onto the labs instance with the `UBI_*` glob. build.opensuse.org never builds
them.

Red Hat UBI 10 is out. The labs instance already mirrors it (`RedHat:UBI-10`
with `baseos`, `appstream`, `CRB` and a `standard` aggregate), and the
interconnect already serves `Fedora:EPEL:10` and `RockyLinux:10` (including
its `devel` repository). `RockyLinux_10` has been a root-level build
repository for a while, so every package already builds against EL10 content.

Goal of this PR: every package that builds on `UBI_8` or `UBI_9` also builds
on `UBI_10`, for x86_64 and aarch64, so that PR 2 can install them into
`ubi10` container images.

## Non-goals

- No `ubi10` container repository, no `common:containers:ubi10`, no
  Dockerfile changes. That is PR 2.
- No change to `root/ppg/releases/*`. Release snapshots are frozen and pick up
  `UBI_10` at the next release train, like every other repository change.
- No change to the `percona-obs` tool or the CI workflows. The `UBI_*` slice
  glob and the repository-name PR labels already cover a new `UBI_10` name.
- No change to the dev OBS instance (`192.168.1.103`).

## Prerequisite outside git

Done 2026-09-28: `RedHat:UBI-10` on labs now matches `RedHat:UBI-8`/`UBI-9`
(same repository names, x86_64 and aarch64).

## Design

### Repository declaration

`root/project.yaml` gains a `UBI_10` repository right after `UBI_9`, a copy of
the `UBI_9` block with the numbers changed:

```yaml
  - name: UBI_10
    paths:
      - subproject: common:deps:build
        repository: UBI_10
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:10
        repository: standard
      - project: RedHat:UBI-10
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:10
        repository: devel
    archs: [x86_64, aarch64]
```

The `RockyLinux:10/devel` path plays the same role as `RockyLinux:9/devel`
does for `UBI_9`: it supplies `-devel` packages that Red Hat does not ship in
UBI (CRB covers many but not all). Path order matters, since OBS expands only
the last path transitively: `RedHat:UBI-10/standard` is itself an aggregate
of CRB, appstream and baseos, so it is listed as a single path.

Because the repository is declared at root level it is inherited by every
project that does not opt out: `common:deps:build`, `common:deps:runtime`,
`ppg:common:deps`, `ppg:staging:14`–`18`, `ppg:devel:*` (via the symlinked
`subprojects.yaml` and `path-prefix`). That matches the reach of `UBI_8` and
`UBI_9` today.

Projects that opt out with `repositories-inherit: false` and declare UBI
repositories themselves get an explicit `UBI_10` block following their own
`UBI_9` block:

- `root/ppg/staging/_shared/extras/project.yaml` (all `<V>/extras` symlink
  to it): paths `ppg:common:deps`, `common:deps:build`,
  `ppg:staging:%!{PG_MAJOR_VERSION}`, then EPEL 10, `RedHat:UBI-10`,
  Rocky 10 devel.
- `root/ppg/staging/16/tde/project.yaml`: same shape as its `UBI_9` entry.

The container projects (`_shared/containers`, `staging/containers`,
`_shared/extras/containers`, `<V>/extras/containers`) also opt out, but they
only consume UBI RPM repositories as paths of the `ubi8`/`ubi9` image repos.
They are untouched here and gain a `ubi10` image repository in PR 2.

### Project configuration (prjconf)

`UBI_10` takes the same build configuration as `RockyLinux_10` wherever a
`RockyLinux_10` block exists, and the same as `UBI_9` where the block is
UBI-specific. Concretely:

- `root/ppg/staging/subprojects.yaml`: the `RockyLinux_10` block
  (`Prefer: selinux-policy-targeted`, `Prefer: hdf-libs`, the
  `%__brp_check_rpaths %{nil}` macro) becomes
  `%if "%_repository" == "RockyLinux_10" || "%_repository" == "UBI_10"`.
- `root/ppg/staging/_shared/extras/project.yaml`: a `UBI_10` block with the
  same three settings. This file cannot rely on `subprojects.yaml` because it
  is one level deeper than the staging tier's direct children.
- `root/ppg/staging/16/tde/project.yaml`: its own `RockyLinux_10`-equivalent
  block does not exist yet, so a `UBI_10` block with the same three settings
  is added next to the existing UBI blocks.
- `root/project.yaml`, `root/ppg/common/deps/project.yaml`,
  `root/common/deps/runtime/project.yaml`: no `RockyLinux_10` block exists in
  any of them, so nothing is added up front. If the first build round reports
  `have choice` on `UBI_10` (the EL8/EL9 blocks settle `libverto-libev`,
  `Lmod`, `llvm-toolset` and `hdf-libs`), the fix is a `UBI_10` line in the
  matching file, mirroring the `UBI_9` precedent.

No `Release:` line: RPM repositories keep the default `<CI_CNT>.<B_CNT>`.

No `debuginfo` entry: `UBI_8` and `UBI_9` are not in the staging
`debuginfo:` map either.

### Package build flags

`package.yaml` `build:` flags default to enabled. The rule for this PR is:
**`UBI_10` mirrors `UBI_9`**. A package that is disabled on `UBI_9` is disabled
on `UBI_10`; every other package builds.

Packages gaining `UBI_10: false` (all have `UBI_9: false` today):

| package | why it is off on UBI 9 |
|---|---|
| `common/deps/build/llvm-21` | Debian 11/12 only repackage |
| `ppg/common/deps/bison` | EL8-only backport |
| `ppg/common/deps/flex` | EL8-only backport |
| `ppg/common/deps/nlohmann-json` | EL8-only backport |

Packages that are disabled on `RockyLinux_10` but enabled on `UBI_9` (atlas,
blis, boost, c-ares, proj, geos, lapack, flexiblas, perl-JSON,
python3-systemd) stay **enabled** on `UBI_10`. They are disabled on Rocky
because Rocky ships them; they are built on UBI 9 because UBI does not. UBI
10 is the same subset story as UBI 9, so the UBI 9 choice is the better
predictor. If a first-round build shows a package is redundant on UBI 10
(the distro package resolves and ours is never picked, or ours conflicts),
it gets `UBI_10: false` with a one-line comment, as `geos` and `proj` do for
`RockyLinux_9.6`.

### Anything else referencing UBI repositories

- `.github/workflows/obs-pr-check.yml`: PR labels are repository names, so a
  `UBI_10` label narrows the check to the new repo with no workflow change.
  The `for other in ubi8 ubi9` loop concerns image flavours and is extended
  in PR 2.
- `docs/PERCONA_OBS_TOOL.md` and `root/README.md` list no per-repository
  table that enumerates `UBI_9`; no doc change beyond a changelog-style note
  in the PR description.
- `tests/`: the repository-merge tests build their own fixtures and do not
  assert on the root file's repository list. `pytest` must still pass.

## Verification

1. `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q`
   pass (no Python changes expected, this guards the YAML through the
   config-merge tests).
2. `percona-obs -P labsmain project config` (and `--diff`) for
   `ppg:staging:18`, `ppg:staging:18:extras`, `ppg:staging:16:tde`,
   `ppg:common:deps` and `common:deps:build` shows a `UBI_10` repository with
   the expected paths, and the rendered prjconf contains the `UBI_10` blocks.
3. `sync push --dry-run` against `labsmain` lists only additions (the new
   repository on the affected projects) and no orphan deletions.
4. Open the PR against `percona/obs-packaging` with the `UBI_10` label so the
   PR check builds only the new repository on the labs PR project. The gate:
   every package that is `succeeded` on `UBI_9` is `succeeded` on `UBI_10`
   for both architectures, across `ppg:staging:14`–`18`, their `extras`
   (16–18), `ppg:staging:16:tde`, `ppg:common:deps`, `common:deps:build` and
   `common:deps:runtime`.
5. Triage loop for the first round: `unresolvable` means a missing
   `-devel`/module in the UBI 10 path set (candidate fix: prjconf `Prefer`,
   `Ignore`, `Substitute`, or a `UBI_10: false` flag with a comment);
   `failed` means a real packaging problem on EL10 and gets its own
   spec-level decision if it is not a one-liner.
6. After merge, `sync-main` creates the repositories on `isv:percona` and
   the full-tree build is the final proof.

## Risks

- **UBI 10 is a subset of RHEL 10.** Some build dependency that
  `RockyLinux_10` satisfies from appstream may be missing from UBI 10 and
  from `RockyLinux:10/devel`. Expect a handful of `unresolvable` packages in
  round one; that is the point of doing this PR on its own.
- **Rebuild fan-out.** Adding a repository to the root project touches the
  meta of every inheriting project. OBS schedules builds only for the new
  repository, so existing `UBI_8`/`UBI_9`/Rocky builds are not rebuilt.
- **aarch64 mirror gap.** Until `RedHat:UBI-10` on labs has aarch64, every
  aarch64 result is `unresolvable`. That is a prerequisite, not a PR issue.

## Follow-ups (not this PR)

- PR 2: `ubi10` container repository in the four container project files,
  `common:containers:ubi10` with `createrepo_c` and `umoci`, the
  `ARG UBI_BASE` / `FROM $UBI_BASE` Dockerfile form with per-repo
  `dockerarg:UBI_BASE`, the `ubi10-images` PR label, and the `ubi10` QA
  matrix entry.
- PR 3: switch `ubi8`/`ubi9` to `RedHat:UBI:Registry`, delete the kiwi
  `minimal-image` stack from `common:containers:ubi8/9`, prune the tool's
  kiwi handling.
