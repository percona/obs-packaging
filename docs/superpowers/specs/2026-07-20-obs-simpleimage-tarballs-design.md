# OBS simpleimage Tarballs for Percona PostgreSQL — Design

**Date:** 2026-07-20 (revised same day: real POC supplied, scope expanded to full
component set; revised 2026-07-21: variants as repositories, ssl3 temporarily
deb-based; revised 2026-07-22: two-variant matrix — ssl3 back on EL9 via the
staging pgcrypto patch, ssl3.5 dropped, deb builder removed; revised
2026-07-28: QA round — see the revision note below)
**Status:** Implemented (branch `tarballs-simpleimage`)

## Revision note — 2026-07-28 QA round

A QA pass against the built artifacts drove six changes; the design sections
below have been updated where they described the superseded mechanisms:

1. **Compiled `/tmp` socket defaults** (d11e9c8, 1170e11): the builder
   rewrites the RPM-compiled `/run/postgresql` socket-dir C string constants
   to `/tmp` in place in every bundled ELF (same-length NUL-padded), so the
   server, `initdb`'s generated config (any invocation form) and every libpq
   client default to a `/tmp` unix socket — no wrappers, no `PGHOST`,
   matching the official binaries' compiled defaults. Gates: zero-match
   FATAL, a residual byte-string audit over all bundled ELFs, and a
   longest-first replacement-pattern table.
2. **Zero-env PL languages** (c4beb06, 4ce65ba, 5fe49b2, e08a04f):
   from-source `/opt`-prefixed runtime packages in `ppg:common:deps` —
   `percona-tarball-perl` (5.26.3 EL8 / 5.32.1 EL9), `percona-tarball-tcl`
   (8.6.10), `percona-tarball-python3` (3.12.13) — with every path compiled
   to the `/opt` prefix; plperl/pltcl/plpython3 resolve them via RUNPATHs, so
   all three PLs work under a bare `postgres -D` start from an empty
   environment. The postgres/initdb/psql-`PGHOST`/python3/tclsh wrappers are
   all gone (psql retains only the readline shim).
3. **Perl version constraint — documented, not fixed** (user decision):
   `plperl.so` is ABI-tied to the distro libperl the PG RPM was built
   against, so the bundled perl must be 5.26.3 (ssl1.1) / 5.32.1 (ssl3). The
   official tarball ships 5.38 because it builds PostgreSQL against its own
   perl — replicating that would change the shipped RPM product.
4. **haproxy component added** (e08a04f): eleven components now,
   file-for-file official layout parity.
5. **Python bytecode stripped** (e08a04f): zero `.pyc`/`__pycache__` in the
   artifact (official also ships none); gate-enforced.
6. **`import ssl` on ALL OpenSSL 3.x hosts** (84e3ec1, beats official
   parity): `percona-tarball-python3` patches CPython's `_ssl`/`_hashlib` to
   stay at `OPENSSL_3.0.0` versioned symbols; a spec `%check` gate pins the
   promise. The official tarball's python fails `import ssl` on 3.0 hosts.

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
  python3/perl/tcl runtimes. *(2026-07-28: haproxy added — eleven components,
  full official layout parity.)*
- Two SSL variants (ssl1.1, ssl3; ssl3.5 was dropped — see the 2026-07-22
  revision note); x86_64 only for now.
- Tarballs rebuild automatically when any package in their dependency closure changes.

## Non-Goals (this iteration)

- aarch64 builds.
- Bit-identical parity with the official from-source tarballs (behavioral/layout parity
  is the target, not identical binaries).
- Debian-based tarball variants.
- ~~haproxy (present in the official tarball; not in the POC BuildRequires — added later
  if the structure-diff shows it is required for parity)~~ *(added 2026-07-28:
  the QA structure-diff showed it is required for parity — see revision note.)*

## Design

### Project & tree structure

*(Revised 2026-07-21, user decision: SSL variants are **repositories** of a single
subproject, not separate subprojects.)*

One subproject with one package; each SSL variant is an OBS repository whose path
chain points at a different EL base of `ppg:staging:17`:

```
root/ppg/staging/17/tarballs/            → ppg:staging:17:tarballs
├── project.yaml                          # repos: ssl1.1, ssl3
└── percona-postgresql-tarball/
    └── obs/
        ├── simpleimage
        └── build-tarball.sh
```

