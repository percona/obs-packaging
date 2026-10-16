# PostGIS GIS library stack: mirror PGDG

Date: 2026-10-16
Related: PG-2864 (QA request to align percona-postgis35 libraries with percona-release)

## Problem

`percona-postgis35_<M>` (PostGIS 3.5.7, PG 14–18) and `percona-postgis37_19`
(PostGIS 3.7, PG 19) build on every RPM distro against whatever GEOS, PROJ,
GDAL and SFCGAL the buildroot happens to offer. Today that means EPEL GDAL
3.4.3 on EL9, unversioned `geos` (3.13.1) and `proj` (9.6.0) from
`ppg:common:deps`, and open-ended `SFCGAL-devel >= 2.1.0`. Two consequences:

- The libraries are well below the targets the PostGIS compatibility matrix
  (<https://postgis.net/development/compatibility/>) recommends. PROJ and GDAL
  are rated "compatible, not a recommended target".
- Builds are not pinned. The SFCGAL 2.3.0 rebuild silently changed what
  PostGIS 3.5.7 links. Two upstream regression tests then failed
  (`sfcgal/regress/alphashape`, `extrudestraigthskeleton`), which led to
  PG-2864. Upstream fixed those tests on `stable-3.5` (`8b3fcf54a5`,
  `fb149e1499`); only test files changed.

## Goal

Ship the same GIS stack as PGDG on every RPM distro, never below what PPG
releases ship today, with every library version pinned. Debian and Ubuntu
keep the distro libraries, as PPG ships today and as apt.postgresql.org does.

## Decisions

| Topic | Decision |
|---|---|
| GEOS | One line, `geos315`, for both PostGIS 3.5 and 3.7. This matches PGDG, which builds postgis35 3.5.7 against GEOS 3.15 with a backport patch. |
| PROJ | `proj98`; `proj96` on EL8 (PGDG's EL-8 choice). |
| GDAL | `gdal313`; `gdal38` on EL8. Full PGDG feature parity, including the Python 3.12 and Java bindings on EL9+. |
| SFCGAL | 2.3.x; the two failing tests are patched in ppg-testing until PostGIS 3.5.8. |
| Supporting libraries | `libgeotiff17`, `libspatialite50`, and `librttopo` (EL8 only: EPEL 8 lacks it). |
| Naming / layout | PGDG package names, prefixes `/usr/<name>`, RPATH. No `/etc/ld.so.conf.d` drop-ins. |
| Pins | Minor line pinned: `>= X.Y.0` together with `< X.(Y+1)` on BuildRequires, and matching runtime Requires. A minor bump is a deliberate edit. |
| Skip-if-distro-matches | No. We always build our own on RPM distros, so there is one code path and every pin is under our control. |
| Debian / Ubuntu | Distro libraries (no change). Debian 11 is dropped for upcoming releases. |
| Publishing | Runtime libraries are aggregated from `ppg:common:deps` into every `ppg:staging:<ver>`. |

### Rejected alternatives

- **geos314 + geos315 with two flavors of every GEOS-linked library**
  (gdal, libspatialite, librttopo through `_multibuild`, with distinct
  prefixes so that PG 18 and PG 19 PostGIS stay co-installable for
  `pg_upgrade`). This was viable but doubled the package count. PGDG's
  GEOS 3.15 backport for 3.5.7 removes the need.
- **Shipping our own stack on Debian/Ubuntu** under a versioned-prefix deb
  layout. This was the largest and riskiest piece, with no precedent at
  apt.postgresql.org. PPG debs have always used the distro libraries.

## No-regression check (2026-10-16)

`percona-postgis35_<M>` 3.5.7 in the latest releases ppg-14.24, 15.19, 16.15,
17.11 and 18.6 (repo.percona.com, all built 2026-08-12) requires:

| | Shipped today | This design |
|---|---|---|
| EL8 | geos311 3.11.2, proj95 9.5.1, gdal38 3.8.5, SFCGAL 1.4.1 | geos315, proj96 9.6.2, gdal38 3.8.5, SFCGAL 2.3 (1.4.1 if 2.3 does not build on EL8) |
| EL9 | geos311 3.11.2, proj95 9.5.1, gdal311 3.11.0, SFCGAL 2.x | geos315, proj98, gdal313, SFCGAL 2.3 |
| EL10 | geos313 3.13.1, proj96 9.6.2, gdal311 3.11.3, SFCGAL 2.2.0 | geos315, proj98, gdal313, SFCGAL 2.3 |
| all EL | libgeotiff17 | libgeotiff17 |

Every library stays the same or moves up. The shipped GDAL packages already
include `-java`, `-python-tools` and `-python3`, which full parity keeps.

On deb, all five releases × six codenames link the distro libraries
(`libgdalNN`, `libgeos-c1v5`/`libgeos-c1t64`, `libprojNN`, `libsfcgalN`). The
apt repos contain no GIS libraries of their own. Keeping distro libraries is
therefore no change.

## Design

### 1. Packages in `ppg:common:deps`

The specs are ported from PGDG's `rpm/redhat/main/common/<pkg>` (including
the `EL-8` and `SLES-16` variants) and adapted to this tree's conventions:
`_service`, `package.yaml` and `%!{}` macros.

| Package | EL8 / UBI8 | EL9, 9.6, UBI9, EL10, UBI10 | Leap 16 / Tumbleweed |
|---|---|---|---|
| `geos315` | 3.15.x | 3.15.x | 3.15.x |
| `proj96` | 9.6.2 | — | — |
| `proj98` | — | 9.8.x | 9.8.x |
| `libgeotiff17` | on proj96 | on proj98 | on proj98 |
| `librttopo` | ✓ | — on EL9/9.6/UBI9 (EPEL); EL10/UBI10 to confirm in step 1 | to confirm in step 1 |
| `libspatialite50` | ✓ | ✓ | ✓ |
| `gdal38` | 3.8.5 | — | — |
| `gdal313` | — | 3.13.x, full parity | 3.13.x (PGDG's SLES-16 variant) |
| `SFCGAL` | 2.3.x (existing `sfcgal` package) | 2.3.x | 2.3.x |

- Every package is disabled on Debian/Ubuntu in `package.yaml`.
- The unversioned `geos` (3.13.1) and `proj` (9.6.0) packages are retired,
  together with the Debian packaging of `geos`, which existed only for
  Debian 11.
- PGDG's `/etc/ld.so.conf.d/*-pgdg-libs.conf` files are left out. Consumers
  find the libraries through RPATH only, so the system-wide linker path is
  never changed.
- GDAL drivers and subpackages follow PGDG's spec for each EL variant. A
  dependency missing on one of our distros is either built in common:deps or
  disabled for that distro only, with a comment in the spec. The known
  differences are muParser (absent on EL, also off in PGDG) and the bindings
  on EL8 (off in PGDG too).

Versions are defined once in `root/macros.yaml`, the same way
`POSTGIS_RPM_MAJOR` is: `GEOS_RPM_MAJOR`, `GEOS_VERSION`, `PROJ_*`, `GDAL_*`,
including the EL8 values. Specs read them through `%!{…}`.

### 2. PostGIS specs

Files: `root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec`
(3.5, PG 14–18) and `root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec`
(3.7).

- The current per-distro override blocks (EL10 versioned, EL8/9 EPEL `/usr`,
  SUSE unversioned, RHEL 7 leftovers) are replaced by one selection block that
  mirrors PGDG's postgis35/postgis37 headers:
  - `geos315` everywhere;
  - EL8: `gdal38` + `proj96`;
  - everywhere else: `gdal313` + `proj98`;
  - `libgeotiff17`, `libspatialite50` and `SFCGAL` everywhere.
- PGDG dropped EL8 from postgis37. We keep it and use the same EL8 combination
  as 3.5, extending the existing `# PERCONA:` note.
- BuildRequires and Requires use the PGDG names with minor-line pins. The
  EPEL by-name Requires (`gdal3.4-libs`, `gdal-libs`, `hdf5`,
  `geos proj libgeotiff`) are removed.
- The configure wiring (`--with-geosconfig`, `--with-projdir`, `-Wl,-rpath`,
  instdir macros) keeps its shape; only the macro values change.
- 3.5 only: add PGDG's `postgis35-3.5.7-geos315-backport.patch` (stable-3.5
  !445 + !465). Without it, `ST_Split()` of a line by points returns the line
  unsplit with GEOS ≥ 3.15. The code changes are guarded by
  `POSTGIS_GEOS_VERSION >= 31500`. The patch also goes into `debian/patches`
  so the source is the same everywhere; it has no effect there. It is removed
  with PostGIS 3.5.8.
- The SFCGAL test fixes do not go into the package (see §5).
- `debian/control` library dependencies are unchanged.

### 3. Aggregates into `ppg:staging:<ver>`

- New `root/ppg/staging/_shared/<pkg>/obs/_aggregate` →
  `${OBS_ROOTPRJ}:ppg:common:deps` for `geos315`, `proj96`, `proj98`,
  `libgeotiff17`, `librttopo`, `libspatialite50`, `gdal38` and `gdal313`,
  symlinked into `staging/14`–`19`. `sfcgal` stays.
- The existing `geos` and `proj` aggregates are removed.
- Repository scoping is done with `package.yaml` `build:` flags:
  - every aggregate is off on Debian/Ubuntu;
  - `gdal38`, `proj96` and `librttopo` are enabled on RockyLinux_8 and UBI_8 only;
  - `gdal313` and `proj98` are enabled on every other RPM repository.
- All binaries are aggregated (`-devel`, `-python3`, `-java`, tools).
- Build-time resolution does not depend on the aggregates, because every
  staging repository already resolves `ppg:common:deps` first through
  `path-prefix`.
- `project release` already copies aggregates into `ppg:releases:<ver>`
  (`sfcgal` is in releases:18). The retired `geos`/`proj` aggregates become
  orphans, and the release flow's orphan handling cleans them up.

### 4. Tarballs

`ppg:common:deps:tarballs` keeps its relocatable `/opt` builds, and they
follow the new SONAMEs:

| | ssl1.1 (EL8) | ssl3 / ssl3.5 (EL9.6 / EL9) |
|---|---|---|
| `percona-gdal` | 3.0.4 → 3.8.5 (`libgdal.so.34`) | 3.4.3 → 3.13.x (`libgdal.so.39`) |
| `percona-proj` | 6.3.2 → 9.6.2 (`libproj.so.25`) | 9.6.0 → 9.8.x (`libproj.so.25`) |
| GEOS | `geos315` bundled as-is | same |

- `percona-gdal` keeps the minimal driver set derived from the official
  tarball. It is deliberately not full parity, so that poppler, arrow, the JDK
  and hdf stay out of a relocatable tarball.
- `percona-gdal` switches to GDAL's bundled libgeotiff, so the tarball carries
  a single PROJ.
- The `percona-gis-compat` `Provides:` move to the new by-name Requires:
  `proj96`/`proj98`, `gdal38-libs`/`gdal313-libs`, `libgeotiff17`,
  `libspatialite50`.
- The `Prefer:` lines in `staging/_shared/tarballs/project.yaml` are
  unchanged apart from comments.
- The `build-tarball.sh` 0a guard and the SSL-ABI audit stay as they are.

### 5. QA

ppg-testing changes, in `Percona-QA/ppg-testing` (`postgis/setup/tasks/main.yml`),
coordinated with QA:

1. Install the build dependencies derived from
   `rpm -q --requires percona-postgis<MM>_<V>`, mapped to their `-devel`
   packages, instead of the hardcoded `gdal311`/`geos311`/`proj95`. Debian
   keeps the distro `-dev` packages.
2. While `COMPONENT_REF` is 3.5.7, apply after the git checkout:
   - the SFCGAL test fixes `8b3fcf54a5` and `fb149e1499`;
   - the regression-test parts of the GEOS 3.15 backport
     (`regress/core/fixedoverlay*`, `wrapx*`).

   Remove all of them when 3.5.8 is tagged. The suite runs from the git tree,
   so patches carried in the package do not reach it.

Acceptance for each staging major:

- `PostGIS_Full_Version()` on rhel-9 reports GEOS 3.15.x, PROJ 9.8.x,
  GDAL 3.13.x and SFCGAL 2.3.0. On rhel-8 it reports PROJ 9.6 and GDAL 3.8.
- installcheck passes all 342 tests on rhel-8/9/10 (amd + arm) and on the
  deb lanes.
- `dnf install percona-postgis35_<V>` resolves on rhel-8/9/10 without any
  EPEL GIS package.
- The tarball and container lanes are green, and `postgis_full_version()`
  works from inside the tarball and the images.

When done, comment on PG-2864 with the outcome and close it.

### 6. Rollout

Each step is a PR from a worktree off `percona/main` and is verified on OBS
before the next one starts:

1. **common:deps libraries**, in dependency order: geos315 → proj98/proj96 →
   libgeotiff17 → librttopo (EL8) → libspatialite50 → gdal38/gdal313; then
   check that SFCGAL 2.3 builds on EL8. The old `geos`/`proj` packages stay
   until step 3. Everything must be green on all RPM repos × 2 arches.
2. **`macros.yaml` and the PostGIS specs** (3.5 shared and 3.7), with the
   backport patch. Staging 14–19 PostGIS must be green, and the dependency
   cascade must promote only the expected packages.
3. **Aggregates**: add the new ones and retire `geos`/`proj`. The published
   staging repos must contain the new libraries and pass the dnf-resolve
   check.
4. **Tarballs**: the `percona-gdal`/`percona-proj` bumps and the shim. Tarball
   builds and audits must be green.
5. **ppg-testing PR** (QA), merged together with step 2 reaching the staging
   publish.
6. **Release train**: the next 14.x–18.x releases and 19 ship the new stack,
   and the old aggregates are cleaned up as orphans.

## Risks

- PGDG builds GDAL against proj96 rather than proj98 on EL8 and gives no
  reason. We follow them; if proj98 turns out to work on EL8 it can be bumped
  later.
- The bindings bring a JDK and python3.12 (with numpy) into the GDAL build on
  UBI. They are available in the UBI repository paths, per the 2026-10-16
  dependency scan.
- Every library bump rebuilds PostGIS across 6 majors × the RPM repositories.
- GEOS 3.15 behaviour changes in PostGIS 3.5.7 beyond the backport are covered
  only by installcheck. PGDG ships the same combination.
- Tumbleweed is rolling. The pins turn a distro drift into a build failure
  rather than a silent relink.

## Out of scope

- Debian/Ubuntu library upgrades (distro libraries by design).
- Debian 11 (dropped for upcoming releases).
- PostGIS 3.5.8 / 3.7.0 GA bumps. When they happen, remove the backport patch
  and the ppg-testing patches.
