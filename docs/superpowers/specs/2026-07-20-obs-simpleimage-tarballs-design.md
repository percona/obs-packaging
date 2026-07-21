# OBS simpleimage Tarballs for Percona PostgreSQL — Design

**Date:** 2026-07-20 (revised same day: real POC supplied, scope expanded to full component set)
**Status:** Approved design, pending implementation plan

## Background

Besides RPM/DEB packages and container images, Percona distributes PostgreSQL as
binary tarballs for air-gapped systems and unsupported distros
(see <https://docs.percona.com/postgresql/17/tarball.html>). Today these are built
outside OBS by `percona/postgres-packaging/pg_tarballs/pg_tarballs_builder.sh`,
which compiles PostgreSQL and ~30 dependencies from source (network-dependent —
not runnable inside OBS build chroots).

This design generates equivalent tarballs **inside OBS** using the `simpleimage`
build format, repackaging the RPMs that `ppg:staging:<V>` already builds. A working
POC `simpleimage` recipe exists (`~/Downloads/simpleimage`, PPG 17.9) and is the
basis for the build script.

### Facts established during research

- **Official tarball layout** (inspected `percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz`):
  per-component top-level dirs (`percona-postgresql17/`, `percona-patroni/`,
  `percona-pgbackrest/`, `percona-pgbouncer/`, `percona-pgpool-II/`, `percona-haproxy/`,
  `percona-etcd/`, `percona-pgbadger/`, plus bundled `percona-python3/`, `percona-perl/`,
  `percona-tcl/` runtimes), each with `bin/ lib/ share/ include/`. Third-party libs are
  bundled in `lib/`; **glibc and OpenSSL come from the host** — that is why
  ssl1.1 / ssl3 / ssl3.5 variants exist. Binaries carry `RUNPATH=${ORIGIN}/../lib:…`
  plus hardcoded `/opt/percona-{python3,perl,tcl}` entries for the PL runtimes.
  Extension `.so` files sit directly in `lib/`.
- **simpleimage mechanics** (from obs-build source): the `simpleimage` file is parsed as
  an RPM spec preamble (`BuildRequires:` etc.). OBS installs the dependency closure into
  the build chroot and runs the `%build` section chrooted as root. By default the recipe
  then tars **the entire buildroot**; with `#!NoTarBall` the recipe skips its own tar
  step but still picks up `/.simpleimage.tar.gz` if the `%build` script created one, and
  renames it `Name-Version_ARCH.tar.gz`. `#!NoSquashfs` suppresses the squashfs artifact.
  Recipe sources are copied to `/usr/src/packages/SOURCES/` inside the chroot.
- **The POC** already implements the full official component set: PG server +
  extensions, companion tools (pgbouncer, pgpool-II, pgbackrest, pgbadger, patroni,
  etcd), and bundled python3.12/perl/tcl runtimes with portable-execution fixes
  (PYTHONHOME wrapper, libperl copied into `CORE/` with matching RPATH, `TCL_LIBRARY`
  wrapper, patroni + deps relocated into the bundled python with shebang rewrites).
  It stages everything under `/opt/percona-*` and creates the final tarball itself
  (`cd /opt && tar -czf /.simpleimage.tar.gz *`) — no buildroot pruning needed.
- `ppg:staging:17` already builds RockyLinux_8, RockyLinux_9, and RockyLinux_10 repos —
  the three bases needed for the ssl variants. Its `python3-*` packages are built
  against **python 3.12**, matching the bundled runtime (no C-extension ABI mismatch).
- `root/README.md` already reserves `staging/<V>/tarballs/`; the `containers/ubi*/`
  subprojects are the structural precedent (colon-named subproject, packages with `obs/`
  dirs synced verbatim, `%!{…}` macro expansion from cascading `macros.yaml`).

## Goals

- Produce a tarball equivalent in layout and consumption model to the official
  `percona-postgresql-<ver>-<ssl>-linux-x86_64.tar.gz`, built entirely in OBS from
  staging RPMs.
- **Full official component set** (POC scope): server + extensions, pgbouncer,
  pgpool-II, pgbackrest, pgbadger, patroni, etcd, pg_gather, and bundled
  python3/perl/tcl runtimes.
- Three SSL variants; x86_64 only for now.
- Tarballs rebuild automatically when any package in their dependency closure changes.

## Non-Goals (this iteration)

- aarch64 builds.
- Bit-identical parity with the official from-source tarballs (behavioral/layout parity
  is the target, not identical binaries).
- Debian-based tarball variants.
- haproxy (present in the official tarball; not in the POC BuildRequires — added later
  if the structure-diff shows it is required for parity).

## Design

### Project & tree structure

*(Revised 2026-07-21, user decision: SSL variants are **repositories** of a single
subproject, not separate subprojects.)*

One subproject with one package; each SSL variant is an OBS repository whose path
chain points at a different EL base of `ppg:staging:17`:

```
root/ppg/staging/17/tarballs/            → ppg:staging:17:tarballs
├── project.yaml                          # repos: ssl1.1, ssl3, ssl3.5
└── percona-postgresql-tarball/
    └── obs/
        ├── simpleimage
        └── build-tarball.sh
```

Path chains listed explicitly — OBS only expands the last path transitively:

| Repository | Path chain | Host ABI targeted |
|---|---|---|
| `ssl1.1` | `ppg:staging:17/RockyLinux_8` + `ppg:common:deps` + EPEL 8 + Rocky 8 (appstream, baseos, devel) | glibc ≥ 2.28, OpenSSL 1.1 |
| `ssl3` | `ppg:staging:17/Ubuntu_22.04` + `ppg:common:deps` + Ubuntu 22.04 universe | glibc ≥ 2.35, OpenSSL 3.0 |
| `ssl3.5` | `ppg:staging:17/RockyLinux_10` + EPEL 10 + Rocky 10 | glibc ≥ 2.39, OpenSSL 3.5 |

*(Revised 2026-07-21: ssl3 was originally Rocky 9-based, but RHEL 9.8 rebased to
OpenSSL 3.5 and the EL9 staging `pgcrypto.so` references `OPENSSL_3.4.0` symbols —
breaking the "OpenSSL 3.0 hosts" promise. Verified: Ubuntu 22.04 staging debs need
only `OPENSSL_3.0.0`. The ssl3 repo therefore consumes the staging **deb** packages
via a second builder script, `build-tarball-deb.sh`, selected by a `/etc/os-release`
dispatcher in `%build`. The verification gate enforces each variant's OpenSSL promise
via a versioned-symbol-needs audit, so any future drift fails the build loudly.
Documented divergence: the ssl3 tarball bundles python 3.10 — the Ubuntu 22.04
distro python — while ssl1.1/ssl3.5 bundle 3.12.)*

- Archs: `[x86_64]` on every repo.
- Single project-config: `Type: simpleimage` globally, plus per-repo
  `%if "%_repository" == "…"` blocks carrying the `ExpandFlags`/`Prefer` hints the
  base needs (mirroring `staging/17/project.yaml` prjconf). OBS defines
  `%_repository` in every build config (`BSSched/ProjPacks.pm` prepends
  `%define _repository <repo>`), so the same conditionals also work inside the
  `simpleimage` recipe, which is parsed as an RPM spec.
- **Publishing: enabled on all three repos** — the produced `.tar.gz` is directly
  downloadable from each repo's publish tree.
- OBS builds the one package once per repository → three artifacts per checkin;
  no duplicated package files, no copy-identity test needed.

### The simpleimage package

One copy of each file. Per-variant differences are expressed with
`%if "%_repository"` conditionals inside `simpleimage` (the EL10 base has no
`python3.12` package name — its default `python3` *is* 3.12):

```
%if "%_repository" == "ssl3.5"
BuildRequires:  python3
BuildRequires:  python3-pip
BuildRequires:  python3-devel
%else
BuildRequires:  python3.12
BuildRequires:  python3.12-pip
BuildRequires:  python3.12-devel
%endif
```

`Version:` is plain `%!{PG_VERSION}` — metadata only; it no longer drives the
artifact name (see below). The `TARBALL_SSL_VARIANT`/`TARBALL_PYTHON_PKG` macros
are gone.

`obs/simpleimage` (macro-expanded at sync time) — POC preamble adapted to staging:17
package names and macros:

```
#!NoTarBall
#!NoSquashfs
Name:           percona-postgresql
Version:        %!{PG_VERSION}

# PostgreSQL server and all extensions
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-server
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-contrib
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-libs
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-plpython3
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-plperl
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-pltcl
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-devel
BuildRequires:  percona-pg_tde%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgaudit%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgaudit%!{PG_MAJOR_VERSION}_set_user
BuildRequires:  percona-pg_stat_monitor%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg_repack%!{PG_MAJOR_VERSION}
BuildRequires:  percona-wal2json%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgvector_%!{PG_MAJOR_VERSION}
BuildRequires:  percona-postgis35_%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg_gather
# Companion tools
BuildRequires:  percona-pgbouncer
BuildRequires:  percona-pgpool-II-pg%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgbackrest
BuildRequires:  percona-pgbadger
BuildRequires:  percona-patroni
BuildRequires:  percona-patroni-aws
BuildRequires:  etcd
BuildRequires:  python3-pysyncobj
# Language runtimes (python via the %if "%_repository" conditional shown above)
BuildRequires:  perl
BuildRequires:  perl-libs
BuildRequires:  perl-devel
BuildRequires:  tcl
BuildRequires:  tcl-devel
# Build tools
BuildRequires:  patchelf
BuildRequires:  file

%build
exec bash /usr/src/packages/SOURCES/build-tarball.sh
```

Notes:

- The exact RPM names above (`percona-pgvector_…`, `percona-postgis35_…`,
  `percona-pgpool-II-pg…`, extension list vs the official tarball contents, e.g.
  pg_cron / pg-telemetry) are **verified against staging:17 build results and the
  official tarball structure-diff during implementation** — the POC list is the
  starting point, and it may need per-repo `%if` guards if names differ across bases.
- Output artifact: `percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz` — **exactly**
  the official name, including the dash before the arch. The recipe's own
  `Name-Version_ARCH` naming cannot vary per repository (it reads the tags with a raw
  `sed`, no macro expansion), so the `%build` script writes the artifact itself into
  `/usr/src/packages/OTHER/` (the directory OBS collects results from) and creates no
  `/.simpleimage.tar.gz` (which makes the recipe's rename step a no-op). The name is
  fully self-derived inside the buildroot: PG version from the installed server
  package (`rpm -q` / `dpkg-query`), SSL variant mapped from the buildroot's platform
  (RPM side: EL major from `/etc/os-release` `PLATFORM_ID` with a glibc dist-tag
  fallback, 8→ssl1.1, 10→ssl3.5, 9→fatal since the ssl3 rebase; deb side:
  `ubuntu`+`22.04`→ssl3; anything unmapped fails the build loudly), arch from
  `uname -m`. *(An openssl-version-based mapping was originally specified but is
  impossible: EL9 and EL10 both ship OpenSSL 3.5 now.)*
- Version bumps are automatic: `PG_VERSION` derives from `PG_MINOR_VERSION` in
  `staging/17/macros.yaml`, which is already bumped during release prep.
- All build logic lives in `build-tarball.sh`, not inline in `%build`: the `%build`
  body is piped through `sed | chroot sh -x` (fragile for non-trivial scripts), and a
  standalone script can be exercised locally in a container. The script is macro-free —
  it discovers the PG major version from `/usr/pgsql-*` and probes perl/tcl/python
  versions at run time (replacing the POC's hardcoded `PG_MAJOR=17` / `PY_VER=3.12`
  where practical) — so the same script serves all variant repos and future PG majors.

### The %build pipeline (`build-tarball.sh`)

The POC `%build` body, cleaned up and parameterized. Runs as root inside the chroot
after OBS installs the BuildRequires closure:

1. **Stage components under `/opt/percona-*`** (per-component prefix dirs, official
   layout):
   - `percona-postgresql<V>`: `/usr/pgsql-<V>/{bin,lib,share,include}` + extension docs;
     drop RPM service helpers (`postgresql-<V>-*` scripts); `gather.sql` into `bin/`.
   - `percona-pgbouncer`, `percona-pgpool-II`, `percona-pgbackrest`: binaries from
     `/usr/bin`, configs from `/etc/<tool>`, docs/licenses from `/usr/share/doc`.
   - `percona-pgbadger`: flat layout (script + man page + license, no `bin/`).
   - `percona-patroni`: entry-point scripts with shebangs rewritten to the bundled
     python; patroni + its python deps copied into the bundled python's
     `site-packages` (staging's `python3-*` packages are built for python 3.12, so
     compiled extensions match the bundled runtime).
   - `percona-etcd`: static Go binaries, no `lib/`.
   - `percona-python3`, `percona-perl`, `percona-tcl`: full runtime bundling with
     portable-execution fixes — python wrapped with `PYTHONHOME` (+ `lib64` symlink for
     `sys.platlibdir`), libperl copied into `CORE/` and `perl` RPATH-pointed at it,
     `tclsh` wrapper exporting `TCL_LIBRARY`/`TCLLIBPATH`.
2. **Bundle shared libraries** via the POC's 3-pass `ldd` walk (`bundle_deps`), copying
   symlink families into each component's `lib/`, filtered by the **official system-lib
   exclusion list** (matches `pg_tarballs_builder.sh`): glibc family, `ld-linux`,
   `libnss_*`, `libgcc_s`/`libstdc++`, compression libs (z, bz2, lz4, lzma, zstd),
   systemd, selinux, pam, audit, cap, econf, gcrypt/gpg-error, **OpenSSL**, pcre2,
   **tinfo/readline**, idn2, unistring, nghttp2, expat, tirpc. These stay
   host-provided. Exception: OpenSSL **is** bundled into `percona-python3/lib`
   (python's `_hashlib` is compiled against the build-env OpenSSL; POC behavior).
3. **Wrappers matching the official tarball:**
   - `psql` → `psql.bin` + wrapper that LD_PRELOADs host readline (falls back to
     bundled libedit behavior when absent).
   - `postgres` → `postgres.real` + wrapper exporting `PERL5LIB` and `TCL_LIBRARY`
     pointing at `/opt/percona-perl` / `/opt/percona-tcl` (docs install flow copies
     the runtimes to `/opt`).
4. **Patch RPATHs** (`patch_rpath` + POC step 14): `'$ORIGIN/../lib'` for `bin/`,
   `'$ORIGIN'` for `lib/`; `postgres`/`postmaster` and `plperl.so`/`plpython3.so`/
   `pltcl.so` additionally get `/opt/percona-python3/lib`, the perl `CORE` dir, and
   `/opt/percona-tcl/lib` appended (matching official RUNPATHs).
5. **Pre-tar verification (build fails on error — addition over the POC):**
   - DT_NEEDED soname audit over `/opt` (`patchelf --print-needed`): every needed
     soname must pass the exclusion list or be bundled (dangling symlinks rejected).
     (Replaced the originally-specified `ldd` audit, which is blind inside a fully
     populated buildroot — missing libs still resolve from `/usr/lib64`.)
   - Smoke: `bin/initdb --version`, `bin/postgres.real --version`,
     `percona-python3/bin/python3 -c 'import ssl, yaml'`,
     `percona-patroni/bin/patronictl version` — all with RPATH/wrapper resolution only.
6. **Create the artifact ourselves, with the official name:** derive the full name
   inside the buildroot (PG version from the server RPM, SSL variant from
   `openssl-libs`, arch from `uname -m`) and
   `tar -czf /usr/src/packages/OTHER/percona-postgresql-<ver>-<variant>-linux-<arch>.tar.gz`
   from `/opt`. `#!NoTarBall` keeps the recipe from tarring the buildroot, and with no
   `/.simpleimage.tar.gz` present its rename step is a no-op — OBS collects our file
   from `OTHER/` as the build result. No buildroot pruning, no `rm -rf` tricks.

### percona-obs tooling impact

None expected. The `tarballs/` dir has the same shape as `containers/ubi*/`:
a colon-named subproject with `project.yaml` and a package whose `obs/` files sync
verbatim with macro expansion (a package is any dir with an `obs/` subdir —
`common.is_package`). Implementation includes a verification step that nothing in
`targets.py` / `cmd_sync.py` / `cmd_project.py` special-cases containers.

### Testing

1. **Script-level:** `shellcheck` on `build-tarball.sh`; fast iteration by running the
   script in a Rocky 9 container with staging RPMs preinstalled (no OBS round-trip).
2. **PR project in production OBS:** open a PR (manually) adding the `tarballs/`
   layout; the `obs-pr-sync` workflow creates a PR project in production OBS that
   builds the tarball packages. Check build results and download the produced
   tarball artifacts from there.
3. **Acceptance:** on a container of a *different* distro with no PostgreSQL
   (e.g. `ubuntu:24.04` against the ssl3 variant — the "unsupported distro" scenario):
   untar the PR-project artifact following the docs install flow (extract, copy
   `percona-{python3,perl,tcl}` to `/opt`), then `initdb`, `pg_ctl start`, `psql`
   smoke queries, `CREATE EXTENSION pg_tde`, `patronictl version`. Structure-diff the
   tarball against the official 17.10 tarball (top two levels, per component).
4. The PR is merged only after acceptance passes.

## Known caveats (documented, accepted)

- RPM builds use `--with-system-tzdata=/usr/share/zoneinfo`: the host must have tzdata
  installed (virtually always true).
- Tarball binaries are the RPM builds (`--prefix=/usr/pgsql-<V>`); `pg_config` reports
  those original paths even though runtime path resolution is relocatable.
- OpenSSL versions come from the base distro (EL8 = 1.1.1, EL9 = 3.x, EL10 = 3.5)
  rather than Percona-pinned source builds (exception: python3's bundled OpenSSL).
- The PL runtime wrappers hardcode `/opt/percona-{python3,perl,tcl}` (as the official
  tarballs do) — PL/Perl, PL/Python, PL/Tcl require the runtimes to be copied to
  `/opt` per the install docs.

## Open questions for implementation

- Exact `BuildRequires` package names/list — verify against `ppg:staging:17` build
  results per repo and the official tarball structure-diff (pg_cron, pg-telemetry,
  haproxy presence; pgvector/postgis/pgpool RPM naming).
- Confirm Rocky 10 ships OpenSSL 3.5 (naming of the `ssl3.5` variant depends on it).
- Confirm where published simpleimage artifacts land in the publish tree URL layout.
- Confirm the `obs-pr-sync` workflow correctly creates PR projects for the *brand-new*
  subproject (`ppg:staging:17:tarballs` does not exist in production yet), including
  its repo path rewrites against the PR project namespace.
- Python runtime availability per base: `python3.12` exists on EL8/EL9 as parallel
  stacks and is the default on EL10 — the script's version probing must handle both
  (`/usr/bin/python3.12` vs `/usr/bin/python3`).

## Rejected alternatives

- **Port `pg_tarballs_builder.sh` into `%build`:** OBS chroots have no network; all ~30
  upstream source tarballs would need vendoring as OBS sources; hours-long builds;
  duplicates what the RPM packages already build.
- **CI-side tarball build (GitHub Actions + `dnf --installroot`):** abandons the goal of
  building in OBS; no OBS rebuild triggers; parallel build infrastructure.
- **Root-overlay or full-chroot tarball models:** rejected in favor of matching the
  official documented layout (drop-in replacement for the existing deliverable).
- **Buildroot pruning via final `rm -rf` (first spec revision):** superseded by the
  POC's `#!NoTarBall` + self-created `/.simpleimage.tar.gz` of `/opt` — strictly safer
  and simpler.