Path chains listed explicitly — OBS only expands the last path transitively:

| Repository | Path chain | Host ABI targeted |
|---|---|---|
| `ssl1.1` | `ppg:staging:17/RockyLinux_8` + `ppg:common:deps` + EPEL 8 + Rocky 8 (appstream, baseos, devel) | glibc ≥ 2.28, OpenSSL 1.1 |
| `ssl3` | `ppg:staging:17/RockyLinux_9` + `ppg:common:deps` + EPEL 9 + Rocky 9 | glibc ≥ 2.34, OpenSSL 3.0+ |

*(Revised 2026-07-21: ssl3 was originally Rocky 9-based, but RHEL 9.8 rebased to
OpenSSL 3.5 and the EL9 staging `pgcrypto.so` references `OPENSSL_3.4.0` symbols —
breaking the "OpenSSL 3.0 hosts" promise; ssl3 was moved to an Ubuntu 22.04 deb
base with a second builder script. The verification gate enforces each variant's
OpenSSL promise via a versioned-symbol-needs audit, so any future drift fails the
build loudly.)*

*(Revised 2026-07-22: the Ubuntu-deb ssl3 was abandoned — the PGDG deb layout is
non-relocatable (multiarch lib paths, split `/usr/share/postgresql` trees, tools
hardwired to `/usr/lib/postgresql/<V>`; verified against PGDG's own packages), so
it cannot reproduce the official `/opt/percona-*` tarball layout. ssl3 is back on
the EL9 base: the `OPENSSL_3.4.0` reference was fixed at the source instead —
staging `percona-postgresql` now carries a pgcrypto patch avoiding the
`EVP_MD_CTX_get_size_ex()` OpenSSL-3.4 API, so EL9-built binaries stay at
`OPENSSL_3.0.0` and the gate's strict `OPENSSL_3\.0\.[0-9]*` policy passes.
ssl3.5 (RockyLinux_10 base) was dropped as redundant: with the pgcrypto fix, the
ssl3 tarball already runs on every OpenSSL 3.x host, including 3.5 ones. The deb
builder `build-tarball-deb.sh` and the `%build` os-release dispatcher were
removed; see "Rejected alternatives".)*

- Archs: `[x86_64]` on every repo.
- Single project-config: `Type: simpleimage` globally, plus per-repo
  `%if "%_repository" == "…"` blocks carrying the `ExpandFlags`/`Prefer` hints the
  base needs (mirroring `staging/17/project.yaml` prjconf). OBS defines
  `%_repository` in every build config (`BSSched/ProjPacks.pm` prepends
  `%define _repository <repo>`), so the same conditionals also work inside the
  `simpleimage` recipe, which is parsed as an RPM spec.
- **Publishing: enabled on both repos** — the produced `.tar.gz` is directly
  downloadable from each repo's publish tree.
- OBS builds the one package once per repository → two artifacts per checkin;
  no duplicated package files, no copy-identity test needed.

### The simpleimage package

One copy of each file. Both remaining variants are EL bases with identical
package naming (the parallel `python3.12` stack exists on EL8 and EL9), so the
recipe needs no `%if "%_repository"` conditionals at all — per-variant
differences live only in the project config's prjconf blocks. *(The mechanism
remains available: OBS defines `%_repository` in the recipe too, and earlier
revisions used it for the ssl3.5 python naming and the deb branch.)*

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

