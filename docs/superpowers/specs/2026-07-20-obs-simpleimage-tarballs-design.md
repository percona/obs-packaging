# OBS simpleimage Tarballs for Percona PostgreSQL — Design

**Date:** 2026-07-20
**Status:** Approved design, pending implementation plan

## Background

Besides RPM/DEB packages and container images, Percona distributes PostgreSQL as
binary tarballs for air-gapped systems and unsupported distros
(see <https://docs.percona.com/postgresql/17/tarball.html>). Today these are built
outside OBS by `percona/postgres-packaging/pg_tarballs/pg_tarballs_builder.sh`,
which compiles PostgreSQL and ~30 dependencies from source (network-dependent —
not runnable inside OBS build chroots).

This design generates equivalent tarballs **inside OBS** using the `simpleimage`
build format, repackaging the RPMs that `ppg:staging:<V>` already builds.

### Facts established during research

- **Official tarball layout** (inspected `percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz`):
  per-component top-level dirs (`percona-postgresql17/`, `percona-patroni/`, …), each with
  `bin/ lib/ share/ include/`. Third-party libs are bundled in `lib/`; **glibc and OpenSSL
  come from the host** — that is why ssl1.1 / ssl3 / ssl3.5 variants exist. Binaries carry
  `RUNPATH=${ORIGIN}/../lib:…`. Extension `.so` files sit directly in `lib/`.
- **simpleimage mechanics** (from obs-build source): the `simpleimage` file is parsed as an
  RPM spec preamble — **only `BuildRequires:` (plural) is recognized**; the old POC's
  `BuildRequire:` lines were silently ignored. OBS installs the dependency closure into the
  build chroot, runs the `%build` section chrooted as root, then tars **the entire buildroot**
  (everything except `/proc`, `/sys`, build metadata) into `Name-Version_ARCH.tar.gz`.
  `#!NoSquashfs` suppresses the additional squashfs artifact. Recipe sources are copied to
  `/usr/src/packages/SOURCES/` inside the chroot.
- `ppg:staging:17` already builds RockyLinux_8, RockyLinux_9, and RockyLinux_10 repos —
  the three bases needed for the ssl variants.
- `root/README.md` already reserves `staging/<V>/tarballs/`; the `containers/ubi*/`
  subprojects are the structural precedent (colon-named subproject, packages with `obs/`
  dirs synced verbatim, `%!{…}` macro expansion from cascading `macros.yaml`).

## Goals

- Produce a tarball equivalent in layout and consumption model to the official
  `percona-postgresql-<ver>-<ssl>-linux-x86_64.tar.gz`, built entirely in OBS from
  staging RPMs.
- First iteration scope: **server + extensions only** (the `percona-postgresql17/`
  component); three SSL variants; x86_64 only.
- Tarballs rebuild automatically when any package in their dependency closure changes.

## Non-Goals (this iteration)

- The other official components (patroni, pgbackrest, pgbouncer, pgpool-II, haproxy,
  etcd, pgbadger) and the bundled `percona-python3/perl/tcl` runtimes.
- aarch64 builds.
- Bit-identical parity with the official from-source tarballs (behavioral/layout parity
  is the target, not identical binaries).
- Debian-based tarball variants.

## Design

### Project & tree structure

Three variant subprojects, one per SSL generation, mirroring the `containers/` pattern:

```
root/ppg/staging/17/tarballs/
├── ssl1.1/                          → ppg:staging:17:tarballs:ssl1.1
│   ├── macros.yaml                  # - TARBALL_SSL_VARIANT: ssl1.1
│   ├── project.yaml
│   └── percona-postgresql-tarball/
│       └── obs/
│           ├── simpleimage
│           └── build-tarball.sh
├── ssl3/                            → ppg:staging:17:tarballs:ssl3     (RockyLinux_9)
└── ssl3.5/                          → ppg:staging:17:tarballs:ssl3.5   (RockyLinux_10)
```

Each `project.yaml` defines one repository whose path chain matches the corresponding
base in `ppg:staging:17`:

| Subproject | Repo | Path chain | Host ABI targeted |
|---|---|---|---|
| `tarballs:ssl1.1` | `RockyLinux_8` | `ppg:staging:17/RockyLinux_8` + Rocky 8 (baseos, appstream, devel) + EPEL 8 | glibc ≥ 2.28, OpenSSL 1.1 |
| `tarballs:ssl3` | `RockyLinux_9` | `ppg:staging:17/RockyLinux_9` + Rocky 9 + EPEL 9 | glibc ≥ 2.34, OpenSSL 3.x |
| `tarballs:ssl3.5` | `RockyLinux_10` | `ppg:staging:17/RockyLinux_10` + Rocky 10 + EPEL 10 | glibc ≥ 2.39, OpenSSL 3.5 |

- Archs: `[x86_64]`.
- Project-config: `Type: simpleimage`.
- **Publishing: enabled** — the produced `.tar.gz` is directly downloadable from the
  published repository tree of each variant project.

### The simpleimage package

The package files are **byte-identical across all three variants**; variant identity
comes from the subproject's `macros.yaml` and its repo path chain.

`obs/simpleimage` (macro-expanded at sync time):

```
#!NoSquashfs
Name:           percona-postgresql
Version:        %!{PG_VERSION}-%!{TARBALL_SSL_VARIANT}-linux

BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-server
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-contrib
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-libs
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-plperl
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-plpython3
BuildRequires:  percona-postgresql%!{PG_MAJOR_VERSION}-pltcl
BuildRequires:  percona-pg_tde%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgaudit%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgaudit%!{PG_MAJOR_VERSION}_set_user
BuildRequires:  percona-pg_stat_monitor%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg_repack%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgvector%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg_cron%!{PG_MAJOR_VERSION}
BuildRequires:  percona-wal2json%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg-telemetry%!{PG_MAJOR_VERSION}
BuildRequires:  patchelf

%build
exec bash /usr/src/packages/SOURCES/build-tarball.sh
```

Notes:

- `BuildRequires:` **must** be plural (obs-build ignores the singular form).
- Output artifact: `percona-postgresql-17.10-ssl3-linux_x86_64.tar.gz`
  (recipe naming is `Name-Version_ARCH.tar.gz`; the underscore before the arch differs
  from the official name — exact renaming, if needed, happens at release/download time).
- Version bumps are automatic: `PG_VERSION` derives from `PG_MINOR_VERSION` in
  `staging/17/macros.yaml`, which is already bumped during release prep.
- All build logic lives in `build-tarball.sh`, not inline in `%build`: the `%build`
  body is piped through `sed | chroot sh -x` (fragile for non-trivial scripts), and a
  standalone script can be exercised locally in a container. The script is macro-free —
  it discovers the PG major version from `/usr/pgsql-*` at run time — so it stays
  identical across variants and future PG majors.

### The %build pipeline (`build-tarball.sh`)

Runs as root inside the chroot after OBS installs the BuildRequires closure:

1. **Stage the component tree.** Copy `/usr/pgsql-<V>/{bin,lib,share,include,doc}` to a
   new top-level `/percona-postgresql<V>/`. RPM builds already place extension `.so`
   files directly in `/usr/pgsql-<V>/lib`, matching the official layout.
2. **Bundle shared libraries.** Walk every ELF in `bin/` and `lib/` with `ldd`; copy each
   resolved dependency into `/percona-postgresql<V>/lib/`, excluding **only**:
   - glibc family: `libc`, `libm`, `libdl`, `libpthread`, `librt`, `libresolv`,
     `ld-linux-*` (host-provided);
   - OpenSSL: `libssl`, `libcrypto` (host-provided — this is what defines the ssl
     variants).
   Everything else is bundled (libicu, libxml2, krb5/ldap chain, libpam, compression
   libs, …). Repeat the walk until a pass adds no new libraries (catches dependencies
   of copied libraries and `dlopen` users listed as `NEEDED`).
3. **Readline (deliberate divergence).** Official tarballs build `psql` against libedit
   plus a wrapper that LD_PRELOADs host readline. Our RPM `psql` links `libreadline`
   directly, so we bundle `libreadline` + `libtinfo` and ship no wrapper. Simpler,
   functionally equivalent.
4. **Patch RPATHs.** `patchelf --set-rpath '$ORIGIN/../lib'` on `bin/*`, `'$ORIGIN'` on
   `lib/*`. No `/opt` components are referenced. PostgreSQL relocates its compiled-in
   paths relative to the binary location at run time, so the tree works from any
   extraction directory.
5. **Pre-prune verification (build fails on error).**
   - `ldd` audit over the staged tree: zero `not found` beyond the deliberate
     exclusions.
   - `bin/initdb --version` and `bin/postgres --version` must run from the staged tree
     with `LD_LIBRARY_PATH` unset (RPATH must resolve everything).
6. **Prune.** Single final `rm -rf` of every top-level directory except
   `/percona-postgresql<V>` (a running `rm` survives its own binary being unlinked;
   the recipe's tar step runs outside the chroot afterwards). The tarball therefore
   contains exactly `./percona-postgresql<V>/`.

### percona-obs tooling impact

None expected. The `tarballs/ssl*/` dirs have the same shape as `containers/ubi*/`:
colon-named subprojects with `project.yaml` and packages whose `obs/` files sync
verbatim with macro expansion. Implementation includes a verification step that nothing
in `targets.py` / `cmd_sync.py` / `cmd_project.py` special-cases containers.

### Testing

1. **Script-level:** `shellcheck` on `build-tarball.sh`; fast iteration by running the
   script in a Rocky 9 container with staging RPMs preinstalled (no OBS round-trip).
2. **PR project in production OBS:** open a PR (manually) adding the `tarballs/`
   layout; the `obs-pr-sync` workflow creates a PR project in production OBS that
   builds the tarball packages. Check build results and download the produced
   tarball artifacts from there.
3. **Acceptance:** on a container of a *different* distro with no PostgreSQL
   (e.g. `ubuntu:24.04` against the ssl3 variant — the "unsupported distro" scenario):
   untar the PR-project artifact, `initdb`, `pg_ctl start`, `psql` smoke queries,
   `CREATE EXTENSION pg_tde`. Structure-diff `percona-postgresql17/` against the
   official 17.10 tarball's same component.
4. The PR is merged only after acceptance passes.

## Known caveats (documented, accepted)

- `plperl` / `plpython3` / `pltcl`: the `libperl`/`libpython`/`libtcl` shared libraries
  are bundled, but the interpreter *stdlib* must exist on the host. The official
  tarballs solve this with separate `percona-python3/perl/tcl` components — future
  iteration.
- RPM builds use `--with-system-tzdata=/usr/share/zoneinfo`: the host must have tzdata
  installed (virtually always true).
- Tarball binaries are the RPM builds (`--prefix=/usr/pgsql-<V>`); `pg_config` reports
  those original paths even though runtime path resolution is relocatable.
- OpenSSL versions come from the base distro (EL8 = 1.1.1, EL9 = 3.x, EL10 = 3.5)
  rather than Percona-pinned source builds.

## Open questions for implementation

- Exact `BuildRequires` package list — verify against `ppg:staging:17` build results
  per repo (PostGIS/sfcgal are excluded from this scope).
- Confirm Rocky 10 ships OpenSSL 3.5 (naming of the `ssl3.5` variant depends on it).
- Confirm where published simpleimage artifacts land in the publish tree URL layout.
- Confirm the `obs-pr-sync` workflow correctly creates PR projects for *brand-new*
  subprojects (`tarballs:ssl*` do not exist in production yet), including their
  repo path rewrites against the PR project namespace.

## Rejected alternatives

- **Port `pg_tarballs_builder.sh` into `%build`:** OBS chroots have no network; all ~30
  upstream source tarballs would need vendoring as OBS sources; hours-long builds;
  duplicates what the RPM packages already build.
- **CI-side tarball build (GitHub Actions + `dnf --installroot`):** abandons the goal of
  building in OBS; no OBS rebuild triggers; parallel build infrastructure.
- **Root-overlay or full-chroot tarball models:** rejected in favor of matching the
  official documented layout (drop-in replacement for the existing deliverable).
