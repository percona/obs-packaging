# UBI 10 container images on the real Red Hat base image

**Date:** 2026-09-29
**Status:** approved by the user in brainstorming (2026-09-28/29); plan pending approval
**Scope:** PR 2 of 2 (amended 2026-09-29: the user folded the former PR 3 into
this one). Adds a `ubi10` image repository to every PPG container project,
switches **all three flavours** (`ubi8`, `ubi9`, `ubi10`) to the official
`registry.access.redhat.com/ubi<N>/ubi-minimal:latest` images through OBS
download-on-demand, makes the Dockerfiles base-image parametric, and retires
the kiwi-built `percona-ubi-minimal` stack in `common:containers:ubi8/ubi9`.
PR 1 (`UBI_10` RPM repository, merged 2026-09-29) supplies the packages.

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
and (2026-09-29) transition ubi8 and ubi9 to the real UBI images in this same
PR rather than a later one.

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

### The image repositories

Every container project file's existing `ubi8`/`ubi9` repositories change in
the same way: `RedHat:UBI:Registry/images`
becomes the first path and the `common:containers:ubi<N>/images` path (the
kiwi image) is removed. The per-major and cross-major containers projects
(not the extras ones, see below) additionally gain a `ubi10` repository whose
path list, in order, is:

1. `project: RedHat:UBI:Registry`, `repository: images` (the base image);
2. the same PPG RPM sources the project's `ubi9` entry lists, with
   `UBI_9` → `UBI_10` (`ppg:staging:<V>`/`…:extras`/`ppg:common:deps`);
3. `subproject: common:containers:ubi10`, `repository: UBI_10`;
4. `project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:10`, `repository: standard`;
5. `project: RedHat:UBI-10`, `repository: standard` (last, so OBS expands it
   transitively into baseos/appstream/codeready-builder).

Files with a `ubi10` repository: `root/ppg/staging/_shared/containers/project.yaml`
(per-major containers, symlinked by 14–18) and
`root/ppg/staging/containers/project.yaml` (cross-major upgrade image;
staging 18…14 `UBI_10` paths).

**Extras get no `ubi10` flavour** (found during execution): the extras
subprojects build only on `UBI_9` by the PR 1 decision, so
`ppg:staging:<V>:extras/UBI_10` does not exist and the custom images cannot be
built for UBI 10 yet. `root/ppg/staging/extras/containers/project.yaml` and the
three per-major `root/ppg/staging/{16,17,18}/extras/containers/project.yaml`
only get the `ubi9` edit (registry path first, kiwi path removed) and the
`UBI_BASE` flag. Extending extras to UBI 10 is a separate decision.

### Build configuration

