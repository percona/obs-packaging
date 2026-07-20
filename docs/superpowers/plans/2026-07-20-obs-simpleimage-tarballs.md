# OBS simpleimage Tarballs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Percona PostgreSQL 17 binary tarballs (official layout, full component set) inside OBS via the `simpleimage` format, as three SSL-variant subprojects under `root/ppg/staging/17/tarballs/`.

**Architecture:** Each variant subproject (`ssl1.1`/`ssl3`/`ssl3.5`) builds against a different EL base (Rocky 8/9/10) of `ppg:staging:17`. A `simpleimage` recipe pulls the staging RPMs via `BuildRequires`; `build-tarball.sh` (adapted from the approved POC) stages components under `/opt/percona-*`, bundles non-system libs, patches RPATHs, verifies, and tars `/opt` itself (`#!NoTarBall`). Package files are byte-identical across variants; variant identity lives in per-subproject `macros.yaml`.

**Tech Stack:** OBS simpleimage (obs-build), bash, patchelf, RPM repos, `percona-obs` sync tooling (no Python code changes expected), pytest for the copy-identity test.

**Spec:** `docs/superpowers/specs/2026-07-20-obs-simpleimage-tarballs-design.md` (approved 2026-07-20, revised for full POC scope).

**User decisions (already made):**
- Tarball must match the official docs.percona.com layout (drop-in replacement deliverable).
- Full official component set (POC scope), including bundled python3/perl/tcl runtimes; haproxy excluded for now.
- One OBS subproject per SSL variant: `ppg:staging:17:tarballs:ssl1.1|ssl3|ssl3.5`; all three variants, x86_64 only.
- Approach A: repackage staging RPMs in `%build` (the POC's approach).
- Repository publishing **enabled** on tarball repos.
- Version strings use `%!{…}` macros as in containers (`PG_VERSION`, per-variant `TARBALL_SSL_VARIANT`).
- Testing via manually-opened PR → `obs-pr-sync` PR project in **production** OBS (no dev environment); merge only after acceptance passes.
- staging `python3-*` packages are already built against python 3.12 (no ABI mismatch with the bundled runtime).

---

## Reference facts for all tasks

- POC recipe: `~/Downloads/simpleimage` (PPG 17.9, Name/Version + BuildRequires + `%build` body). Task 1 imports its `%build` body into `build-tarball.sh` with listed modifications.
- Production OBS: profile `isv` → `https://api.opensuse.org`, rootprj `isv:percona`. **NEVER run a write operation with `-P isv` without `--dry-run`** (standing rule).
- Published staging repo (RPM-MD): `https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/17/RockyLinux_9/`
- Verified staging:17 RPM names: `percona-pgvector_17`, `percona-postgis35_17`, `percona-pgpool-II-pg17`, `percona-pg_cron_17`, `percona-pg_stat_monitor17`, `percona-pg_gather`, `percona-patroni`(+`-aws`), `percona-pgaudit17`, `percona-pgaudit17_set_user`. `percona-pg-telemetry` spec is `%{sname}%{pgrel}` — confirm exact binary name in Task 1 Step 2.
- `simpleimage` recipe output naming: `Name-Version_ARCH.tar.gz`, picked up from `/.simpleimage.tar.gz` when `#!NoTarBall` is set.
- Macro expansion: `%!{NAME}` tokens in synced `obs/` files are substituted from cascading `macros.yaml` (repo root → package dir). `staging/17/macros.yaml` defines `PG_MAJOR_VERSION: 17`, `PG_VERSION: 17.10`.

---

### Task 1: ssl3 variant subproject (reference variant)

**Goal:** Create `root/ppg/staging/17/tarballs/ssl3/` — `project.yaml`, `macros.yaml`, and the `percona-postgresql-tarball` package (`simpleimage` + `build-tarball.sh`) — complete and shellcheck-clean.

**Files:**
- Create: `root/ppg/staging/17/tarballs/ssl3/project.yaml`
- Create: `root/ppg/staging/17/tarballs/ssl3/macros.yaml`
- Create: `root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/simpleimage`
- Create: `root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/build-tarball.sh`

**Acceptance Criteria:**
- [ ] `simpleimage` uses only `%!{…}` macros defined in ancestor `macros.yaml` files (`PG_MAJOR_VERSION`, `PG_VERSION`, `TARBALL_SSL_VARIANT`, `TARBALL_PYTHON_PKG`)
- [ ] All `BuildRequires` names verified against the published staging repo (Step 2)
- [ ] `shellcheck --severity=error build-tarball.sh` → no errors
- [ ] `build-tarball.sh` contains no hardcoded PG major or python version (discovers at run time)

**Verify:** `shellcheck --severity=error root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/build-tarball.sh && bash -n root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/build-tarball.sh` → exit 0, no output

**Steps:**

- [ ] **Step 1: Create `macros.yaml`**

```yaml
- TARBALL_SSL_VARIANT: ssl3
- TARBALL_PYTHON_PKG: python3.12
```

(`TARBALL_PYTHON_PKG` exists because Rocky 10 has no `python3.12` package name — its default `python3` *is* 3.12. ssl1.1/ssl3 use `python3.12`; ssl3.5 uses `python3`.)

- [ ] **Step 2: Verify RPM package names against the published staging repo**

```bash
dnf repoquery --repofrompath=ppg,https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/17/RockyLinux_9/ \
  --disablerepo='*' --enablerepo=ppg --queryformat '%{name}\n' 'percona-*' 'etcd*' 'python3*' | sort -u
```

Expected: the names listed in "Reference facts" appear. Note the exact `percona-pg-telemetry*` and `etcd` names. If any `BuildRequires` name in Step 3 differs from repoquery output, fix the recipe to match reality (reality wins). If the URL 404s (staging not published), fall back to `venv/bin/osc -A https://api.opensuse.org ls -b isv:percona:ppg:staging:17` and grep the binary list.

- [ ] **Step 3: Create `obs/simpleimage`**

```
#!NoTarBall
#!NoSquashfs
Name:           percona-postgresql
Version:        %!{PG_VERSION}-%!{TARBALL_SSL_VARIANT}-linux

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
BuildRequires:  percona-pg_cron_%!{PG_MAJOR_VERSION}
BuildRequires:  percona-wal2json%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pgvector_%!{PG_MAJOR_VERSION}
BuildRequires:  percona-postgis35_%!{PG_MAJOR_VERSION}
BuildRequires:  percona-pg-telemetry%!{PG_MAJOR_VERSION}
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
# Language runtimes
BuildRequires:  %!{TARBALL_PYTHON_PKG}
BuildRequires:  %!{TARBALL_PYTHON_PKG}-pip
BuildRequires:  %!{TARBALL_PYTHON_PKG}-devel
BuildRequires:  %!{TARBALL_PYTHON_PKG}-idle
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

Adjust names per Step 2 findings (e.g. `percona-pg-telemetry17` vs `percona-pg-telemetry_17`).

- [ ] **Step 4: Create `obs/build-tarball.sh` from the POC**

Copy the `%build` body of `~/Downloads/simpleimage` (everything after the `%build` line) into `obs/build-tarball.sh`, then apply ALL of the following modifications. The POC logic (component staging sections 1–14, `SYSTEM_LIBS_EXCLUDE`, `is_system_lib`, `copy_deps`, `bundle_deps`, `patch_rpath`, wrappers) is kept verbatim except where listed.

**4a. New header — replace the POC's hardcoded version block** (`PG_MAJOR=17`, `PY_VER=3.12`, `PY_BIN=…`) with:

```bash
#!/bin/bash
# Builds the Percona PostgreSQL binary tarball from RPM-installed content.
# Runs chrooted as root inside an OBS simpleimage buildroot; writes the
# final artifact to /.simpleimage.tar.gz (picked up via #!NoTarBall).
set -e

PG_MAJOR=$(basename "$(ls -d /usr/pgsql-*)" | sed 's/^pgsql-//')
[ -n "$PG_MAJOR" ] || { echo "FATAL: no /usr/pgsql-* tree found" >&2; exit 1; }

# Prefer the parallel 3.12 stack (EL8/EL9); fall back to the default python3 (EL10+).
PY_BIN=$(command -v python3.12 || command -v python3)
PY_VER=$("$PY_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')

PG_PREFIX=/opt/percona-postgresql${PG_MAJOR}
PYTHON_PREFIX=/opt/percona-python3
PERL_PREFIX=/opt/percona-perl
TCL_PREFIX=/opt/percona-tcl
```

**4b. Fix hardcoded interpreter versions in POC heredocs/loops:**

- Section 2c `postgres` wrapper: the POC hardcodes `/opt/percona-perl/lib/5.32.1`. Generate the wrapper with the discovered perl version instead — move the `PERL_VER=$(perl -e 'printf "%vd", $^V')` line from section 10 up to the header (after `PY_VER`), and write the wrapper with an **unquoted** heredoc, escaping the runtime-expanded variables:

```bash
mv $PG_PREFIX/bin/postgres $PG_PREFIX/bin/postgres.real
cat > $PG_PREFIX/bin/postgres << EOF
#!/bin/sh
# Set bundled PL/Perl stdlib path (libperl.so @INC points to system paths by default)
export PERL5LIB="\${PERL5LIB:+\${PERL5LIB}:}/opt/percona-perl/lib/${PERL_VER}"
# Set bundled Tcl library path so pltcl can find init.tcl
export TCL_LIBRARY="/opt/percona-tcl/lib/tcl\${TCL_LIBRARY_VER:-8.6}"
SELFDIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$SELFDIR/postgres.real" "\$@"
EOF
chmod +x $PG_PREFIX/bin/postgres
```

  Likewise move `TCL_VER=$(echo 'puts $tcl_version' | tclsh)` to the header and replace the literal `tcl8.6` in the wrapper above with `tcl${TCL_VER}`.
- Section 7: replace every literal `3.12` / `python3.12` with `${PY_VER}` / `python${PY_VER}` (the POC already does this in most places; sweep the stragglers: `pip3.12`, `2to3-3.12`, `pydoc3.12`, `idle3.12`, the `$PYTHON_PREFIX/bin/python3` wrapper's `exec` line, and the copy of `$PY_BIN`).
- Section 12 Python wrapper: `exec "$SELFDIR/python3.12"` → `exec "$SELFDIR/python${PY_VER}"` (unquoted heredoc, escape the `$SELFDIR`/`$PREFIX`/`$LD_LIBRARY_PATH` occurrences).

**4c. Append the verification gate — new section between POC section 14 (RPATH fixes) and the final tar:**

```bash
###############################################################
# 15. Verification gate — fail the build on any breakage
###############################################################
echo "=== Verification: ldd audit ==="
UNRESOLVED=0
find /opt -type f \( -perm -u+x -o -name '*.so*' \) | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    ldd "$f" 2>/dev/null | grep 'not found' | while read -r line; do
        lib=$(echo "$line" | awk '{print $1}')
        if ! is_system_lib "$lib"; then
            echo "UNRESOLVED: $f -> $line"
        fi
    done
done > /tmp/ldd-audit.txt
if [ -s /tmp/ldd-audit.txt ]; then
    cat /tmp/ldd-audit.txt
    UNRESOLVED=$(wc -l < /tmp/ldd-audit.txt)
fi
[ "$UNRESOLVED" -eq 0 ] || { echo "FATAL: $UNRESOLVED unresolved libraries" >&2; exit 1; }

echo "=== Verification: smoke commands ==="
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/initdb" --version
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/postgres.real" --version
"$PYTHON_PREFIX/bin/python3" -c 'import ssl, yaml; print("python OK")'
"$PYTHON_PREFIX/bin/python3" -c 'import patroni; print("patroni import OK")'
"$PERL_PREFIX/bin/perl" -e 'print "perl OK\n"'
"$TCL_PREFIX/bin/tclsh" <<< 'puts "tcl OK"'
```

Note: `patronictl version` needs a full runtime env; the import check is the build-time gate — the full CLI check happens in the Task 6 acceptance test.

**4d. Keep the POC's final tar step verbatim** (section "14. Create tarball of /opt only"):

```bash
cd /opt
tar -czf /.simpleimage.tar.gz *
```

**4e. Shellcheck pass:** run `shellcheck --severity=error` and fix every error (typical: unquoted `$PG_PREFIX` in `find` args — quote them; `local` outside function — none expected). Warnings (`--severity=warning`) may remain; do not restructure working POC logic to silence style-level findings.

- [ ] **Step 5: Create `project.yaml`**

```yaml
title: Percona PostgreSQL %!{PG_MAJOR_VERSION} Tarballs (%!{TARBALL_SSL_VARIANT})
description: |
  Binary tarball (simpleimage) builds for Percona Software for PostgreSQL
  %!{PG_MAJOR_VERSION}, %!{TARBALL_SSL_VARIANT} variant. The tarball repackages
  the ppg:staging:%!{PG_MAJOR_VERSION} RPMs into the official per-component
  layout for air-gapped / unsupported-distro installs.

repositories:
  - name: RockyLinux_9
    paths:
      - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
        repository: RockyLinux_9
      - subproject: ppg:common:deps
        repository: RockyLinux_9
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:9
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:9
        repository: standard
    archs: [x86_64]

publish:
  RockyLinux_9: true

project-config: |
  Type: simpleimage
  # Same choice-resolution as staging RockyLinux_9 (hdf-libs vs hdf both
  # provide libdf.so.0 — pulled in via the PostGIS/gdal dependency chain).
  Prefer: hdf-libs
```

- [ ] **Step 6: Commit**

```bash
git add root/ppg/staging/17/tarballs/ssl3/
git commit -s -m "staging:17/tarballs: add ssl3 simpleimage tarball subproject"
```

---

### Task 2: Local container validation of build-tarball.sh

**Goal:** Prove `build-tarball.sh` produces a correct tarball in a Rocky 9 container with the staging RPMs installed, before touching OBS. Iterate on the script until it passes.

**Files:**
- Modify (as needed during iteration): `root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/build-tarball.sh`
- Create: `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/*/scratchpad/tarball-test/run-local.sh` (throwaway harness, NOT committed)

**Acceptance Criteria:**
- [ ] Script runs to completion inside `rockylinux:9` with all `BuildRequires` packages installed
- [ ] `/.simpleimage.tar.gz` produced; top-level entries are exactly the `percona-*` component dirs
- [ ] Verification gate (section 15) passes: 0 unresolved libs, all smoke commands OK
- [ ] Tarball top-2-level structure-diff vs official `percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz` shows no missing component dirs and no missing `bin/lib/share/include` subdirs (content-level diffs reviewed and either fixed or explicitly accepted)

**Verify:** `podman run … bash /work/build-tarball.sh && tar -tzf .simpleimage.tar.gz | awk -F/ '{print $1}' | sort -u` → the component dir list

**Steps:**

- [ ] **Step 1: Write the throwaway harness `run-local.sh` in the scratchpad**

```bash
#!/bin/bash
# Local build-tarball.sh test harness — mimics the OBS simpleimage chroot.
set -ex
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REPO_URL="https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/17/RockyLinux_9/"
PKGS="percona-postgresql17 percona-postgresql17-server percona-postgresql17-contrib
percona-postgresql17-libs percona-postgresql17-plpython3 percona-postgresql17-plperl
percona-postgresql17-pltcl percona-postgresql17-devel percona-pg_tde17 percona-pgaudit17
percona-pgaudit17_set_user percona-pg_stat_monitor17 percona-pg_repack17 percona-pg_cron_17
percona-wal2json17 percona-pgvector_17 percona-postgis35_17 percona-pg-telemetry17
percona-pg_gather percona-pgbouncer percona-pgpool-II-pg17 percona-pgbackrest
percona-pgbadger percona-patroni percona-patroni-aws etcd python3-pysyncobj
python3.12 python3.12-pip python3.12-devel python3.12-idle
perl perl-libs perl-devel tcl tcl-devel patchelf file"

podman run --rm -v "$SCRIPT_DIR/build-tarball.sh:/work/build-tarball.sh:ro,Z" \
    -v "$SCRIPT_DIR/out:/out:Z" rockylinux:9 bash -ec "
  dnf -y install epel-release
  dnf -y --nogpgcheck --repofrompath=ppg,$REPO_URL install \$(echo '$PKGS')
  bash /work/build-tarball.sh
  cp /.simpleimage.tar.gz /out/
"
```

(Copy `build-tarball.sh` from the package dir next to it; `mkdir -p out`. Package list mirrors the `simpleimage` `BuildRequires` — keep them in sync when Task 1 Step 2 findings rename anything.)

- [ ] **Step 2: Run, iterate until green**

Run: `bash run-local.sh`
Expected: dnf resolves all packages; script completes; verification gate prints `python OK`, `patroni import OK`, `perl OK`, `tcl OK`; `out/.simpleimage.tar.gz` exists.

Failures here are the point of this task — fix `build-tarball.sh` (in the package dir, then re-copy) until green. Typical issues: renamed RPMs (fix `simpleimage` + `PKGS` together), paths that differ between the POC's build env and Rocky 9, missing `libssh` runtime lib for pgbackrest (add `BuildRequires: libssh` back if `ldd` audit flags it — the POC carried it).

- [ ] **Step 3: Structure-diff against the official tarball**

```bash
curl -fLO https://downloads.percona.com/downloads/postgresql-distribution-17/17.10/binary/tarball/percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz
tar -tzf percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz | awk -F/ 'NF>1 {print $2"/"$3}' | sort -u > official.lst
tar -tzf out/.simpleimage.tar.gz | awk -F/ 'NF>1 {print $1"/"$2}' | sort -u > ours.lst
diff official.lst ours.lst
```

Expected: component dirs match (haproxy missing is accepted per spec non-goals). Review any other diffs: fix real gaps in `build-tarball.sh`; record accepted divergences in the commit message.

- [ ] **Step 4: Commit the script fixes**

```bash
git add root/ppg/staging/17/tarballs/ssl3/percona-postgresql-tarball/obs/
git commit -s -m "staging:17/tarballs: validate build-tarball.sh in local Rocky 9 container"
```

---

### Task 3: Replicate to ssl1.1 and ssl3.5 + copy-identity test

**Goal:** Create the ssl1.1 (Rocky 8) and ssl3.5 (Rocky 10) variant subprojects as byte-identical package copies with variant-specific `macros.yaml`/`project.yaml`, plus a pytest guarding the copies against divergence.

**Files:**
- Create: `root/ppg/staging/17/tarballs/ssl1.1/{project.yaml,macros.yaml}`
- Create: `root/ppg/staging/17/tarballs/ssl1.1/percona-postgresql-tarball/obs/{simpleimage,build-tarball.sh}` (copies)
- Create: `root/ppg/staging/17/tarballs/ssl3.5/{project.yaml,macros.yaml}`
- Create: `root/ppg/staging/17/tarballs/ssl3.5/percona-postgresql-tarball/obs/{simpleimage,build-tarball.sh}` (copies)
- Test: `tests/test_tarball_variants.py`

**Acceptance Criteria:**
- [ ] `simpleimage` and `build-tarball.sh` byte-identical across the three variant dirs (enforced by pytest)
- [ ] ssl1.1 repo chain = staging RockyLinux_8 chain (EPEL 8 + appstream/baseos/devel); ssl3.5 = RockyLinux_10 chain (EPEL 10 + standard); archs `[x86_64]`; publish enabled
- [ ] ssl3.5 `macros.yaml` sets `TARBALL_PYTHON_PKG: python3` (Rocky 10 has no `python3.12` name)
- [ ] `venv/bin/black percona_obs/` and `venv/bin/pyright` pass; `venv/bin/pytest tests/test_tarball_variants.py -v` passes

**Verify:** `venv/bin/pytest tests/test_tarball_variants.py -v` → 1 passed (parametrized over both files)

**Steps:**

- [ ] **Step 1: Copy the package dir and write variant `macros.yaml`**

```bash
cd root/ppg/staging/17/tarballs
for v in ssl1.1 ssl3.5; do mkdir -p $v; cp -r ssl3/percona-postgresql-tarball $v/; done
printf -- '- TARBALL_SSL_VARIANT: ssl1.1\n- TARBALL_PYTHON_PKG: python3.12\n' > ssl1.1/macros.yaml
printf -- '- TARBALL_SSL_VARIANT: ssl3.5\n- TARBALL_PYTHON_PKG: python3\n' > ssl3.5/macros.yaml
```

- [ ] **Step 2: Write `ssl1.1/project.yaml`**

Same file as ssl3's `project.yaml` with these replacements — repo name `RockyLinux_8`, and paths/prjconf per staging's RockyLinux_8 block:

```yaml
repositories:
  - name: RockyLinux_8
    paths:
      - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
        repository: RockyLinux_8
      - subproject: ppg:common:deps
        repository: RockyLinux_8
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:8
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: appstream
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: baseos
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: devel
    archs: [x86_64]

publish:
  RockyLinux_8: true

project-config: |
  Type: simpleimage
  # Same install-time resolution hints as staging RockyLinux_8.
  ExpandFlags: module:llvm-toolset-rhel8
  ExpandFlags: module:perl-5.26
  ExpandFlags: module:perl-IO-Socket-SSL-2.066
  ExpandFlags: module:perl-libwww-perl-6.34
  Prefer: python3-devel
  Prefer: selinux-policy-targeted
```

(title/description lines identical to ssl3's — the `%!{TARBALL_SSL_VARIANT}` macro renders the variant name.)

- [ ] **Step 3: Write `ssl3.5/project.yaml`**

```yaml
repositories:
  - name: RockyLinux_10
    paths:
      - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
        repository: RockyLinux_10
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:10
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:10
        repository: standard
    archs: [x86_64]

publish:
  RockyLinux_10: true

project-config: |
  Type: simpleimage
  # Same install-time resolution hints as staging RockyLinux_10.
  Prefer: selinux-policy-targeted
  Prefer: hdf-libs
```

(No `ppg:common:deps` path — staging's RockyLinux_10 repo does not chain it either.)

Also confirm the variant name is honest — Rocky 10 must actually ship OpenSSL 3.5:

```bash
dnf repoquery --repofrompath=r10,https://download.rockylinux.org/pub/rocky/10/BaseOS/x86_64/os/ \
  --disablerepo='*' --enablerepo=r10 --queryformat '%{name}-%{version}\n' openssl-libs
```

Expected: `openssl-libs-3.5.*`. If it reports a different major (e.g. 3.2), STOP and ask the user whether to rename the variant (the subproject dir, `TARBALL_SSL_VARIANT`, and docs all carry the name).

- [ ] **Step 4: Write the copy-identity test `tests/test_tarball_variants.py`**

```python
"""The tarball package files must stay byte-identical across SSL variants.

Variant identity lives exclusively in each subproject's macros.yaml and
project.yaml; simpleimage and build-tarball.sh are deliberate copies."""

from pathlib import Path

import pytest

TARBALLS_ROOT = Path(__file__).parent.parent / "root" / "ppg" / "staging" / "17" / "tarballs"
VARIANTS = ["ssl1.1", "ssl3", "ssl3.5"]
PACKAGE = "percona-postgresql-tarball"


@pytest.mark.parametrize("filename", ["simpleimage", "build-tarball.sh"])
def test_variant_copies_identical(filename: str) -> None:
    contents = {
        variant: (TARBALLS_ROOT / variant / PACKAGE / "obs" / filename).read_bytes()
        for variant in VARIANTS
    }
    reference = contents["ssl3"]
    for variant, data in contents.items():
        assert data == reference, (
            f"{filename} in {variant} diverges from ssl3 — "
            "variant differences belong in macros.yaml/project.yaml"
        )
```

- [ ] **Step 5: Run test + repo tooling checks**

Run: `venv/bin/pytest tests/test_tarball_variants.py -v`
Expected: 2 passed
Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: "left unchanged" / 0 errors

- [ ] **Step 6: Commit**

```bash
git add root/ppg/staging/17/tarballs/ tests/test_tarball_variants.py
git commit -s -m "staging:17/tarballs: add ssl1.1 and ssl3.5 variants + copy-identity test"
```

---

### Task 4: Sync tooling dry-run verification

**Goal:** Confirm `percona-obs` resolves and syncs the new tarball subprojects without code changes (spec: "tooling impact: none expected" — verify, don't assume).

**Files:**
- None expected; modify `percona_obs/*.py` only if the dry-run exposes a container-specific assumption.

**Acceptance Criteria:**
- [ ] `sync push --dry-run` for each variant project resolves the target, expands macros, and reports the files it would upload (`simpleimage`, `build-tarball.sh`) and the project meta/prjconf it would create — no tracebacks
- [ ] Dry-run output shows `Type: simpleimage` in the prjconf and the expanded `Version: 17.10-<variant>-linux` in `simpleimage`

**Verify:** `venv/bin/python -m percona_obs -P isv sync push --dry-run ppg:staging:17:tarballs:ssl3 percona-postgresql-tarball` → dry-run report, exit 0

**Steps:**

- [ ] **Step 1: Dry-run each variant against production (read-only — NEVER without --dry-run on -P isv)**

```bash
for v in ssl1.1 ssl3 ssl3.5; do
  venv/bin/python -m percona_obs -P isv sync push --dry-run "ppg:staging:17:tarballs:$v" percona-postgresql-tarball
done
```

Expected: each run lists the new project (meta + prjconf with `Type: simpleimage`) and the two package files as would-be uploads. If target resolution fails (e.g. something assumes `obs/Dockerfile` or a `_service`), read the failing code path in `percona_obs/targets.py` / `percona_obs/cmd_sync.py`, fix minimally, then rerun `venv/bin/black percona_obs/ && venv/bin/pyright` and the existing pytest suite (`venv/bin/pytest tests/ -x`).

- [ ] **Step 2: Commit (only if code fixes were needed)**

```bash
git add percona_obs/ tests/
git commit -s -m "percona-obs: handle simpleimage tarball packages in sync"
```

---

### Task 5: Document the tarballs subprojects

**Goal:** Record the tarballs layout and build model where the repo documents its structure.

**Files:**
- Modify: `root/README.md` (the "Product project layout" section that currently only name-drops `tarballs/`)

**Acceptance Criteria:**
- [ ] `root/README.md` explains: one subproject per SSL variant, base-distro mapping (ssl1.1→Rocky 8, ssl3→Rocky 9, ssl3.5→Rocky 10), byte-identical package files with variant `macros.yaml`, `#!NoTarBall` self-tar model, publish-enabled artifact location

**Verify:** `grep -A5 'tarballs' root/README.md` → shows the new subsection

**Steps:**

- [ ] **Step 1: Add a `### tarballs/` subsection under the staging layout docs in `root/README.md`**

```markdown
### `staging/<V>/tarballs/`

Binary-tarball builds (OBS `simpleimage` format) for air-gapped / unsupported-distro
installs, replicating the official Percona tarball layout. One subproject per SSL
variant, each building against a different EL base of `ppg:staging:<V>`:

| Subproject | Base repo | Host ABI targeted |
|---|---|---|
| `tarballs/ssl1.1` | RockyLinux_8 | glibc ≥ 2.28, OpenSSL 1.1 |
| `tarballs/ssl3` | RockyLinux_9 | glibc ≥ 2.34, OpenSSL 3.x |
| `tarballs/ssl3.5` | RockyLinux_10 | glibc ≥ 2.39, OpenSSL 3.5 |

The `percona-postgresql-tarball` package files (`simpleimage`, `build-tarball.sh`)
are byte-identical across variants (enforced by `tests/test_tarball_variants.py`);
variant identity comes from each subproject's `macros.yaml` (`TARBALL_SSL_VARIANT`,
`TARBALL_PYTHON_PKG`) and repository paths. The `%build` script stages all components
under `/opt/percona-*` and creates the artifact itself (`#!NoTarBall`), so the tarball
contains only the official per-component tree. Repositories publish their results, so
the `.tar.gz` is downloadable from the OBS publish tree.
```

- [ ] **Step 2: Commit**

```bash
git add root/README.md
git commit -s -m "docs: document staging tarballs subprojects in root/README.md"
```

---

### Task 6: PR build in production OBS + acceptance test

**Goal:** Prove the end-to-end deliverable: obs-pr-sync builds all three variants in a production PR project, and the ssl3 artifact passes the acceptance test on a foreign distro.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- None (operational task; fixes loop back into Tasks 1–3 files if builds fail)

**Acceptance Criteria:**
- [ ] User has opened the PR (manual step — do NOT `git push` or `gh pr create` without the user's explicit go-ahead)
- [ ] obs-pr-sync created the PR project including all three `tarballs:ssl*` subprojects; `build status` shows `succeeded` for `percona-postgresql-tarball` in all three
- [ ] Artifact downloaded from the PR project (`osc getbinaries` or the publish tree)
- [ ] Acceptance on `ubuntu:24.04` container (ssl3 artifact): untar to `/opt/pgdistro`, copy `percona-{python3,perl,tcl}` to `/opt`, then as non-root: `initdb` succeeds, `pg_ctl start` succeeds, `psql -c 'SELECT version()'` returns the Percona version string, `psql -c "CREATE EXTENSION pg_tde"` succeeds, `percona-patroni/bin/patronictl version` prints a version
- [ ] Structure-diff vs official 17.10 ssl3 tarball reviewed; divergences accepted explicitly or fixed

**Verify:** `venv/bin/python -m percona_obs -A https://api.opensuse.org -R isv:percona:PR:pr-<N> build status ppg:staging:17:tarballs:ssl3` → `succeeded`, then the containerized acceptance commands above, each with captured output

**Steps:**

- [ ] **Step 1: Ask the user to open the PR** (branch with Tasks 1–5 commits). Wait — do not push or create it yourself.

- [ ] **Step 2: Watch the PR project build**

```bash
venv/bin/python -m percona_obs -A https://api.opensuse.org -R isv:percona:PR:pr-<N> build status ppg:staging:17:tarballs:ssl3
```

Expected: `succeeded` for all three variants (repeat per variant). On failure, fetch the log:

```bash
venv/bin/osc -A https://api.opensuse.org buildlog isv:percona:PR:pr-<N>:ppg:staging:17:tarballs:ssl3 percona-postgresql-tarball RockyLinux_9 x86_64
```

Fix in the package files (Tasks 1–3 layout), commit; the PR re-sync rebuilds.

- [ ] **Step 3: Download the ssl3 artifact**

```bash
venv/bin/osc -A https://api.opensuse.org getbinaries isv:percona:PR:pr-<N>:ppg:staging:17:tarballs:ssl3 percona-postgresql-tarball RockyLinux_9 x86_64
```

Expected: `percona-postgresql-17.10-ssl3-linux_x86_64.tar.gz` in `binaries/`. Note the actual publish-tree URL for the spec's open question.

- [ ] **Step 4: Acceptance test on ubuntu:24.04**

```bash
podman run --rm -v ./binaries:/dist:Z ubuntu:24.04 bash -ec '
  apt-get update -qq && apt-get install -y -qq libreadline8 >/dev/null
  useradd -m postgres
  mkdir -p /opt/pgdistro && tar -xzf /dist/percona-postgresql-*-ssl3-linux_x86_64.tar.gz -C /opt/pgdistro
  cp -r /opt/pgdistro/percona-python3 /opt/pgdistro/percona-perl /opt/pgdistro/percona-tcl /opt/
  chown -R postgres /opt/pgdistro
  su postgres -c "
    export PATH=/opt/pgdistro/percona-postgresql17/bin:\$PATH
    initdb -D /tmp/data
    pg_ctl -D /tmp/data -l /tmp/log start
    psql -c \"SELECT version()\"
    psql -c \"CREATE EXTENSION pg_tde\"
    /opt/pgdistro/percona-patroni/bin/patronictl version
  "
'
```

Expected: every command succeeds; `SELECT version()` shows the Percona PostgreSQL 17.10 build. Capture the full output as gate evidence.

- [ ] **Step 5: Structure-diff vs official** (same commands as Task 2 Step 3, against the PR artifact). Review; fix or explicitly accept each divergence.

- [ ] **Step 6: Report results to the user** — build status per variant, acceptance output, structure-diff summary. The user merges the PR; do not merge it yourself.

---

## Execution notes

- Tasks 1→2 are strictly sequential (script must exist before local validation). Task 3 depends on 2 (copies replicate the *validated* script). Tasks 4 and 5 depend on 3. Task 6 is last and user-gated.
- Standing rules: `git commit -s`, no Claude attribution anywhere, never `git push`/`gh pr create` without asking, `-P isv` writes only with `--dry-run`.
- After any `percona_obs/` code change: `venv/bin/black percona_obs/` then `venv/bin/pyright`, both must pass.
