# UBI 10 container images on the real Red Hat base image

**Date:** 2026-09-29
**Status:** approved by the user in brainstorming (2026-09-28/29); plan pending approval
**Scope:** PR 2 of 3. Adds a `ubi10` image repository to every PPG container
project, built `FROM registry.access.redhat.com/ubi10/ubi-minimal:latest`
through OBS download-on-demand, and makes the Dockerfiles base-image
parametric. PR 1 (`UBI_10` RPM repository, merged 2026-09-29) supplies the
packages; PR 3 will switch `ubi8`/`ubi9` to the registry image and delete the
kiwi-built `percona-ubi-minimal` stack.

## Background

The PPG container images (`percona-distribution-postgresql`, `-with-postgis`,
`-custom`, the two `-upgrade` images, `percona-pgbackrest`, `percona-pgbouncer`)
are built on the labs OBS from `FROM percona-ubi-minimal:latest`, a kiwi
image we build ourselves in `common:containers:ubi8/ubi9`. The labs instance
now has an admin project `RedHat:UBI:Registry` whose `images` repository is a
`<download repotype="registry">` of `registry.access.redhat.com`; a consumer
repository lists it as a path and OBS fetches the image a `FROM` line names
(proven by `Percona:Test/hello-image-el`, x86_64 and aarch64).

User decisions from brainstorming: always the `latest` tag (release projects
are build-disabled, so no drift there); keep the labels the Dockerfiles set
today; keep `RUN microdnf -y update`; no change to the dev OBS instance;
UBI 10 first, in its own PR, before the kiwi stack is dropped.

## What UBI 10 provides (verified on labs, 2026-09-29)

- `registry.access.redhat.com/ubi10/ubi-minimal:latest` exists (manifest 200;
  the tag list is paginated, which hides it from a naive listing). The `10`
  tag does not exist, same as `9` on ubi9.
- `RedHat:UBI-10/appstream` ships podman, buildah, skopeo, crun,
  fuse-overlayfs, containers-common. EPEL 10 ships `umoci`. Neither UBI 10 nor
  EPEL 10 ships `createrepo_c`, which `#!UseOBSRepositories` needs at build
  time; Rocky 10 devel has it, but Rocky must not enter an image repository's
  path (its packages would become installable inside the image).

So the only helper package UBI 10 images need from us is `createrepo_c`.

## Design

### `root/common/containers/ubi10/`