- *(2026-07-28: the distro `perl`/`perl-libs`/`perl-devel`/`tcl`/`tcl-devel`
  runtime BuildRequires shown above were replaced by
  `percona-tarball-{perl,tcl,python3}`, and `percona-haproxy` was added — the
  synced `obs/simpleimage` is the current list; the block above is kept as the
  original design snapshot.)*
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
  package (`rpm -q`), SSL variant mapped from the buildroot's EL major
  (`/etc/os-release` `PLATFORM_ID` with a glibc dist-tag fallback: 8→ssl1.1,
  9→ssl3; anything unmapped fails the build loudly), arch from `uname -m`.
  *(An openssl-version-based mapping was originally specified but is
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
   - `percona-python3`, `percona-perl`, `percona-tcl`: *(revised 2026-07-28)*
     installed directly into `/opt` by the `percona-tarball-{python3,perl,tcl}`
     BuildRequires — from-source builds whose every path (`sys.prefix`, `@INC`,
     `TCL_LIBRARY`) is compiled to the `/opt` prefix, so no flattening from
     system locations and no env-var wrappers. The script only asserts the
     trees, adds a few utility scripts (syncobj_admin, jp.py, ydiff, pip
     symlink), copies patroni's site-packages in, and bundles libcrypt next to
     libperl. *(The POC mechanism — `PYTHONHOME` wrapper, libperl copied from
     the distro tree, `TCL_LIBRARY` wrapper — is superseded; see Rejected
     alternatives.)*
2. **Bundle shared libraries** via the POC's 3-pass `ldd` walk (`bundle_deps`), copying
   symlink families into each component's `lib/`, filtered by the **official system-lib
   exclusion list** (matches `pg_tarballs_builder.sh`): glibc family, `ld-linux`,
   `libnss_*`, `libgcc_s`/`libstdc++`, compression libs (z, bz2, lz4, lzma, zstd),
   systemd, selinux, pam, audit, cap, econf, gcrypt/gpg-error, **OpenSSL**, pcre2,
   **tinfo/readline**, idn2, unistring, nghttp2, expat, tirpc. These stay
   host-provided. Exception: OpenSSL **is** bundled into `percona-python3/lib`
   (python's `_hashlib` is compiled against the build-env OpenSSL; POC behavior).
3. **Wrapper matching the official tarball** *(revised 2026-07-28 — one left)*:
   - `psql` → `psql.bin` + wrapper that LD_PRELOADs host readline (with a
     `libreadline.so.7` symlink fallback for the EL8-built binary).
   - `postgres`, `initdb` and every other binary ship REAL — the former
     `postgres` env wrapper (`PERL5LIB`/`TCL_LIBRARY`/`PYTHONHOME`) and the
     initdb wrapper are gone (see Rejected alternatives); the PL `.so`
     RUNPATHs plus the compiled-in `/opt` runtime paths and the compiled
     `/tmp` socket default (step 4a) replace them.
4. **Patch RPATHs** (`patch_rpath` + step 14): `'$ORIGIN/../lib'` for `bin/`,
   `'$ORIGIN'` for `lib/`; `plperl.so`/`plpython3.so`/`pltcl.so` get RUNPATHs
   pointing at the perl `CORE` dir, `/opt/percona-python3/lib` and
   `/opt/percona-tcl/lib` (matching official RUNPATHs). *(Revised 2026-07-28:
   the `postgres` binary itself needs only `$ORIGIN/../lib` — the loader
   resolves a dlopened PL's NEEDED libs through the PL's own RUNPATH.)*
   **4a. Compiled socket-dir patch** *(added 2026-07-28, step 14a)*: rewrite
   the RPM-compiled `/run/postgresql` socket-dir C string constants (all four
   spellings, longest-first) to `/tmp` in place in every bundled ELF —
   same-length NUL-padded, so no ELF offsets change. Zero patched files is a
   FATAL (the RPMs stopped compiling the string in → human look needed).
5. **Pre-tar verification (build fails on error — addition over the POC):**
   - DT_NEEDED soname audit over `/opt` (`patchelf --print-needed`): every needed
     soname must pass the exclusion list or be bundled (dangling symlinks rejected).
     (Replaced the originally-specified `ldd` audit, which is blind inside a fully
     populated buildroot — missing libs still resolve from `/usr/lib64`.)
   - Per-variant OpenSSL host-ABI audit (versioned symbol needs against
     libssl/libcrypto; the percona-python3 tree is exempt — it bundles its
     own OpenSSL copy).
   - Residual socket-dir audit: no bundled ELF may still contain the byte
     string `/run/postgresql` (proves 4a ran and catches re-staged copies).
   - Component inventory: exactly the eleven expected `/opt/percona-*` dirs.
   - Python bytecode audit: zero `.pyc`/`.pyo`/`__pycache__` under `/opt`.
   - Smoke: `bin/initdb --version`, `bin/postgres --version`, and — under
     `env -i`, proving the zero-env promise — the bundled python
     (`import ssl, yaml`, `import patroni`), perl (`use strict`) and tclsh,
     plus `haproxy -v`.
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
  installed (virtually always true, but absent on some minimal images).
- Tarball binaries are the RPM builds (`--prefix=/usr/pgsql-<V>`); `pg_config` reports
  those original paths even though runtime path resolution is relocatable.
- OpenSSL versions come from the base distro (EL8 = 1.1.1, EL9 = 3.5 since
  Rocky 9.8) rather than Percona-pinned source builds (exception: python3's
  bundled OpenSSL). The per-variant symbol-needs gate — plus the pgcrypto and
  CPython `_ssl`/`_hashlib` source patches that pin EL9-built binaries at
  `OPENSSL_3.0.0` — is what keeps the host promise honest despite the newer
  buildroot OpenSSL.
- The PL `.so` RUNPATHs and the runtimes' compiled-in paths hardcode
  `/opt/percona-{python3,perl,tcl}` (as the official tarballs do) — PL/Perl,
  PL/Python, PL/Tcl require the runtimes to be copied to `/opt` per the
  install docs. *(2026-07-28: this replaced the env-var wrappers; the old
  PYTHONHOME-leaks-into-server-children caveat is obsolete — no environment
  variables are set anywhere.)*
- The bundled perl is the distro-matched 5.26.3 (ssl1.1) / 5.32.1 (ssl3), not
  the official tarball's 5.38: `plperl.so` is ABI-tied to the distro libperl
  the PG RPM was built against. Shipping 5.38 would require building the PG
  RPM itself against a custom perl — a product change, out of scope.
- Host prerequisites beyond the glibc/OpenSSL floors: a non-root OS user for
  the server, host readline for interactive psql
  (`libreadline8`/`libreadline8t64`), tzdata, and the `/opt` copy step above.
  No `/run/postgresql` directory and no environment variables.

## Open questions for implementation

- Exact `BuildRequires` package names/list — verify against `ppg:staging:17` build
  results per repo and the official tarball structure-diff (pg_cron, pg-telemetry,
  haproxy presence; pgvector/postgis/pgpool RPM naming).
- ~~Confirm Rocky 10 ships OpenSSL 3.5 (naming of the `ssl3.5` variant depends on
  it).~~ Confirmed (it does), then mooted: the ssl3.5 variant was dropped on
  2026-07-22 as redundant with the fixed ssl3.
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
- **Ubuntu 22.04 deb-based ssl3 (2026-07-21 revision, removed 2026-07-22):** built
  the ssl3 variant from staging's Ubuntu 22.04 debs (whose OpenSSL 3.0.2 base
  guaranteed only `OPENSSL_3.0.0` symbol needs) via a parallel
  `build-tarball-deb.sh` and a `%build` os-release dispatcher. Abandoned because
  the PGDG deb layout is non-relocatable — multiarch lib dirs
  (`/usr/lib/x86_64-linux-gnu`), split `/usr/share/postgresql` trees, and tools
  hardwired to `/usr/lib/postgresql/<V>` (verified against PGDG's own packages) —
  unlike the PGDG RPM `/usr/pgsql-NN` prefix the official tarball layout derives
  from. Superseded by fixing the root cause: the staging pgcrypto patch keeps
  EL9-built binaries at `OPENSSL_3.0.0`, so ssl3 builds honestly from Rocky 9
  again. The deb builder survives in git history for reference.
- **`postgres` env wrapper (`PERL5LIB`/`TCL_LIBRARY`/`PYTHONHOME`) for the PLs
  (original design, removed 2026-07-28):** broke whenever the server was
  started without the wrapper (bare `postgres -D` — the QA repro), and its
  `PYTHONHOME` leaked into every server child (`archive_command` etc.).
  Superseded by the `/opt`-prefixed `percona-tarball-*` runtimes with
  compiled-in paths.
- **initdb wrapper + psql `PGHOST` export for the `/tmp` socket (removed
  2026-07-28):** the initdb wrapper missed the positional `initdb DATADIR`
  form and only two of the many libpq clients were covered. Superseded by
  patching the compiled `DEFAULT_PGSOCKET_DIR` string in every bundled ELF.
- **python3/tclsh env wrappers (removed 2026-07-28):** same class — any
  wrapper bypass (and the embedded interpreter case, which never runs the
  wrapper) broke; compiled-in prefixes need no wrapper.