Each of those files gets a `%if "%_repository" == "ubi10"` block with
`BuildFlags: dockerarg:RHEL_VER=el10` and
`BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi10/ubi-minimal:latest`.
The existing `ubi8` and `ubi9` blocks get
`BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi8/ubi-minimal:latest`
and `…/ubi9/ubi-minimal:latest` respectively (both tags verified on the
registry), so the base image is always chosen by the repository, never by the
Dockerfile default. The
extras files keep their single `%if ubi9` block, plus the `UBI_BASE` flag.

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
ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest
FROM $UBI_BASE
```

(the default only matters outside OBS; every repository sets the flag).

OBS's Dockerfile parser substitutes `ARG` defaults and `dockerarg` build
flags into `FROM`, resolving the base-image dependency per repository (this
is how `home:Admin:testing/testimage` builds for ubi9 and ubi10 from one
file). Nothing else in the Dockerfiles changes: labels, `microdnf update`,
package lists and entrypoints are untouched (user decision).

### QA lanes

- `_shared/containers` and `staging/containers` already use named lanes
  (`ubi8`, `ubi9`); they get a `ubi10` lane, a copy of `ubi9` with the
  registry path ending in `/ubi10`.
- The extras files keep their unnamed single-flavour lanes unchanged (no
  ubi10 flavour there).

### CI

`.github/workflows/obs-pr-check.yml`: the `for other in ubi8 ubi9` loop that
excludes the other flavours' `common:containers:*` projects becomes
`ubi8 ubi9 ubi10`. The `ubi10-images` label already exists on GitHub and the
`<flavor>-images` expansion (`ubi10`, `UBI_10`, `images`) needs no change.

### Retiring the kiwi minimal image

Nothing consumes `common:containers:ubi8/ubi9`'s `images` repository once the
paths above are gone, so those projects shrink to the build helpers the docker
builds still pull (verified from `_buildinfo` on labs):

- ubi9 keeps `createrepo_c` and `umoci`; ubi8 keeps `createrepo_c`, `umoci`
  and the repackaged `rpm-devel`, `file-devel`, `popt-devel` that
  createrepo_c needs on EL8.
- Deleted from both: `minimal-image` (kiwi description, `config.sh`, helper
  services), `python-kiwi`, `obs-service-kiwi_label_helper`,
  `obs-service-kiwi_metainfo_helper`, `python3-docopt`, `python3-poetry-core`,
  `python3-simplejson`, `python3-xmltodict`; from ubi8 also `python3-tomli`
  and `dnf4` (kiwi's dnf backend). None of them is a build dependency of the
  kept packages (checked against the specs and `_buildinfo`).
- Both `project.yaml` files lose the `images` repository and its whole kiwi
  prjconf block (`Type: kiwi`, `Preinstall:` list, kiwi `Ignore:`s,
  `BuildFlags: container-*`); the `UBI_N` repository and its `Type: spec`
  block stay.

On labs, the next full sync deletes the removed packages as orphans; the
`percona-ubi-minimal` images stop being published. Releases 17/18 still
reference `common:containers:ubi9/images` in their frozen config; their
projects are build-disabled, so nothing breaks, and the next release train
picks up the new layout.

### Not changed

- `root/ppg/releases/*` (frozen; next release train).
- `percona_obs/` (image repo names are derived from config, the flavour is
  never hardcoded). In `tests/` only the lane-count assertion of
  `test_qa_entry_name.py` moves from two to three lanes.
- The dev OBS instance.

## Verification

1. black / pyright / pytest pass; `project verify` clean.
2. `percona-obs -P labsmain project config --offline` for `ppg:staging:18:containers`
   and `ppg:staging:containers` renders the `ubi10` repository with the path
   order above and the `UBI_BASE` build flags for all three flavours;
   `ppg:staging:18:extras:containers` and `ppg:staging:extras:containers`
   render their `ubi9` repository with the registry path first and the ubi9
   `UBI_BASE` flag only; `common:containers:ubi10` renders `UBI_10` only.
3. `qa show` for `ppg:staging:18:containers` and `ppg:staging:containers` lists
   `ubi8`, `ubi9`, `ubi10`; the extras lanes are unchanged.
4. PR against `percona/obs-packaging` with the `ubi8-images`, `ubi9-images`
   and `ubi10-images` labels (the user adds `obs-sync`). Gate on the labs PR
   project: `createrepo_c` succeeded on `common:containers:ubi10/UBI_10`;
   every image succeeded on `ubi8`, `ubi9` and (containers projects only)
   `ubi10` for x86_64 and aarch64; the `_buildinfo` of one image per flavour lists
   `container:registry.access.redhat.com-ubi<N>-ubi-minimal-latest` from
   `RedHat:UBI:Registry`; no package of the PR's `common:containers:ubi8/9`
   is anything but `createrepo_c`/`umoci`/the three ubi8 `-devel` repackages.
5. Optional smoke test by the user: pull one `ubi10` image from the labs
   registry, `podman run … cat /etc/os-release` shows RHEL 10, `psql --version`
   matches the major.

## Risks

- `FROM $UBI_BASE`: proven for registry names on the dev instance; every
  repository sets the flag so the default is never relied on.
- The real UBI 8/9 minimal images differ from our kiwi image in what is
  pre-installed (the kiwi image added e.g. `langpacks-en`, `dejavu-sans-fonts`,
  `libusbx`, `rootfiles`); a `microdnf install` in a Dockerfile may now pull
  something the kiwi base already had, or a later `RUN` may miss a file. Found
  in the build round and fixed in the Dockerfile only if needed for all
  flavours alike.
- `createrepo_c` 0.20.1 may need spec tweaks on EL10 (it built on UBI_9's
  Rocky 9 devel path); triaged in the build round.
- Red Hat certification labels: the real base images carry Red Hat labels
  that all three flavours now inherit; the user chose to keep the current
  label set for now.
  A later pass can add the `/licenses` EULA and clear `com.redhat.component`
  (see `Percona:Test/hello-image-el`).
- The registry download is per digest; a new upstream `latest` triggers OBS
  rebuilds of every ubi10 image (accepted: that is the point of `latest`).

## Addendum 2026-09-30: ubi8 needs non-modular rebuilds of its module-stream packages

The real `ubi8/ubi-minimal` image cannot install EL8 module-stream packages
from an OBS build: OBS serves the in-build repository without module
metadata (`build-recipe-docker` runs plain `createrepo`; the backend never
fetches `modules.yaml` for download-on-demand repositories), and libdnf refuses
any package carrying a modularity label when no metadata declares its stream
(`No available modular metadata for modular package …`). The kiwi-built
`percona-ubi-minimal` sidestepped this: its from-scratch bootstrap had no
`/etc/os-release` while dnf installed, so libdnf's modular logic was off, and
the resulting image already contained 281 packages including the whole perl
stack, perl-DBD-Pg and llvm. A kiwi image *derived from* the real ubi8-minimal
hits the same refusal (tested in `home:rjfd.di:ubi8test` on labs: non-modular
packages install, the modular set does not).

Decision (user, 2026-09-30): keep ubi8 on the official image and remove the
need for modular packages, JIT included. Only seven packages are affected,
the ones with `.module+el8` in the kiwi image: perl-IO-Socket-SSL 2.066,
perl-Net-SSLeay 1.88, perl-Mozilla-CA 20160104 (from the `perl-IO-Socket-SSL:2.066`
and `perl-libwww-perl:6.34` streams, pulled in by `perl`), perl-DBD-Pg 3.7.4
(`perl-DBD-Pg:3.7`, PostGIS utils) and llvm, llvm-libs, llvm-filesystem 21.1.8
(`llvm-toolset:rhel8`, required by every `-llvmjit` subpackage as `llvm >= 19`).

`common:containers:ubi8` (already in every ubi8 image path) gains only what
UBI 8 does not ship non-modular:

- `perl-DBD-Pg` 3.7.4, built from the CentOS Stream 8 spec (plain
  `1%{?dist}` release, so no modularity label; CPAN tarball via
  `download_url`; builds against `libpq-devel`; the live-database tests are
  skipped because they need `postgresql-server`, itself a module stream).
- `llvm`: a binary repackaging of the Rocky Linux 8 AppStream llvm 21.1.8
  RPMs (`llvm`, `llvm-libs`, `llvm-filesystem`, x86_64 and aarch64) into
  non-modular RPMs with the same names and version, the same technique as
  the EL8 `file-devel`/`rpm-devel`/`popt-devel` repackages. 21.1.8 is
  exactly the version the `-llvmjit` subpackages on `UBI_8` were built
  against, so the ABI matches.

perl-IO-Socket-SSL, perl-Net-SSLeay and perl-Mozilla-CA need no rebuild:
UBI 8 AppStream ships them without a module stream; the kiwi image carried
the `.module+` copies only because the stream flags were enabled.

The ubi8 image build config enables only `module:perl-5.26` (its artifacts
are plain RPMs) and `module:container-tools-rhel8`; the perl-IO-Socket-SSL,
perl-libwww-perl, perl-DBI, perl-DBD-Pg and llvm-toolset streams are not
enabled in image projects, so OBS resolves those names to UBI's non-modular
packages or our rebuilds. The RPM build projects are unchanged: they keep
building against the module toolchain.