A new project with one repository, `UBI_10`, whose paths are EPEL 10,
`RedHat:UBI-10/standard` and `RockyLinux:10/devel` (a build-only path, like
`common:containers:ubi9/UBI_9`), archs x86_64 and aarch64, `publish: false`,
`repositories-inherit: false`, `project-config-inherit: false`, prjconf
`Type: spec` under `%if "%_repository" == "UBI_10"`. It holds one package,
`createrepo_c`, a copy of `root/common/containers/ubi9/createrepo_c`. No
`images` repository, no kiwi packages, no `umoci` (EPEL 10's is used).

### The `ubi10` image repository

Every container project file gains a `ubi10` repository. The path list,
in order:

1. `project: RedHat:UBI:Registry`, `repository: images` (the base image);
2. the same PPG RPM sources the project's `ubi9` entry lists, with
   `UBI_9` → `UBI_10` (`ppg:staging:<V>`/`…:extras`/`ppg:common:deps`);
3. `subproject: common:containers:ubi10`, `repository: UBI_10`;
4. `project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:10`, `repository: standard`;
5. `project: RedHat:UBI-10`, `repository: standard` (last, so OBS expands it
   transitively into baseos/appstream/codeready-builder).

Files: `root/ppg/staging/_shared/containers/project.yaml` (per-major
containers, symlinked by 14–18), `root/ppg/staging/containers/project.yaml`
(cross-major upgrade image; staging 18…14 `UBI_10` paths),
`root/ppg/staging/_shared/extras/containers/project.yaml` (cross-major custom
upgrade; extras 18…16 and staging 18…16), and the three per-major
`root/ppg/staging/{16,17,18}/extras/containers/project.yaml` (real files, not
symlinks).

### Build configuration

Each of those files gets a `%if "%_repository" == "ubi10"` block with
`BuildFlags: dockerarg:RHEL_VER=el10` and
`BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi10/ubi-minimal:latest`.
The existing `ubi8` and `ubi9` blocks get
`BuildFlags: dockerarg:UBI_BASE=percona-ubi-minimal:latest` so the base image
is always chosen by the repository, never by the Dockerfile default. The
extras files, which wrap their whole config in `%if ubi9`, get the ubi10 block
as a second conditional with the same body plus the el10 args.

`Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-libs` and the other
`Prefer`/`Ignore` lines are repository-independent and stay as they are.
`Substitute: rocky-release redhat-release` stays: harmless where no Rocky
repository is in the path.

### Dockerfiles

All seven Dockerfiles replace

```
FROM percona-ubi-minimal:latest
```

with

```
ARG UBI_BASE=percona-ubi-minimal:latest
FROM $UBI_BASE
```

OBS's Dockerfile parser substitutes `ARG` defaults and `dockerarg` build
flags into `FROM`, resolving the base-image dependency per repository (this
is how `home:Admin:testing/testimage` builds for ubi9 and ubi10 from one
file). Nothing else in the Dockerfiles changes: labels, `microdnf update`,
package lists and entrypoints are untouched (user decision).

### QA lanes

- `_shared/containers` and `staging/containers` already use named lanes
  (`ubi8`, `ubi9`); they get a `ubi10` lane, a copy of `ubi9` with the
  registry path ending in `/ubi10`.
- The extras files use unnamed lanes today. Two flavours on one pipeline need
  names, so the existing entries become `name: ubi9` (server pipeline) and
  `name: ubi9-upgrade` (`ppg-obs-upgrade`), and `ubi10` / `ubi10-upgrade`
  copies are added. Consequence: the extras QA check-run names change from
  `OBS QA / <project> / <pipeline> / …` to `OBS QA / <project> / ubi9… / …`.
  The cross-major `_shared/extras/containers` block has a single unnamed
  entry; it becomes `ubi9` + `ubi10`.

### CI

`.github/workflows/obs-pr-check.yml`: the `for other in ubi8 ubi9` loop that
excludes the other flavours' `common:containers:*` projects becomes
`ubi8 ubi9 ubi10`. The `ubi10-images` label already exists on GitHub and the
`<flavor>-images` expansion (`ubi10`, `UBI_10`, `images`) needs no change.

### Not changed

- `common:containers:ubi8/ubi9`, the kiwi image, the `ubi8`/`ubi9` base
  image (PR 3).
- `root/ppg/releases/*` (frozen; next release train).
- `percona_obs/` (image repo names are derived from config, the flavour is
  never hardcoded) and `tests/`.
- The dev OBS instance.

## Verification

1. black / pyright / pytest pass; `project verify` clean.
2. `percona-obs -P labsmain project config --offline` for `ppg:staging:18:containers`,
   `ppg:staging:containers`, `ppg:staging:18:extras:containers`,
   `ppg:staging:extras:containers` and `common:containers:ubi10` renders the
   `ubi10` repository with the path order above and the `UBI_BASE` build
   flags for every flavour.
3. `qa show` for the extras projects lists the four named lanes.
4. PR against `percona/obs-packaging` with the `ubi10-images` label (the user
   adds `obs-sync`). Gate on the labs PR project: `createrepo_c` succeeded on
   `common:containers:ubi10/UBI_10`; all seven images succeeded on `ubi10`
   for x86_64 and aarch64; the `_buildinfo` of one image lists
   `container:registry.access.redhat.com-ubi10-ubi-minimal-latest` from
   `RedHat:UBI:Registry`; the `ubi8`/`ubi9` images still build (their base
   now comes from the `UBI_BASE` build flag) — at least one per-major
   project's `ubi9` image is rebuilt in the PR project and succeeds.
5. Optional smoke test by the user: pull one `ubi10` image from the labs
   registry, `podman run … cat /etc/os-release` shows RHEL 10, `psql --version`
   matches the major.

## Risks

- `FROM $UBI_BASE` with a default that is a local kiwi image name: proven for
  registry names on the dev instance; the `dockerarg` for ubi8/ubi9 is set
  explicitly so the default is never relied on.
- `createrepo_c` 0.20.1 may need spec tweaks on EL10 (it built on UBI_9's
  Rocky 9 devel path); triaged in the build round.
- Red Hat certification labels: the real base image carries Red Hat labels the
  images now inherit; the user chose to keep the current label set for now.
  A later pass can add the `/licenses` EULA and clear `com.redhat.component`
  (see `Percona:Test/hello-image-el`).
- The registry download is per digest; a new upstream `latest` triggers OBS
  rebuilds of every ubi10 image (accepted: that is the point of `latest`).
