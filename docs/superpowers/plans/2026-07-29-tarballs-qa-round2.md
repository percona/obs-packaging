# Tarballs QA Round 2 Fixes Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development or superpowers-extended-cc:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the three QA round-2 findings against the pr-2 tarballs at their roots: a lean, from-source GDAL+PROJ replacing EPEL's kitchen-sink chain (postgis_raster missing libs, FlexiBLAS constructor abort, missing GDAL/PROJ data), a libedit-built `percona-psql` replacing the readline-linked psql (works on minimal hosts, no GPL question), a vetted universal exclusion baseline, and gates/battery that catch this class before QA does.

**Root causes (evidence in scratchpad `qa3/`):**
1. `postgis_raster → libgdal.so.30 (EPEL GDAL 3.4.3 / EL8: .so.26 GDAL 3.0.4)` drags ~70 libs official never ships. Its chain needs `libtirpc.so.3` (dap/netcdf/hdf), `libexpat.so.1` (gdal/kml), `libpcre2-posix.so.3` (metis) — all on `SYSTEM_LIBS_EXCLUDE` (copied from the official *builder* list, which was calibrated for official's 28-dep from-source GDAL). Minimal hosts lack them (probed: debian:12/ubuntu:24.04 lack tirpc+pcre2-posix+expat; rocky9-minimal lacks tirpc+expat). Official *bundles* pcre2-8/posix.
2. Rocky crash = `libarmadillo → {libarpack,libsuperlu} → libflexiblas.so.3`, whose ELF constructor unconditionally `dlopen`s `libflexiblas_netlib.so` from compiled-in `/usr/lib64/flexiblas/` and `abort()`s when absent (stock RHEL/Rocky don't install `flexiblas-netlib`). A dlopen'ed plugin — invisible to the NEEDED-based bundling and audit. Reproduced Rocky 9.8 + 10.2 with gdb backtrace. Also found: bundled libgdal/libproj compile in `/usr/share/{gdal,proj}` → no `proj.db`/GDAL_DATA → CRS ops will fail at runtime.
3. psql: our RPM `psql.bin` links `libreadline.so.7/8`; minimal Debian/Ubuntu ship no readline at all. Official compiles psql `--with-libedit-preferred` against a bundled libedit (BSD) and only *optionally* preloads host readline. A libedit *shim* is not viable for our binary (6 symbols missing: rl_completion_matches, rl_variable_bind, history_truncate_file, …).

**User decisions (2026-07-29):**
- Issues 1+2+data: **lean `percona-gdal` (+ matching `percona-proj`) rebuild** in `ppg:common:deps`, RL8+RL9, distinct names, tarball-only (shipped PostGIS RPMs keep EPEL GDAL). Same soname series as what PostGIS linked: GDAL 3.0.4/`libgdal.so.26` + PROJ 6.3.2/`libproj.so.15` on EL8; GDAL 3.4.3/`libgdal.so.30` + PROJ 9.x/`libproj.so.25` on EL9. Official's driver set; data dirs compiled into the /opt prefix.
- Issue 3: **`percona-psql`** — PG 17.10 source configured `--with-libedit-preferred`, only `psql` installed; lives in the **tarballs project** (`ppg:staging:17:tarballs`, PG-version-bound) with dedicated build repositories added to its project config; the simpleimage repos consume it via a sibling path.
- Gates: **both** a build-time dlopen smoke of every `$libdir/*.so` extension AND a minimal-host all-extensions acceptance battery (no prerequisite packages beyond tzdata).

---

### Task 21: `percona-psql` package + tarballs project build repos

**Goal:** A libedit-linked `psql` built from the same PG 17.10 source as staging, produced inside the tarballs project on RL8/RL9 build repos, consumable by the ssl1.1/ssl3 simpleimage chroots.

**Files:**
- Modify: `root/ppg/staging/17/tarballs/project.yaml`
- Create: `root/ppg/staging/17/tarballs/percona-postgresql-tarball/package.yaml`
- Create: `root/ppg/staging/17/tarballs/percona-psql/{obs/_service,rpm/percona-psql.spec,package.yaml}`

**Design:**
- project.yaml: ADD repos `RockyLinux_8` and `RockyLinux_9` (path chains identical to ssl1.1/ssl3's current chains; `publish: false`); ssl1.1/ssl3 chains gain a FIRST path `subproject: ppg:staging:%!{PG_MAJOR_VERSION}:tarballs / repository: RockyLinux_8|9` (same-project sibling path — precedent: containers project.yaml references its own subproject). Prjconf: `Type: simpleimage` + `Binarytype: rpm` MUST become repo-scoped (`%if "%_repository" == "ssl1.1" || "%_repository" == "ssl3"`); the build repos keep default spec type. Existing per-repo Prefer/ExpandFlags blocks stay on the ssl repos; add `Prefer:` lines for `percona-gdal`/`percona-proj` (Task 22 — same-soname provides vs EPEL gdal-libs/proj will be "have choice").
- `percona-postgresql-tarball/package.yaml`: `build: {RockyLinux_8: false, RockyLinux_9: false}`. `percona-psql/package.yaml`: `build: {ssl1.1: false, ssl3: false}`.
- `percona-psql/obs/_service`: mirror `percona-postgresql/obs/_service` (obs_scm Percona-Lab/postgres `release-%!{PG_VERSION}.1`, filename `percona-psql`, tar+recompress, set_version for spec + `%!{PG_VERSION}`).
- Spec: `Name: percona-psql`, `Version: 1.0.0` placeholder (set_version), `BuildRequires: libedit-devel` (EL8: PowerTools = RockyLinux:8/devel ✓; EL9: CRB, reachable via RockyLinux:9/standard ✓ verified) + zlib-devel, openssl-devel (libpq in-tree link), bison/flex, gcc; **NO readline-devel**. `%build`: `./configure --prefix=/usr/pgsql-%{pgmajorversion} --with-libedit-preferred --with-openssl --without-icu` (minimal; psql needs only libpq/port/common) then `make -C src/bin/psql` (submakes libpq/port/common). `%install`: install ONLY `src/bin/psql/psql` to `%{_libexecdir}/percona-psql/psql` (non-conflicting path; the tarball script copies it to `$PG_PREFIX/bin/psql`). `__requires_exclude` libpq self-soname if needed; the binary must NEED `libedit.so.0`, `libtinfo.so.6`, `libpq.so.5` and NOT libreadline (spec %check asserts via readelf).
- PERCONA comments; changelog day-of-week correct.

**Acceptance Criteria:**
- [ ] `readelf -d psql` → NEEDED libedit.so.0 + libpq.so.5, zero libreadline; %check enforces it
- [ ] rpmbuild green rocky8 + rocky9 (local), psql runs against a server using its libedit line editing (`\conninfo`, history) on a minimal debian:12 container with NO readline installed
- [ ] percona-obs dry-runs clean for: the project (new repos + scoped prjconf), percona-psql, percona-postgresql-tarball (STANDING RULE: -P isv never without --dry-run); verify the loader renders the same-project sibling path correctly
- [ ] The scoped `Type:` prjconf is loader-valid (project.yaml parses; `%if` balanced)

### Task 22: `percona-gdal` + `percona-proj` (common:deps, RL8+RL9)

**Goal:** Lean, /opt-prefixed GDAL and PROJ whose sonames match what PostGIS linked on each base, with official's driver set and compiled-in data dirs — drop-in replacements for EPEL's libs inside the tarball only.

**Files:**
- Create: `root/ppg/common/deps/percona-proj/{obs/_service,rpm/*.spec,package.yaml}` — PROJ **6.3.2** (RL8, `libproj.so.15`) / the EPEL9-matching **9.x** (RL9, `libproj.so.25`; pick the version whose soname is 25 — verify against the ssl3 artifact's `libproj.so.25.9.6.0` → PROJ 9.6.0; our common:deps `proj` spec is already 9.6.0 — reuse its sources/patches as the template) — cmake `-DCMAKE_INSTALL_PREFIX=/opt/percona-proj` so `proj.db` lives at the compiled data path; BuildRequires sqlite-devel, libtiff-devel, libcurl-devel.
- Create: `root/ppg/common/deps/percona-gdal/{obs/_service,rpm/*.spec,package.yaml}` — GDAL **3.0.4** (RL8) / **3.4.3** (RL9) via `%if 0%{?rhel}` (two download_url sources from GitHub OSGeo/gdal releases). Autotools (both versions support it): `--prefix=/opt/percona-gdal`, explicit driver set mirroring official's libgdal NEEDED list (`--with-geos --with-proj=/opt/percona-proj --with-sqlite3 --with-libtiff --with-geotiff --with-png --with-jpeg --with-curl --with-xml2 --with-crypto --with-zstd --with-liblzma --with-lz4? --with-qhull --with-spatialite --with-freexl --with-expat --with-libjson-c --with-pcre2 --with-webp`) and explicit `--without-` for everything else (hdf4/hdf5/netcdf/dods-root(dap)/armadillo/poppler/mysql/odbc/libkml/xerces/cfitsio/gta/ogdi/openjpeg/jasper/gif?…). Data dir → `/opt/percona-gdal/share/gdal`. Build against `percona-proj` + EPEL geos-devel (geos soname `libgeos_c.so.1` stable).
- Both: `package.yaml` RL8+RL9 only; distinct names; NO provides filtering of the sonames — they must auto-Provide `libgdal.so.NN()(64bit)` / `libproj.so.NN()(64bit)` so PostGIS's Requires can be satisfied by them (Task 21/23 adds prjconf `Prefer:` to pick ours over EPEL in the ssl chroots).

**Acceptance Criteria:**
- [ ] rpmbuild green both bases; `readelf -d libgdal.so.NN` NEEDED surface ≈ official's (no armadillo/flexiblas/hdf/netcdf/dap/poppler/mariadb/odbc/kml/xerces); no `libtirpc`
- [ ] `strings libgdal | grep /opt/percona-gdal/share` and `strings libproj | grep /opt/percona-proj` show compiled data paths; `/opt/percona-proj/share/proj/proj.db` present
- [ ] `python3 -c "ctypes.CDLL('/opt/percona-gdal/lib/libgdal.so.NN')"` dlopen smoke OK (no constructor abort) from `env -i`
- [ ] ABI drop-in proof: in a rocky9 (and rocky8) container with PostGIS RPMs + our gdal/proj + PL RUNPATH simulation, `CREATE EXTENSION postgis; CREATE EXTENSION postgis_raster; SELECT postgis_raster_lib_version(); SELECT ST_AsText(ST_Transform(ST_SetSRID(ST_MakePoint(1,1),4326),3857));` all succeed (proj.db found, raster loads)
- [ ] isv dry-runs clean

### Task 23: build-tarball.sh integration — lean GDAL/PROJ, percona-psql, exclusion baseline, new gates

**Goal:** Tarball consumes the new packages; exclusion list becomes a vetted universal baseline; gates catch constructor aborts and non-universal leaks.

**Files:** `obs/simpleimage`, `obs/build-tarball.sh`, `root/ppg/staging/17/tarballs/project.yaml` (Prefer lines if not done in 21)

**Changes:**
- simpleimage: `BuildRequires: percona-psql percona-gdal percona-proj`. Ensure EPEL `gdal-libs`/`proj` are NOT pulled: PostGIS Requires resolve to ours via prjconf `Prefer: percona-gdal` / `Prefer: percona-proj` (verify with buildinfo after sync; if EPEL still lands in the chroot, add `Ignore:` or explicit conflicts).
- Bundling: `copy_deps` uses `ldd`, which resolves via the system loader — run the bundling pass with `LD_LIBRARY_PATH=/opt/percona-gdal/lib:/opt/percona-proj/lib` so `postgis_raster.so`'s `libgdal.so.NN`/`libproj.so.NN` resolve to OUR libs (and their lean deps), not EPEL's; assert afterwards that no bundled lib NEEDs `libflexiblas`/`libarmadillo`/`libhdf`/`libnetcdf`/`libdap` (FATAL) — the surplus must be gone.
- Data: stage `/opt/percona-gdal/share/gdal` and `/opt/percona-proj/share/proj` into `$PG_PREFIX/share/{gdal,proj}` — BUT the compiled paths are `/opt/percona-{gdal,proj}/share/...`, which only exist if the user copies those trees to /opt like the runtimes. Decide the layout to match the documented install flow: simplest = ship `percona-gdal`/`percona-proj` as additional /opt components (like percona-perl) → 13 components; OR compile GDAL/PROJ prefixes as `/opt/percona-postgresql17/...`? No — official compiles data into its own prefix. RECOMMENDED: two more top-level components (`percona-gdal`, `percona-proj`) copied to /opt by the documented step; PostGIS libs resolve libgdal/libproj via RUNPATH `$ORIGIN` (bundled copies in `$PG_PREFIX/lib`) while those libs find their data via compiled `/opt/percona-*/share`. Document; update the component-inventory gate (11 → 13).
- psql: copy `/usr/libexec/percona-psql/psql` → `$PG_PREFIX/bin/psql` (replacing the RPM psql); DELETE the readline wrapper entirely (no psql.bin); `libedit.so.0` bundles via copy_deps (not excluded). Assert `readelf -d bin/psql` has no libreadline NEEDED.
- SYSTEM_LIBS_EXCLUDE → **universal baseline** (comment the contract: "present on every supported minimal host"): glibc family (`libc libm libpthread libdl librt libresolv libnss_ ld-linux`), `libgcc_s libstdc++`, `libz libbz2 liblz4 liblzma libzstd`, `libsystemd libselinux libpam libpam_misc libaudit libcap libcap-ng`, `libgcrypt libgpg-error`, `libssl libcrypto` (variant contract), `libtinfo` (bash dep, universal — needed by libedit/psql). REMOVE: `libtirpc libnsl libeconf libpcre2-8 libpcre2-posix libexpat libreadline`. Add an assertion comment block listing the three probe images the baseline was verified against (debian:12, ubuntu:24.04, rockylinux:9-minimal) and a gate: every excluded token must appear in the baseline list literal (self-consistency).
- NEW gate — **extension dlopen smoke**: for every `$PG_PREFIX/lib/*.so` that is a PG extension module (has `Pg_magic_func`) run a `dlopen` via `"$PY_BIN" -c 'ctypes.CDLL(path, RTLD_NOW)'`... NOTE: extension .so files reference postgres backend symbols (unresolved without the server) — use `ctypes.CDLL(path, mode=RTLD_LAZY)` so constructors/NEEDED chains run but backend symbols stay lazy; the flexiblas abort WOULD have fired here. Run from `env -i` with only RUNPATH resolution (no LD_LIBRARY_PATH). FATAL on any failure; log each.
- Structure/inventory gate updates; smoke additions: `bin/psql --version` (libedit) and `postgis_raster` in the dlopen smoke list explicitly.

**Acceptance Criteria:**
- [ ] EL8 + EL9 container runs green with the new gates; bundled-lib count drops sharply (report before/after); NO libtirpc/expat/pcre2 needs against the host; NO flexiblas/armadillo/hdf/netcdf/dap anywhere
- [ ] e2e on a MINIMAL image with only tzdata (debian:12-slim or ubuntu:24.04, rocky9-minimal): psql works without readline; `CREATE EXTENSION postgis, postgis_raster` + `ST_Transform` + `ST_AddBand` work via bare `postgres -D`
- [ ] pytest/pyright/black green; isv dry-run clean

### Task 24: minimal-host all-extensions battery script + docs

**Goal:** A reusable battery that runs on minimal images with zero prerequisites beyond tzdata and exercises EVERY shipped extension.

**Files:** `docs/superpowers/plans/…` (battery script kept under `tests/tarball-battery/` or `root/ppg/staging/17/tarballs/percona-postgresql-tarball/battery/`? — decide: commit as `tools/tarball-acceptance.sh` at repo top level so QA can reuse it); `root/README.md`; spec doc revision note.

**Battery contents:** matrix = {debian:11 (ssl1.1), debian:12, ubuntu:22.04, ubuntu:24.04, rockylinux:9-minimal, rockylinux:10-minimal (ssl3)}; per host: untar, /opt copy of ALL `percona-*` runtime/data components, non-root user, bare `postgres -D`; then `for c in share/extension/*.control` → `CREATE EXTENSION <name> CASCADE` (pg_tde needs `shared_preload_libraries` → handled by a preload list; skip known-unloadable relocatable-only scripts gracefully with an allowlist); PostGIS deep checks (`ST_Transform`, `ST_AddBand`, `postgis_gdal_version()` shows GDAL_DATA found); psql line-editing sanity; zero-env clients; `patronictl`, `haproxy -v`; assert `/run/postgresql` never created; report table. Docs: README/spec updated (13 components, libedit psql, lean GDAL/PROJ, baseline contract, prerequisites = user + tzdata only + /opt copy).

### Task 25: acceptance gate (USER GATE) after user pushes

> **USER-ORDERED GATE — NON-SKIPPABLE.** Captured output for every criterion.

Run Task 24's battery against the rebuilt pr-2 artifacts on the full matrix; every extension loads on every host; QA's three flows (postgis_raster load on RHEL-family + Debian-family; no backend crash on Rocky 9/10; psql on Debian 11 without readline) explicitly green; plus all carried-over regressions.

---

## Execution notes
- Order: Task 21 ∥ Task 22 (disjoint) → Task 23 → Task 24 → Task 25 (gate).
- Standing rules: `git commit -s`, no AI attribution, never push/create PRs (user does), `-P isv` writes only with `--dry-run`.
- Highest-risk items: (a) same-soname Prefer resolution in the ssl chroots (EPEL gdal-libs vs ours) — verify with `osc buildinfo` after the first sync; (b) GDAL 3.0.4 (2020) building on modern EL8 toolchain (expect minor patches); (c) the same-project sibling repo path in project.yaml — confirm percona-obs handles it (containers precedent).

---

## Execution status — 2026-07-29

Tasks 21–24 implemented, each with spec+quality review, fix loop and scoped
re-review; final whole-round review (44ad255..HEAD) clean after one fix wave +
one follow-up. Commits: 181033a (rename) · 25b4047 (T21) · c3bd8ad 4af2766
c19a45b 4528249 (T22) · c1dc500 9e01256 (T23) · a6242ae 49a0312 66e14cb (T24) ·
b90ac24 ef347bc (final-review fixes: scoped `Ignore:` for PostGIS's by-name
GDAL/PROJ deps, property-based §0a assert, libpq requires-exclude, battery
warn/pty visibility, `ExcludeArch: aarch64`).

Validation moved to OBS mid-round (user decision): no local builds after Task 21;
compiled-artifact criteria are verified on OBS-built RPMs/tarballs in Task 25.

**Task 25 (user gate) — pending:** user syncs, OBS builds, then
`tools/tarball-acceptance.sh` on the downloaded ssl1.1/ssl3 artifacts.
First-build watch list (ordered by likelihood): §0a stray GDAL/PROJ (is the
scoped `Ignore:` honoured under `Type: simpleimage`? fallback = global
`Ignore:` lines in the ssl blocks) · percona-gdal EL9 `share/gdal` layout +
`gdalicon.png` gates · repo-scoped `Type:` on RockyLinux_8/9 · sibling path
delivering percona-psql · perl-5.26 module ExpandFlags inheritance on
RockyLinux_8 · dlopen gate count/postgis_raster · bundled-lib count drop ·
ssl3 SSL-ABI audit on libgdal (low).

## Gate result — 2026-08-26 (Task 25, PASS)

First OBS build failed at §0a: OBS does not apply prjconf `Ignore:` rules to
image-type (`simpleimage`) expansion, so EPEL GDAL/PROJ stayed in the chroot.
Fixed with the `percona-gis-compat` shim (da1e31c, c255628 — `Provides:` the
by-name deps, `Prefer:`'d; EL8 rpm has no `%elif`). Second build: both variants
green, all in-chroot gates passed (103 modules dlopen-tested).
`tools/tarball-acceptance.sh` on the pr-2 artifacts: **ACCEPTANCE PASSED** —
ssl1.1 (debian:11-slim, ubuntu:20.04) and ssl3 (debian:12-slim, ubuntu:22.04,
ubuntu:24.04, rockylinux 9/10-minimal); 7 hosts × 76/76 extensions; QA flows:
postgis_raster loads on Debian- and RHEL-family minimal hosts, no backend crash
on Rocky 9/10, psql (libedit) works with no host readline on all 7 hosts;
/tmp socket, PLs, ST_Transform, clients, `import ssl` all PASS. PG `lib/`
shrank 326→238 (ssl1.1) / 320→233 (ssl3); zero surplus libraries.
