# PostGIS GIS Library Stack (mirror PGDG) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build PGDG's GIS library set (geos315, proj98/proj96, libgeotiff17,
librttopo, libspatialite50, gdal313/gdal38, SFCGAL 2.3) in `ppg:common:deps`,
link `percona-postgis` 3.5 (PG 14–18) and 3.7 (PG 19) against it on every RPM
distro, and publish the libraries into every `ppg:staging:<ver>`.

**Architecture:** Port PGDG's specs (pgdg-rpms at a pinned commit) into
`root/ppg/common/deps/<pkg>/`. Replace PGDG's `pgdg-srpm-macros` and
`ld.so.conf.d` mechanisms with explicit `%global` blocks driven by
`root/macros.yaml` (`GIS_*`) and with RUNPATH. Switch both PostGIS specs to
one PGDG-style selection block, add `_aggregate` packages in
`root/ppg/staging/_shared/`, and re-target the tarball-only `/opt` GDAL/PROJ.
Debian/Ubuntu are untouched: they keep the distro libraries.

**Tech Stack:** RPM spec files, OBS `_service` (`download_url`) and
`_aggregate`, `package.yaml` build flags, `%!{}` macros rendered by
`percona-obs`, Debian 3.0 (quilt) patches, Ansible (ppg-testing).

**Spec:** `docs/superpowers/specs/2026-10-16-postgis-gis-stack-pgdg-mirror-design.md`

## Global Constraints

- **Work location:** git worktree `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/postgis-gis-stack`
  (branch `postgis-gis-stack`, tracking `percona/main`). Each later PR
  (B, C, D) gets a new branch and worktree off `percona/main` *after* the
  previous PR merges: `git -C /home/rdias/Work/percona-obs-packaging worktree add -b <branch> .claude/worktrees/<branch> percona/main`.
  Never edit the primary checkout.
- **venv:** each worktree uses the main checkout's venv:
  `ln -sfn /home/rdias/Work/percona-obs-packaging/venv venv` (run once in the
  worktree root, and never commit the link: `git status` must not show `venv`).
- **Scratch tooling:** every command below assumes
  `S=/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port`
  is exported (Task 1 creates the scripts there) and is run from the worktree root.
- **Commits:** `git commit -s`. No `Co-Authored-By` lines and no Claude
  attribution in commits or PR bodies. This overrides any harness reminder.
- **Push / PR / external writes:** NEVER `git push`, `gh pr create`, post to
  Jira, or trigger Jenkins without asking the user first and getting a yes in
  chat. Never add the `obs-sync` label. PR branches go to the `percona`
  remote (fork PRs get no OBS sync jobs).
- **OBS access:** `-P isv` is PRODUCTION. Only read-only commands
  (`build status`, `osc ls`, `osc api` GET, `project install`, `--dry-run`).
  Never `sync push` by hand; OBS sync happens through PR CI.
- **Upstream reference:** PGDG pgdg-rpms commit
  `e38918e895bcd74d083b33ccb440f3afd21a5c97`. Port from
  `rpm/redhat/main/common/<pkg>/main/`, and fold in the per-distro differences
  of `EL-8/`, `EL-9/`, `EL-10/` and `SLES-16/`. Some variant files are
  one-line symlinks to `../main/...`; treat those as identical to main.
- **Versions (bind exactly):**

  | Macro | Value | Used for |
  |---|---|---|
  | `GIS_GEOS_VERSION` / `GIS_GEOS_MAJOR` | `3.15.0` / `315` | geos315, all RPM distros |
  | `GIS_PROJ_VERSION` / `GIS_PROJ_MAJOR` | `9.8.1` / `98` | proj98, every RPM distro except EL8 |
  | `GIS_PROJ_EL8_VERSION` / `GIS_PROJ_EL8_MAJOR` | `9.6.2` / `96` | proj96, EL8/UBI8 only |
  | `GIS_GDAL_VERSION` / `GIS_GDAL_MAJOR` | `3.13.3` / `313` | gdal313, every RPM distro except EL8 |
  | `GIS_GDAL_EL8_VERSION` / `GIS_GDAL_EL8_MAJOR` | `3.8.5` / `38` | gdal38, EL8/UBI8 only |
  | `GIS_LIBGEOTIFF_VERSION` | `1.7.4` | libgeotiff17 |
  | `GIS_LIBSPATIALITE_VERSION` | `5.1.0` | libspatialite50 |
  | `GIS_LIBRTTOPO_VERSION` | `1.1.0` | librttopo, EL8/UBI8 only |
  | `GIS_SFCGAL_VERSION` | `2.3.0` | existing `sfcgal` package (already 2.3.0) |

- **Layout:** prefixes `/usr/<pkgname>` exactly as PGDG uses them
  (`/usr/geos315` with `lib64`, `/usr/proj98` with `lib64`,
  `/usr/libgeotiff17/lib`, `/usr/libspatialite50/lib`, `/usr/gdal313/lib`).
  PGDG's `-pgdg-libs.conf` sources and `/etc/ld.so.conf.d` installs are
  **removed**. Every ELF file under a prefix must carry a RUNPATH that covers
  its own lib dir and those of its GIS dependencies (enforced by the RUNPATH
  check in each spec's `%install`).
- **Pins:** PostGIS uses `BuildRequires: <name><MAJOR>-devel >= <full version>`
  and `Requires: <name><MAJOR>[-libs] >= <full version>`. Because the minor line
  is part of the package name (`geos315` can only be 3.15.x), this meets the
  spec's "`>= X.Y.0` and `< X.(Y+1)`" rule. SFCGAL has an unversioned name, so
  it gets an explicit `< 2.4`.
- **Repos:** the new common:deps packages are disabled on `Debian_12`,
  `Debian_13`, `Ubuntu_22.04`, `Ubuntu_24.04` and `Ubuntu_26.04`. EL8-only
  packages (`proj96`, `gdal38`, `librttopo`) are additionally disabled on every
  repo except `RockyLinux_8` and `UBI_8`. `proj98` and `gdal313` are disabled
  on `RockyLinux_8` and `UBI_8`.
- **Spec metadata:** `Release: 1%{?dist}`, plus `Vendor: Percona LLC` and
  `Packager: Percona LLC` (as in `root/ppg/common/deps/sfcgal/rpm/sfcgal.spec`).
  Keep PGDG's `%changelog` history and add a top entry
  `* <LC_ALL=C date -u '+%a %b %d %Y'> Percona Development <info@percona.com> - <version>-1`
  with `- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead`.
- **RPM patch syntax:** `%patch -P <N> -p1` (repo convention; never `%patchN`).

**User decisions (already made):**
- Mirror PGDG: geos315 serves both PostGIS 3.5 and 3.7. postgis35 carries PGDG's `postgis35-3.5.7-geos315-backport.patch` until 3.5.8.
- EL8 follows PGDG: gdal38 + proj96. Everything else: gdal313 + proj98. SFCGAL 2.3 everywhere.
- GDAL has full PGDG parity, including the Python 3.12 and Java bindings on EL9+.
- PGDG package names and `/usr/<name>` prefixes. No `/etc/ld.so.conf.d` drop-ins; RPATH only.
- Pin the minor line; a version bump is a deliberate edit.
- Always build our own on RPM distros (no skip-if-distro-matches).
- Debian/Ubuntu keep the distro libraries. Debian 11 is dropped for upcoming releases.
- Runtime libraries are aggregated from `ppg:common:deps` into every `ppg:staging:<ver>`.
- Tarballs keep their `/opt` `percona-gdal`/`percona-proj` with the minimal driver set (not full parity) and switch to GDAL's bundled libgeotiff.
- The SFCGAL test fixes go into ppg-testing, not the package.
- The steps are separate PRs, each verified on OBS before the next one starts.

---

## File Structure

| Path | Change | Responsibility |
|---|---|---|
| `root/macros.yaml` | modify | Single source of the GIS versions (`GIS_*`) |
| `root/ppg/common/deps/geos315/{package.yaml,obs/_service,rpm/geos315.spec}` | create | GEOS 3.15 |
| `root/ppg/common/deps/proj98/…`, `root/ppg/common/deps/proj96/…` | create | PROJ 9.8 (non-EL8), PROJ 9.6 (EL8) |
| `root/ppg/common/deps/libgeotiff17/…` (+ 2 patches) | create | libgeotiff on our PROJ |
| `root/ppg/common/deps/librttopo/…` | create | EL8 only (EPEL 8 lacks it) |
| `root/ppg/common/deps/libspatialite50/…` | create | SpatiaLite on geos315 + PROJ |
| `root/ppg/common/deps/gdal38/…` (+ patches, cleaner, provenance) | create | GDAL 3.8, EL8 |
| `root/ppg/common/deps/gdal313/…` (+ patch, cleaner, provenance) | create | GDAL 3.13, the others, full parity |
| `root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec` | modify | 3.5: selection block, deps, RUNPATH, Patch0 |
| `root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch` | create | PGDG backport (RPM) |
| `root/ppg/staging/_shared/percona-postgis/debian/patches/{series,geos315-backport}` | create | Same backport (deb, inert there) |
| `root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec` | modify | 3.7: selection block, deps, RUNPATH |
| `root/ppg/staging/_shared/<pkg>/{package.yaml,obs/_aggregate}` + `root/ppg/staging/{14..19}/<pkg>` symlinks | create | Publish the libraries in staging |
| `root/ppg/staging/_shared/{geos,proj}` + their symlinks, `root/ppg/common/deps/{geos,proj}` | delete | Retired unversioned packages |
| `root/ppg/common/deps/tarballs/percona-proj/…` | modify | 9.6.2 (EL8) / 9.8.1 (EL9 bases) |
| `root/ppg/common/deps/tarballs/percona-gdal/…` | modify | 3.8.5 / 3.13.3, CMake, minimal drivers, bundled geotiff |
| `root/ppg/common/deps/tarballs/percona-gis-compat/rpm/percona-gis-compat.spec` | modify | Provides the new by-name Requires |
| `root/ppg/staging/_shared/tarballs/project.yaml` | modify (comments) | Keep the rationale accurate |
| `Percona-QA/ppg-testing: postgis/setup/tasks/main.yml` | modify (QA repo) | Derived -devel list, 3.5.7 regress patches |

---

### Task 1: GIS version macros and port tooling

**Goal:** Define the `GIS_*` macros in `root/macros.yaml` and create the scratch
helper scripts that every later task uses (fetch PGDG files, render a spec,
parse it with rpmspec for each distro).

**Files:**
- Modify: `root/macros.yaml` (after the `POSTGIS_RPM_MAJOR` entry)
- Create (scratch, not committed): `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port/{pgdg-fetch.sh,render-spec.py,parse-spec.sh}`

**Acceptance Criteria:**
- [ ] `root/macros.yaml` contains every `GIS_*` macro from the Global Constraints table with the exact values
- [ ] `render-spec.py` prints a spec with no `%!{` left for `root/ppg/common/deps/sfcgal/rpm/sfcgal.spec`
- [ ] `parse-spec.sh` exits 0 for the rendered sfcgal spec on el8, el9, el10 and suse1600
- [ ] `venv/bin/python -m percona_obs project verify --offline` passes

**Verify:** `S=/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port; $S/parse-spec.sh root/ppg/common/deps/sfcgal root/ppg/common/deps/sfcgal/rpm/sfcgal.spec` → `OK el8 OK el9 OK el10 OK suse1600`

**Steps:**

- [ ] **Step 1: Add the macros** after the `- POSTGIS_RPM_MAJOR: 35` line in `root/macros.yaml`:

```yaml
# GIS library stack for PostGIS (mirrors PGDG, pgdg-rpms e38918e8). Package
# names carry the minor line (geos315, proj98, gdal313...), so a *_MAJOR bump
# means a new package directory under root/ppg/common/deps. EL8 follows
# PGDG's EL-8 choice (gdal38 + proj96).
- GIS_GEOS_VERSION: 3.15.0
- GIS_GEOS_MAJOR: 315
- GIS_PROJ_VERSION: 9.8.1
- GIS_PROJ_MAJOR: 98
- GIS_PROJ_EL8_VERSION: 9.6.2
- GIS_PROJ_EL8_MAJOR: 96
- GIS_GDAL_VERSION: 3.13.3
- GIS_GDAL_MAJOR: 313
- GIS_GDAL_EL8_VERSION: 3.8.5
- GIS_GDAL_EL8_MAJOR: 38
- GIS_LIBGEOTIFF_VERSION: 1.7.4
- GIS_LIBSPATIALITE_VERSION: 5.1.0
- GIS_LIBRTTOPO_VERSION: 1.1.0
- GIS_SFCGAL_VERSION: 2.3.0
```

- [ ] **Step 2: Create `pgdg-fetch.sh`.** It fetches a PGDG package directory at
the pinned commit, resolves one-line symlink files, and prints the diff of
each variant spec against `main`:

```bash
#!/bin/bash
# usage: pgdg-fetch.sh <pgdg-pkg> <outdir>
set -euo pipefail
SHA=e38918e895bcd74d083b33ccb440f3afd21a5c97
PKG=$1; OUT=$2; mkdir -p "$OUT"
RAW=https://raw.githubusercontent.com/pgdg-packaging/pgdg-rpms/$SHA/rpm/redhat/main/common/$PKG
for v in main EL-8 EL-9 EL-10 SLES-16; do
  names=$(gh api "repos/pgdg-packaging/pgdg-rpms/contents/rpm/redhat/main/common/$PKG/$v?ref=$SHA" -q '.[].name' 2>/dev/null) || continue
  mkdir -p "$OUT/$v"
  for n in $names; do
    curl -fsSL "$RAW/$v/$n" -o "$OUT/$v/$n"
    # one-line relative path == git symlink: resolve it
    if [ "$(wc -l < "$OUT/$v/$n")" -le 1 ] && grep -qE '^\.\./' "$OUT/$v/$n"; then
      tgt=$(cat "$OUT/$v/$n"); curl -fsSL "$RAW/$v/$tgt" -o "$OUT/$v/$n"
    fi
  done
done
for v in EL-8 EL-9 EL-10 SLES-16; do
  [ -d "$OUT/$v" ] || continue
  for f in "$OUT/$v"/*.spec; do
    echo "=== $v vs main: $(basename "$f")"; diff -u "$OUT/main/$(basename "$f")" "$f" || true
  done
done
```

- [ ] **Step 3: Create `render-spec.py`.** It renders `%!{}` macros the same
way `percona-obs` does:

```python
#!/usr/bin/env python3
"""usage: render-spec.py <project_dir> <spec> -> writes <spec basename> rendered into $OUTDIR (default /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port/rendered) and prints its path"""
import os, sys, pathlib
sys.path.insert(0, os.getcwd())  # run from the worktree root
from percona_obs.common import load_macros, apply_macro_substitution
proj = pathlib.Path(sys.argv[1]).resolve()
spec = pathlib.Path(sys.argv[2])
out_dir = pathlib.Path(os.environ.get("OUTDIR", "/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port/rendered"))
out_dir.mkdir(parents=True, exist_ok=True)
text = apply_macro_substitution(spec.read_text("utf-8"), load_macros(proj), source=spec)
assert "%!{" not in text, "unrendered macro left"
out = out_dir / spec.name
out.write_text(text, "utf-8")
print(out)
```

- [ ] **Step 4: Create `parse-spec.sh`** (run from the worktree root):

```bash
#!/bin/bash
# usage: parse-spec.sh <project_dir> <spec>   (project_dir = dir whose macros apply)
set -uo pipefail
S=$(dirname "$0")
R=$(venv/bin/python "$S/render-spec.py" "$1" "$2") || exit 1
rc=0
for d in 8 9 10; do
  if rpmspec -P --undefine fedora --define "rhel $d" --define "dist .el$d" --define "_arch x86_64" "$R" >/dev/null 2>"$S/err.el$d"; then echo -n "OK el$d "; else echo -n "FAIL el$d "; cat "$S/err.el$d"; rc=1; fi
done
if rpmspec -P --undefine fedora --undefine rhel --define "suse_version 1600" --define "_arch x86_64" "$R" >/dev/null 2>"$S/err.suse"; then echo "OK suse1600"; else echo "FAIL suse1600"; cat "$S/err.suse"; rc=1; fi
exit $rc
```

`chmod +x` all three scripts.

- [ ] **Step 5: Run the checks**

Run: `$S/parse-spec.sh root/ppg/common/deps/sfcgal root/ppg/common/deps/sfcgal/rpm/sfcgal.spec`
Expected: `OK el8 OK el9 OK el10 OK suse1600`

Run: `venv/bin/python -m percona_obs project verify --offline`
Expected: exit 0, with no error lines.

- [ ] **Step 6: Commit**

```bash
git add root/macros.yaml
git commit -s -m "macros: GIS library versions for the PGDG-mirrored PostGIS stack"
```

```json:metadata
{"files": ["root/macros.yaml"], "verifyCommand": "S=/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/1f8ff2cb-8d8a-45f9-ba64-be2a90a5158a/scratchpad/gis-port; $S/parse-spec.sh root/ppg/common/deps/sfcgal root/ppg/common/deps/sfcgal/rpm/sfcgal.spec", "acceptanceCriteria": ["GIS_* macros present with exact values", "render-spec.py leaves no %!{ in sfcgal.spec", "parse-spec.sh OK on el8/el9/el10/suse1600", "project verify --offline passes"], "modelTier": "standard"}
```

---

### Task 2: geos315 package

**Goal:** `root/ppg/common/deps/geos315` builds GEOS 3.15.0 into `/usr/geos315`
on every RPM repo, with RUNPATH and no ld.so.conf drop-in.

**Files:**
- Create: `root/ppg/common/deps/geos315/package.yaml`
- Create: `root/ppg/common/deps/geos315/obs/_service`
- Create: `root/ppg/common/deps/geos315/rpm/geos315.spec`

**Acceptance Criteria:**
- [ ] The spec is PGDG's `geos315/main/geos315.spec` plus the folded EL-8/EL-9/EL-10/SLES-16 differences, with the edits below and no other functional change
- [ ] There is no `ld.so.conf`, `pgdg-srpm-macros` or `PGDG` Release string in the spec
- [ ] The cmake call passes `-DCMAKE_INSTALL_RPATH=%{geosinstdir}/%{_geoslibdir}` and `-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF`
- [ ] The RUNPATH check block is present at the end of `%install`
- [ ] `parse-spec.sh` reports OK on el8, el9, el10 and suse1600
- [ ] `percona-obs project verify --no-scm-validate` passes

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/geos315/rpm/geos315.spec && ! grep -nE 'ld\.so\.conf|pgdg-srpm|PGDG%' root/ppg/common/deps/geos315/rpm/geos315.spec` → `OK el8 OK el9 OK el10 OK suse1600` and no grep output

**Steps:**

- [ ] **Step 1: Fetch PGDG** — `$S/pgdg-fetch.sh geos315 $S/pgdg/geos315`. Read the printed variant diffs. Each variant-only hunk that touches EL-8, EL-9, EL-10 or SLES-16 goes into the ported spec under the matching `%if 0%{?rhel} == N` / `%if 0%{?suse_version} == 1600` guard.

- [ ] **Step 2: Create the package files**

`root/ppg/common/deps/geos315/package.yaml`:
```yaml
title: GEOS 3.15 (PGDG layout)
description: |
  GEOS 3.15 installed under /usr/geos315, ported from PGDG (pgdg-rpms
  e38918e8) without its /etc/ld.so.conf.d drop-in: consumers and the GEOS
  binaries find the library through RUNPATH. Linked by percona-postgis
  (3.5 and 3.7), libspatialite50 and gdal313/gdal38.
build:
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
```

`root/ppg/common/deps/geos315/obs/_service`:
```xml
<services>
  <service name="download_url">
    <param name="host">github.com</param>
    <param name="protocol">https</param>
    <param name="path">/libgeos/geos/releases/download/%!{GIS_GEOS_VERSION}/geos-%!{GIS_GEOS_VERSION}.tar.bz2</param>
    <param name="filename">geos-%!{GIS_GEOS_VERSION}.tar.bz2</param>
  </service>
</services>
```

- [ ] **Step 3: Port the spec** — copy `$S/pgdg/geos315/main/geos315.spec` to `root/ppg/common/deps/geos315/rpm/geos315.spec`, then:

a. `Version:	3.15.0` → `Version:	%!{GIS_GEOS_VERSION}`; `Release:	2PGDG%{?dist}` → `Release:	1%{?dist}`; add `Vendor:		Percona LLC` and `Packager:	Percona LLC` after `URL:`.

b. `Source0:` → `Source0:	%{sname}-%{version}.tar.bz2`.

c. `BuildRequires:	libtool gcc-c++ pgdg-srpm-macros >= 2.0.0` → `BuildRequires:	libtool gcc-c++ binutils`.

d. In `%build`, replace the `%cmake` invocation with:
```
%cmake .. \
	-DCMAKE_INSTALL_PREFIX:PATH=%{geosinstdir} -DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
	-DCMAKE_INSTALL_RPATH:STRING=%{geosinstdir}/%{_geoslibdir} \
	-D LIB_INSTALL_DIR=%{_lib} .
```

e. In `%install`, delete the three lines under `# Create linker config file:` (the `mkdir` and `echo ... ld.so.conf.d`). In `%files`, delete the `%config(noreplace) ... ld.so.conf.d/...` line. Delete `%post`/`%postun` `/sbin/ldconfig` (nothing in the system linker path changes).

f. Append at the end of `%install`:
```
# PERCONA: PGDG registers %{geosinstdir} in /etc/ld.so.conf.d; we do not
# (system-wide linker path stays untouched). Every ELF object must find
# its siblings through RUNPATH instead.
for f in $(find %{buildroot}%{geosinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{geosinstdir}/%{_geoslibdir}' \
    || { echo "PERCONA: no RUNPATH to %{geosinstdir}/%{_geoslibdir} in ${f#%{buildroot}}"; exit 1; }
done
```

g. Add the top `%changelog` entry described in Global Constraints (version `%!{GIS_GEOS_VERSION}`-1 rendered literally as `3.15.0-1`).

- [ ] **Step 4: Verify** — run the Verify command above, then:

Run: `venv/bin/python -m percona_obs project verify --no-scm-validate`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add root/ppg/common/deps/geos315
git commit -s -m "common:deps: add geos315 (GEOS 3.15, PGDG layout, RUNPATH)"
```

```json:metadata
{"files": ["root/ppg/common/deps/geos315/package.yaml", "root/ppg/common/deps/geos315/obs/_service", "root/ppg/common/deps/geos315/rpm/geos315.spec"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/geos315/rpm/geos315.spec && ! grep -nE 'ld\\.so\\.conf|pgdg-srpm|PGDG%' root/ppg/common/deps/geos315/rpm/geos315.spec", "acceptanceCriteria": ["PGDG main + folded variants", "no ld.so.conf/pgdg-srpm/PGDG release", "cmake install rpath flags", "RUNPATH check in %install", "parse OK el8/el9/el10/suse1600", "project verify passes"], "modelTier": "standard"}
```

---

### Task 3: proj98 and proj96 packages

**Goal:** `proj98` (9.8.1, every RPM repo except EL8) and `proj96` (9.6.2, EL8/UBI8 only)
build into `/usr/proj98` and `/usr/proj96` with RUNPATH.

**Files:**
- Create: `root/ppg/common/deps/proj98/{package.yaml,obs/_service,rpm/proj98.spec}`
- Create: `root/ppg/common/deps/proj96/{package.yaml,obs/_service,rpm/proj96.spec}`

**Acceptance Criteria:**
- [ ] Both specs are PGDG's `main` plus folded variant differences, with the edits below
- [ ] proj98 is disabled on RockyLinux_8, UBI_8 and the deb repos; proj96 is enabled only on RockyLinux_8 and UBI_8
- [ ] There is no `ld.so.conf`, `pgdg-srpm-macros` or `%pgdg_set_gis_variables` in either spec
- [ ] The RUNPATH check is present in both `%install` sections
- [ ] `parse-spec.sh` OK for both (all four targets parse even where the repo is disabled)

**Verify:** `for p in proj98 proj96; do $S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/$p/rpm/$p.spec || exit 1; done; ! grep -nE 'ld\.so\.conf|pgdg' root/ppg/common/deps/proj9[68]/rpm/*.spec` → two `OK ...` lines, no grep output

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh proj98 $S/pgdg/proj98; $S/pgdg-fetch.sh proj96 $S/pgdg/proj96`. Fold variant hunks as in Task 2 Step 1: a variant-only hunk goes in under its `%if` guard.

- [ ] **Step 2: package.yaml files**

`root/ppg/common/deps/proj98/package.yaml`:
```yaml
title: PROJ 9.8 (PGDG layout)
description: |
  PROJ 9.8 under /usr/proj98, ported from PGDG (pgdg-rpms e38918e8), no
  ld.so.conf.d drop-in (RUNPATH). EL8/UBI8 use proj96 instead (PGDG's EL-8
  choice).
build:
  RockyLinux_8: false
  UBI_8: false
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
```

`root/ppg/common/deps/proj96/package.yaml`:
```yaml
title: PROJ 9.6 (PGDG layout, EL8)
description: |
  PROJ 9.6 under /usr/proj96 for EL8/UBI8 only, following PGDG's EL-8
  choice for postgis35/gdal38. Ported from pgdg-rpms e38918e8 without the
  ld.so.conf.d drop-in (RUNPATH).
build:
  RockyLinux_9: false
  RockyLinux_9.6: false
  RockyLinux_10: false
  UBI_9: false
  UBI_10: false
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
  openSUSE_Tumbleweed: false
  openSUSE_Leap_16: false
```

- [ ] **Step 3: _service files**

`root/ppg/common/deps/proj98/obs/_service`:
```xml
<services>
  <service name="download_url">
    <param name="host">download.osgeo.org</param>
    <param name="protocol">https</param>
    <param name="path">/proj/proj-%!{GIS_PROJ_VERSION}.tar.gz</param>
    <param name="filename">proj-%!{GIS_PROJ_VERSION}.tar.gz</param>
  </service>
</services>
```
`root/ppg/common/deps/proj96/obs/_service`: the same with `%!{GIS_PROJ_EL8_VERSION}` in both `path` and `filename`.

- [ ] **Step 4: Port both specs** — copy `$S/pgdg/proj98/main/proj98.spec` and `$S/pgdg/proj96/main/proj96.spec`, then in each:

a. Replace the `%pgdg_set_gis_variables` line with:
```
%global projinstdir /usr/%{name}
```
(Check the spec for any other `%proj9Xinstdir`/`%proj9Xmajorversion` uses and replace them with `%{projinstdir}` / the literal `98`/`96`.)

b. `Version:` → `%!{GIS_PROJ_VERSION}` (proj98) / `%!{GIS_PROJ_EL8_VERSION}` (proj96). `Release:` → `1%{?dist}`. Add `Vendor:`/`Packager:` `Percona LLC`. `Source0:` → `Source0:	%{sname}-%{version}.tar.gz`.

c. Remove `pgdg-srpm-macros >= ...` from its `BuildRequires:` line (keep the rest of the line) and add `BuildRequires:	binutils`.

d. Delete `Source2:	%{name}-pgdg-libs.conf`, the two `%install` lines that create `ld.so.conf.d` and install `%{SOURCE2}`, and the `%config(noreplace) ... ld.so.conf.d` line in `%files`.

e. In the cmake invocation of `%build`, add these two arguments (right after `-DCMAKE_INSTALL_PREFIX...`):
```
	-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
	-DCMAKE_INSTALL_RPATH:STRING=%{projinstdir}/lib64 \
```

f. Append the RUNPATH check to `%install`:
```
# PERCONA: no /etc/ld.so.conf.d drop-in; RUNPATH must cover our lib dir.
for f in $(find %{buildroot}%{projinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{projinstdir}/lib64' \
    || { echo "PERCONA: no RUNPATH to %{projinstdir}/lib64 in ${f#%{buildroot}}"; exit 1; }
done
```

g. Add the changelog entry (Global Constraints).

h. EL8 note: the existing `root/ppg/common/deps/proj/rpm/proj.spec` needed gcc-toolset-14 on EL8 ("PROJ 9.6's C23 cmake check", changelog 2026-05-27). If PGDG's proj96 spec does not already use a newer GCC on EL8, copy our existing block into proj96.spec:
```
%if 0%{?rhel} == 8
%global gts_version 14
%endif
...
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
```
and `source /opt/rh/gcc-toolset-%{gts_version}/enable` at the top of `%build` and `%install` inside `%if 0%{?gts_version}`. Copy those lines from `root/ppg/common/deps/proj/rpm/proj.spec`; `grep -n gts_version` there shows them.

- [ ] **Step 5: Verify** — run the Verify command.

- [ ] **Step 6: Commit**

```bash
git add root/ppg/common/deps/proj98 root/ppg/common/deps/proj96
git commit -s -m "common:deps: add proj98 and proj96 (EL8) in PGDG layout with RUNPATH"
```

```json:metadata
{"files": ["root/ppg/common/deps/proj98/package.yaml", "root/ppg/common/deps/proj98/obs/_service", "root/ppg/common/deps/proj98/rpm/proj98.spec", "root/ppg/common/deps/proj96/package.yaml", "root/ppg/common/deps/proj96/obs/_service", "root/ppg/common/deps/proj96/rpm/proj96.spec"], "verifyCommand": "for p in proj98 proj96; do $S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/$p/rpm/$p.spec || exit 1; done; ! grep -nE 'ld\\.so\\.conf|pgdg' root/ppg/common/deps/proj9[68]/rpm/*.spec", "acceptanceCriteria": ["PGDG main + folded variants", "repo scoping per package.yaml", "no ld.so.conf/pgdg macros", "RUNPATH check present", "parse OK"], "modelTier": "standard"}
```

---

### Task 4: libgeotiff17 package

**Goal:** `libgeotiff17` 1.7.4 is built in `/usr/libgeotiff17` against proj96 (EL8)
or proj98 (all others), with RUNPATH to its own lib dir and to PROJ.

**Files:**
- Create: `root/ppg/common/deps/libgeotiff17/{package.yaml,obs/_service}`
- Create: `root/ppg/common/deps/libgeotiff17/rpm/{libgeotiff17.spec,libgeotiff_cmake.patch,libgeotiff-1.7.4-proj.patch}`

**Acceptance Criteria:**
- [ ] The spec selects proj96 on `rhel == 8` and proj98 elsewhere through an explicit `%global` block (no `%pgdg_set_gis_variables`)
- [ ] Both PGDG patches are carried unchanged and applied with `%patch -P N -p1`
- [ ] RUNPATH covers `%{libgeotiffinstdir}/lib` and `%{projinstdir}/lib64`; the check is in `%install`
- [ ] There is no ld.so.conf drop-in; parse is OK on all four targets

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/libgeotiff17/rpm/libgeotiff17.spec && ! grep -nE 'ld\.so\.conf|pgdg' root/ppg/common/deps/libgeotiff17/rpm/libgeotiff17.spec` → `OK el8 OK el9 OK el10 OK suse1600`

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh libgeotiff17 $S/pgdg/libgeotiff17`. Copy both `.patch` files from `main/` into `rpm/`. Fold variant spec hunks under their guards.

- [ ] **Step 2: package.yaml** — copy the `build:` block of `root/ppg/common/deps/geos315/package.yaml` (the five deb repos `false`), with:
```yaml
title: libgeotiff 1.7 (PGDG layout)
description: |
  libgeotiff 1.7 under /usr/libgeotiff17, linked against our proj96 (EL8)
  or proj98, so GDAL and PostGIS never load a distro PROJ next to ours.
  Ported from pgdg-rpms e38918e8 without the ld.so.conf.d drop-in.
build:
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
```

- [ ] **Step 3: _service**
```xml
<services>
  <service name="download_url">
    <param name="host">github.com</param>
    <param name="protocol">https</param>
    <param name="path">/OSGeo/libgeotiff/releases/download/%!{GIS_LIBGEOTIFF_VERSION}/libgeotiff-%!{GIS_LIBGEOTIFF_VERSION}.tar.gz</param>
    <param name="filename">libgeotiff-%!{GIS_LIBGEOTIFF_VERSION}.tar.gz</param>
  </service>
</services>
```

- [ ] **Step 4: Port the spec** — in the copy of `main/libgeotiff17.spec`:

a. Replace `%pgdg_set_gis_variables` and the following `%if ... proj96 ... %else ... proj98 ... %endif` block (spec lines ~5–15) with:
```
%global libgeotiffinstdir /usr/%{name}
%if 0%{?rhel} == 8
%global projmajorversion %!{GIS_PROJ_EL8_MAJOR}
%global projfullversion %!{GIS_PROJ_EL8_VERSION}
%else
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%endif
%global projinstdir /usr/proj%{projmajorversion}
```
Then replace any remaining `%{libgeotiff17instdir}` with `%{libgeotiffinstdir}`.

b. `Version:` → `%!{GIS_LIBGEOTIFF_VERSION}`, `Release:` → `1%{?dist}`, Vendor/Packager, `Source0:	%{sname}-%{version}.tar.gz`. Remove `Source2: ...pgdg-libs.conf`. Make sure the `Patch0:`/`Patch1:` names match the files you copied.

c. In `BuildRequires:	pgdg-srpm-macros >= 1.0.53 cmake gcc gcc-c++ ccache`, drop `pgdg-srpm-macros >= 1.0.53` and add `binutils`. Make sure `proj%{projmajorversion}-devel >= %{projfullversion}` is a BuildRequires.

d. If `%prep` uses `%patch0`/`%patch1`, convert them to `%patch -P 0 -p1` / `%patch -P 1 -p1`.

e. In the cmake call, add `-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF` and `-DCMAKE_INSTALL_RPATH:STRING="%{libgeotiffinstdir}/lib;%{projinstdir}/lib64"` (keep PGDG's `-DPROJ_LIBRARY=%{projinstdir}/lib64/libproj.so` and include-dir args).

f. Delete the ld.so.conf `%install` lines and the `%files` `%config` line. Append the RUNPATH check, which requires both dirs:
```
# PERCONA: no /etc/ld.so.conf.d drop-in; RUNPATH must reach our lib + PROJ.
for f in $(find %{buildroot}%{libgeotiffinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{libgeotiffinstdir}/lib %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done
```

g. Add the changelog entry.

- [ ] **Step 5: Verify** — run the Verify command.

- [ ] **Step 6: Commit**

```bash
git add root/ppg/common/deps/libgeotiff17
git commit -s -m "common:deps: add libgeotiff17 on proj98/proj96 with RUNPATH"
```

```json:metadata
{"files": ["root/ppg/common/deps/libgeotiff17/package.yaml", "root/ppg/common/deps/libgeotiff17/obs/_service", "root/ppg/common/deps/libgeotiff17/rpm/libgeotiff17.spec", "root/ppg/common/deps/libgeotiff17/rpm/libgeotiff_cmake.patch", "root/ppg/common/deps/libgeotiff17/rpm/libgeotiff-1.7.4-proj.patch"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/libgeotiff17/rpm/libgeotiff17.spec && ! grep -nE 'ld\\.so\\.conf|pgdg' root/ppg/common/deps/libgeotiff17/rpm/libgeotiff17.spec", "acceptanceCriteria": ["explicit proj96/proj98 selection", "PGDG patches carried, %patch -P", "RUNPATH covers own lib + PROJ", "no ld.so.conf; parse OK"], "modelTier": "standard"}
```

---

### Task 5: librttopo package (EL8/UBI8 only)

**Goal:** `librttopo` 1.1.0 builds on RockyLinux_8 and UBI_8, the only repos
whose EPEL lacks it, linked against geos315.

**Files:**
- Create: `root/ppg/common/deps/librttopo/{package.yaml,obs/_service,rpm/librttopo.spec}`

**Acceptance Criteria:**
- [ ] It is enabled only on RockyLinux_8 and UBI_8
- [ ] The spec is PGDG's `EL-8/librttopo.spec` (folded with main), building against `geos315-devel` with RUNPATH to `/usr/geos315/lib64`
- [ ] It installs to the standard `%{_libdir}` (as PGDG does; librttopo is unversioned and lives in /usr), so only geos needs a RUNPATH entry
- [ ] Parse is OK on el8

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/librttopo/rpm/librttopo.spec` → line starts with `OK el8`

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh librttopo $S/pgdg/librttopo`. Use `EL-8/librttopo.spec` as the base (resolve it if it's a symlink). Check its install prefix: if it is not `%{_prefix}`, keep PGDG's prefix and extend the RUNPATH check to that lib dir.

- [ ] **Step 2: package.yaml**
```yaml
title: librttopo (EL8 only)
description: |
  RT Topology library required by libspatialite50. EPEL 9/10 and openSUSE
  ship it; EPEL 8 does not, so it is built here for RockyLinux_8/UBI_8 only,
  linked against geos315. Ported from pgdg-rpms e38918e8.
build:
  RockyLinux_9: false
  RockyLinux_9.6: false
  RockyLinux_10: false
  UBI_9: false
  UBI_10: false
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
  openSUSE_Tumbleweed: false
  openSUSE_Leap_16: false
```

- [ ] **Step 3: _service** — download_url to the same host/path as PGDG's `Source0` (read it from the fetched spec), with `filename` equal to the basename `Source0` expects; version through `%!{GIS_LIBRTTOPO_VERSION}`. If `Source0` is a `gitlab.com/rttopo/librttopo/-/archive/...` URL, the service is:
```xml
<services>
  <service name="download_url">
    <param name="host">gitlab.com</param>
    <param name="protocol">https</param>
    <param name="path">/rttopo/librttopo/-/archive/librttopo-%!{GIS_LIBRTTOPO_VERSION}/librttopo-librttopo-%!{GIS_LIBRTTOPO_VERSION}.tar.gz</param>
    <param name="filename">librttopo-librttopo-%!{GIS_LIBRTTOPO_VERSION}.tar.gz</param>
  </service>
</services>
```
Make sure `filename` equals the basename the ported spec's `Source0:` resolves to, and that `%setup -n` matches the directory inside the archive.

- [ ] **Step 4: Port the spec.** Replace `%pgdg_set_gis_variables` and any geos version selection with:
```
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
```
`Version: %!{GIS_LIBRTTOPO_VERSION}`, `Release: 1%{?dist}`, Vendor/Packager, drop `pgdg-srpm-macros`, add `BuildRequires: geos%{geosmajorversion}-devel >= %{geosfullversion}` and `binutils`. In `%build`, before `%configure`:
```
export LDFLAGS="-Wl,-rpath,%{geosinstdir}/lib64 $LDFLAGS"
```
and pass `--with-geosconfig=%{geosinstdir}/bin/geos-config` if PGDG does not already. Append to `%install`:
```
# PERCONA: librttopo links geos315 outside the system linker path.
for f in %{buildroot}%{_libdir}/librttopo.so.*; do
  [ -L "$f" ] && continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{geosinstdir}/lib64' \
    || { echo "PERCONA: librttopo lacks RUNPATH to %{geosinstdir}/lib64"; exit 1; }
done
```
Add the changelog entry.

- [ ] **Step 5: Verify and commit**

```bash
git add root/ppg/common/deps/librttopo
git commit -s -m "common:deps: add librttopo for EL8 (EPEL 8 lacks it), on geos315"
```

```json:metadata
{"files": ["root/ppg/common/deps/librttopo/package.yaml", "root/ppg/common/deps/librttopo/obs/_service", "root/ppg/common/deps/librttopo/rpm/librttopo.spec"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/librttopo/rpm/librttopo.spec", "acceptanceCriteria": ["enabled only RockyLinux_8/UBI_8", "built on geos315 with RUNPATH", "parse OK el8"], "modelTier": "standard"}
```

---

### Task 6: libspatialite50 package

**Goal:** `libspatialite50` 5.1.0 builds in `/usr/libspatialite50` against geos315,
the PROJ for that distro, and librttopo, with RUNPATH.

**Files:**
- Create: `root/ppg/common/deps/libspatialite50/{package.yaml,obs/_service,rpm/libspatialite50.spec}`

**Acceptance Criteria:**
- [ ] The explicit `%global` block selects geos315 and proj96 (EL8) or proj98
- [ ] librttopo comes from our package on EL8 and from EPEL/distro elsewhere (`BuildRequires: librttopo-devel >= 1.1.0`). PGDG's `-44` release floor is removed
- [ ] The minizip BuildRequires follow PGDG's per-distro conditionals (`minizip-ng-compat-devel` on EL10, `minizip-devel` elsewhere)
- [ ] RUNPATH covers `/usr/libspatialite50/lib`, `/usr/geos315/lib64` and the PROJ lib64; the check is in `%install`
- [ ] Parse is OK on all four targets

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/libspatialite50/rpm/libspatialite50.spec && ! grep -nE 'ld\.so\.conf|pgdg' root/ppg/common/deps/libspatialite50/rpm/libspatialite50.spec` → `OK el8 OK el9 OK el10 OK suse1600`

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh libspatialite50 $S/pgdg/libspatialite50`; fold variants.

- [ ] **Step 2: package.yaml** (deb repos off, as in geos315):
```yaml
title: SpatiaLite 5.0 ABI (PGDG layout)
description: |
  libspatialite 5.1 under /usr/libspatialite50, linked against geos315 and
  our PROJ (proj96 on EL8, proj98 elsewhere) for GDAL's SQLite/SpatiaLite
  driver. Ported from pgdg-rpms e38918e8 without the ld.so.conf.d drop-in.
build:
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
```

- [ ] **Step 3: _service**
```xml
<services>
  <service name="download_url">
    <param name="host">www.gaia-gis.it</param>
    <param name="protocol">https</param>
    <param name="path">/gaia-sins/libspatialite-sources/libspatialite-%!{GIS_LIBSPATIALITE_VERSION}.tar.gz</param>
    <param name="filename">libspatialite-%!{GIS_LIBSPATIALITE_VERSION}.tar.gz</param>
  </service>
</services>
```

- [ ] **Step 4: Port the spec.** Replace `%pgdg_set_gis_variables` and the geos/proj selection lines (spec lines ~10–23) with:
```
%global libspatialitemajorversion 50
%global libspatialiteinstdir /usr/%{name}
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
%if 0%{?rhel} == 8
%global projmajorversion %!{GIS_PROJ_EL8_MAJOR}
%global projfullversion %!{GIS_PROJ_EL8_VERSION}
%else
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%endif
%global projinstdir /usr/proj%{projmajorversion}
```
`Version: %!{GIS_LIBSPATIALITE_VERSION}`, `Release: 1%{?dist}`, Vendor/Packager, `Source0: %{sname}-%{version}.tar.gz`. Remove `Source1: ...pgdg-libs.conf`, `pgdg-srpm-macros`, and the ld.so.conf install and `%files` lines. Change `librttopo-devel >= 1.1.0-44` to `librttopo-devel >= %!{GIS_LIBRTTOPO_VERSION}`. Add `BuildRequires: binutils`. In `%build`, make LDFLAGS carry:
```
-Wl,-rpath,%{libspatialiteinstdir}/lib:%{geosinstdir}/lib64:%{projinstdir}/lib64
```
(prepend to PGDG's existing LDFLAGS export). Append the RUNPATH check:
```
# PERCONA: no /etc/ld.so.conf.d drop-in; RUNPATH must reach own lib, GEOS, PROJ.
for f in $(find %{buildroot}%{libspatialiteinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{libspatialiteinstdir}/lib %{geosinstdir}/lib64 %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done
```
Add the changelog entry.

- [ ] **Step 5: Verify and commit**

```bash
git add root/ppg/common/deps/libspatialite50
git commit -s -m "common:deps: add libspatialite50 on geos315 + proj98/proj96 with RUNPATH"
```

```json:metadata
{"files": ["root/ppg/common/deps/libspatialite50/package.yaml", "root/ppg/common/deps/libspatialite50/obs/_service", "root/ppg/common/deps/libspatialite50/rpm/libspatialite50.spec"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/libspatialite50/rpm/libspatialite50.spec && ! grep -nE 'ld\\.so\\.conf|pgdg' root/ppg/common/deps/libspatialite50/rpm/libspatialite50.spec", "acceptanceCriteria": ["explicit geos315 + proj selection", "librttopo floor without -44", "minizip conditionals", "RUNPATH covers 3 dirs", "parse OK"], "modelTier": "standard"}
```

---

### Task 7: gdal38 package (EL8/UBI8)

**Goal:** `gdal38` 3.8.5 builds on RockyLinux_8 and UBI_8 in `/usr/gdal38`,
mirroring PGDG's `EL-8` variant (on geos315 and proj96, no Python/Java bindings),
with RUNPATH.

**Files:**
- Create: `root/ppg/common/deps/gdal38/{package.yaml,obs/_service}`
- Create: `root/ppg/common/deps/gdal38/rpm/{gdal38.spec,gdal-3.1.2-sphinx-rhel.patch,gdal-3.3.1-sfcgal-linker.patch,gdal-cleaner.sh,PROVENANCE.TXT-fedora}`

**Acceptance Criteria:**
- [ ] It is enabled only on RockyLinux_8 and UBI_8
- [ ] The spec is PGDG's `EL-8/gdal38.spec` with the edits below; drivers and subpackages are otherwise unchanged
- [ ] `BuildRequires: libpq5-devel` (PGDG's own libpq) is replaced by `libpq-devel`
- [ ] RUNPATH of every ELF under `/usr/gdal38` covers `/usr/gdal38/lib`, `/usr/geos315/lib64`, `/usr/proj96/lib64`, `/usr/libgeotiff17/lib` and `/usr/libspatialite50/lib`
- [ ] Parse is OK on el8

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/gdal38/rpm/gdal38.spec | grep -q '^OK el8' && ! grep -nE 'ld\.so\.conf|pgdg-srpm|libpq5' root/ppg/common/deps/gdal38/rpm/gdal38.spec` → exit 0

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh gdal38 $S/pgdg/gdal38`. Base: `EL-8/` (resolve symlinks). Copy the two patches, `gdal-cleaner.sh` and `PROVENANCE.TXT-fedora` into `rpm/`.

- [ ] **Step 2: package.yaml** — the same `build:` block as `root/ppg/common/deps/librttopo/package.yaml` (enabled only RockyLinux_8 and UBI_8), with:
```yaml
title: GDAL 3.8 (PGDG layout, EL8)
description: |
  GDAL 3.8 under /usr/gdal38 for EL8/UBI8 only, PGDG's EL-8 choice for
  postgis35, built on geos315 + proj96 + libgeotiff17 + libspatialite50.
  Ported from pgdg-rpms e38918e8 (EL-8 variant) without the ld.so.conf.d
  drop-in.
```

- [ ] **Step 3: _service** — PGDG's Source0 is the Fedora-cleaned tarball on download.postgresql.org:
```xml
<services>
  <service name="download_url">
    <param name="host">download.postgresql.org</param>
    <param name="protocol">https</param>
    <param name="path">/pub/repos/yum/sources/gdal/3.8/gdal-%!{GIS_GDAL_EL8_VERSION}-fedora.tar.xz</param>
    <param name="filename">gdal-%!{GIS_GDAL_EL8_VERSION}-fedora.tar.xz</param>
  </service>
</services>
```
Before committing, confirm the URL exists:
`curl -sfI https://download.postgresql.org/pub/repos/yum/sources/gdal/3.8/gdal-3.8.5-fedora.tar.xz | head -1` → `HTTP/... 200`.
If it does not, read PGDG's `Source0:` for the exact path.

- [ ] **Step 4: Port the spec:**

a. Replace `%pgdg_set_gis_variables` and the geos/proj/libspatialite `%global` assignments (spec lines ~28–40) with:
```
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
%global projmajorversion %!{GIS_PROJ_EL8_MAJOR}
%global projfullversion %!{GIS_PROJ_EL8_VERSION}
%global projinstdir /usr/proj%{projmajorversion}
%global libgeotiffmajorversion 17
%global libgeotiffinstdir /usr/libgeotiff%{libgeotiffmajorversion}
%global libspatialitemajorversion 50
%global libspatialiteinstdir /usr/libspatialite%{libspatialitemajorversion}
%global gdalinstdir /usr/%{name}
```
Keep PGDG's `%global gdalsomajorversion` and the other non-GIS globals as they are.

b. `Version:` → `%!{GIS_GDAL_EL8_VERSION}`; `Release:` → `1%{?dist}`; Vendor/Packager; delete `Source6: %{name}-pgdg-libs.conf`, the `%install` ld.so.conf lines, and the `%files` `%config ... ld.so.conf.d` line.

c. Drop `pgdg-srpm-macros >= ...` from its BuildRequires line; `libpq5-devel` → `libpq-devel`; add `BuildRequires: binutils`.

d. Convert any `%patchN` to `%patch -P N -p1`.

e. Extend PGDG's `LDFLAGS=... -Wl,-rpath,...` line so that the rpath list begins with `%{gdalinstdir}/lib:`, and add to the cmake call:
```
 -DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
 -DCMAKE_INSTALL_RPATH:STRING="%{gdalinstdir}/lib;%{projinstdir}/lib64;%{libgeotiffinstdir}/lib;%{geosinstdir}/lib64;%{libspatialiteinstdir}/lib" \
```

f. Append the RUNPATH check:
```
# PERCONA: no /etc/ld.so.conf.d drop-in; every ELF under the prefix needs
# RUNPATH to GDAL itself and to each GIS library it links.
for f in $(find %{buildroot}%{gdalinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{gdalinstdir}/lib %{geosinstdir}/lib64 %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done
```

g. Add the changelog entry.

- [ ] **Step 5: Verify and commit**

```bash
git add root/ppg/common/deps/gdal38
git commit -s -m "common:deps: add gdal38 for EL8 (PGDG EL-8 variant) with RUNPATH"
```

```json:metadata
{"files": ["root/ppg/common/deps/gdal38/package.yaml", "root/ppg/common/deps/gdal38/obs/_service", "root/ppg/common/deps/gdal38/rpm/gdal38.spec"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/gdal38/rpm/gdal38.spec | grep -q '^OK el8' && ! grep -nE 'ld\\.so\\.conf|pgdg-srpm|libpq5' root/ppg/common/deps/gdal38/rpm/gdal38.spec", "acceptanceCriteria": ["EL8/UBI8 only", "PGDG EL-8 variant with edits", "libpq-devel instead of libpq5-devel", "RUNPATH covers GDAL/GEOS/PROJ", "parse OK el8"], "modelTier": "frontier"}
```

---

### Task 8: gdal313 package (full parity)

**Goal:** `gdal313` 3.13.3 builds in `/usr/gdal313` on every RPM repo except EL8,
with PGDG's drivers and subpackages (`-libs`, `-devel`, tools,
`-python3`/`-python-tools` and `-java`/`-javadoc` where PGDG enables them),
on geos315 + proj98 + libgeotiff17 + libspatialite50, with RUNPATH.

**Files:**
- Create: `root/ppg/common/deps/gdal313/{package.yaml,obs/_service}`
- Create: `root/ppg/common/deps/gdal313/rpm/{gdal313.spec,gdal313-cleanup.patch,gdal-cleaner.sh,PROVENANCE.TXT-fedora}`

**Acceptance Criteria:**
- [ ] It is disabled on RockyLinux_8, UBI_8 and the deb repos
- [ ] It is PGDG's `main` spec with the folded EL-9/EL-10/SLES-16 hunks; the driver and subpackage set is unchanged apart from the documented exceptions below
- [ ] EL10: Python is `python3` (3.12), BuildRequires `python3-devel`/`python3-numpy`, and minizip comes through libspatialite; the java version is `java-21-openjdk-devel`
- [ ] `libpq5-devel` → `libpq-devel` on EL. On SUSE the libpq devel package name is resolved with the OBS query below
- [ ] The RUNPATH check covers `/usr/gdal313` *and* the Python extension modules (`%{python3_sitearch}/osgeo/_*.so`) and the Java JNI `.so`
- [ ] Parse is OK on el9, el10 and suse1600

**Verify:** `$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/gdal313/rpm/gdal313.spec | grep -qE 'OK el9 OK el10 OK suse1600' && ! grep -nE 'ld\.so\.conf|pgdg-srpm|libpq5' root/ppg/common/deps/gdal313/rpm/gdal313.spec` → exit 0

**Steps:**

- [ ] **Step 1: Fetch** — `$S/pgdg-fetch.sh gdal313 $S/pgdg/gdal313`. Copy `main/gdal313-cleanup.patch`, `main/gdal-cleaner.sh` and `main/PROVENANCE.TXT-fedora` into `rpm/`. Read the EL-9, EL-10 and SLES-16 diffs and fold each under its guard.

- [ ] **Step 2: package.yaml**
```yaml
title: GDAL 3.13 (PGDG layout)
description: |
  GDAL 3.13 under /usr/gdal313 with PGDG's full driver and subpackage set
  (python3/java bindings where PGDG builds them), on geos315 + proj98 +
  libgeotiff17 + libspatialite50. EL8/UBI8 use gdal38 instead. Ported from
  pgdg-rpms e38918e8 without the ld.so.conf.d drop-in.
build:
  RockyLinux_8: false
  UBI_8: false
  Debian_12: false
  Debian_13: false
  Ubuntu_22.04: false
  Ubuntu_24.04: false
  Ubuntu_26.04: false
```

- [ ] **Step 3: _service**
```xml
<services>
  <service name="download_url">
    <param name="host">download.postgresql.org</param>
    <param name="protocol">https</param>
    <param name="path">/pub/repos/yum/sources/gdal/3.13/gdal-%!{GIS_GDAL_VERSION}-fedora.tar.xz</param>
    <param name="filename">gdal-%!{GIS_GDAL_VERSION}-fedora.tar.xz</param>
  </service>
</services>
```
Confirm the URL: `curl -sfI https://download.postgresql.org/pub/repos/yum/sources/gdal/3.13/gdal-3.13.3-fedora.tar.xz | head -1` → `200`.

- [ ] **Step 4: Port the spec:**

a. Replace `%pgdg_set_gis_variables` (line 37) and the geos/proj/libspatialite `%global` block (lines ~39–55) with:
```
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%global projinstdir /usr/proj%{projmajorversion}
%global libgeotiffmajorversion 17
%global libgeotiffinstdir /usr/libgeotiff%{libgeotiffmajorversion}
%global libspatialitemajorversion 50
%global libspatialiteinstdir /usr/libspatialite%{libspatialitemajorversion}
%global gdalinstdir /usr/%{name}
```
Keep `%global gdalsomajorversion 39` and the rest.

b. `Version:	%{gdalmajorversion}.3` → `Version:	%!{GIS_GDAL_VERSION}`; `Release:` → `1%{?dist}`; Vendor/Packager. Delete `Source6` and the ld.so.conf install and `%files` lines. Replace `BuildRequires: geos%{geosmajorversion}-devel >= 3.13.3` with `>= %{geosfullversion}`. Drop `pgdg-srpm-macros >= 1.0.52`; add `BuildRequires: binutils`.

c. Python selection: in the `%if 0%{?rhel} && 0%{?rhel} <= 10` block that sets `python3_pkgversion 3.12`, split EL10 out:
```
%if 0%{?rhel} && 0%{?rhel} <= 9
%global	__ospython %{_bindir}/python3.12
%global	python3_pkgversion 3.12
%endif
%if 0%{?rhel} == 10
# PERCONA: EL10's python3 *is* 3.12; there is no python3.12-devel/-numpy.
%global	__ospython %{_bindir}/python3
%global	python3_pkgversion 3
%endif
```

d. libpq: replace `BuildRequires:	libpq5-devel` with:
```
%if 0%{?suse_version}
BuildRequires:	<SUSE_LIBPQ_DEVEL>
%else
BuildRequires:	libpq-devel
%endif
```
Resolve `<SUSE_LIBPQ_DEVEL>` with this read-only query. The first name that returns a `binary` element without `error` is the one to use:
```bash
for b in libpq-devel postgresql-devel postgresql18-devel postgresql17-devel; do
  venv/bin/osc -A https://api.opensuse.org api "/build/openSUSE:Factory/standard/x86_64/_repository?view=binaryversions&binary=$b" | grep -q 'error=' || { echo "$b"; break; }
done
```
Check the same name against `openSUSE:Leap:16.0/standard` (and its `openSUSE:Backports:SLE-16.0/standard` path) with the same query.

e. Convert `%patch0` to `%patch -P 0 -p1` if present.

f. RPATH: extend PGDG's `LDFLAGS=... -Wl,-rpath,...` so the list begins with `%{gdalinstdir}/lib:`, and add to the cmake call:
```
 -DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
 -DCMAKE_INSTALL_RPATH:STRING="%{gdalinstdir}/lib;%{projinstdir}/lib64;%{libgeotiffinstdir}/lib;%{geosinstdir}/lib64;%{libspatialiteinstdir}/lib" \
```

g. Append the RUNPATH check, which also covers the bindings:
```
# PERCONA: no /etc/ld.so.conf.d drop-in; GDAL, its apps, the Python
# extension modules and the JNI library must all reach the GIS libs via RUNPATH.
for f in $(find %{buildroot}%{gdalinstdir} %{buildroot}%{python3_sitearch}/osgeo %{buildroot}%{_jnidir} -type f 2>/dev/null); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{gdalinstdir}/lib %{geosinstdir}/lib64 %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done
```
If the Python modules come out without RUNPATH (setuptools ignores CMAKE_INSTALL_RPATH), fix that in `%install` before the check with patchelf, on the bindings only:
`for m in %{buildroot}%{python3_sitearch}/osgeo/_*.so; do patchelf --set-rpath '%{gdalinstdir}/lib:%{projinstdir}/lib64:%{geosinstdir}/lib64:%{libgeotiffinstdir}/lib:%{libspatialiteinstdir}/lib' "$m"; done`
and add `BuildRequires: patchelf`. Note: `patchelf` 0.17.x/0.18.0 corrupt ELFs. Use the distro's patchelf only if `rpm -q patchelf` in the build log shows ≥ 0.19; otherwise prefer setting `LDFLAGS` before the Python build step.

h. Add the changelog entry.

- [ ] **Step 5: Verify and commit**

```bash
git add root/ppg/common/deps/gdal313
git commit -s -m "common:deps: add gdal313 with PGDG parity (bindings included) and RUNPATH"
```

```json:metadata
{"files": ["root/ppg/common/deps/gdal313/package.yaml", "root/ppg/common/deps/gdal313/obs/_service", "root/ppg/common/deps/gdal313/rpm/gdal313.spec"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps root/ppg/common/deps/gdal313/rpm/gdal313.spec | grep -qE 'OK el9 OK el10 OK suse1600' && ! grep -nE 'ld\\.so\\.conf|pgdg-srpm|libpq5' root/ppg/common/deps/gdal313/rpm/gdal313.spec", "acceptanceCriteria": ["disabled on EL8/UBI8/deb", "PGDG main + folded variants, parity kept", "EL10 python3/java-21 adjustments", "libpq-devel on EL, resolved SUSE name", "RUNPATH check incl. python/JNI", "parse OK el9/el10/suse1600"], "modelTier": "frontier"}
```

---

### Task 9: PR A on OBS (common:deps libraries)

**Goal:** Tasks 1–8 are pushed as one PR against `percona/main`, and every new
package builds green on every enabled repo × arch on both OBS instances.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (push, PR and verification only)

**Acceptance Criteria:**
- [ ] The user approved the push and the PR in chat before `git push` / `gh pr create`
- [ ] The PR CI's OBS sync job succeeded for the PR (`gh pr checks <N>`)
- [ ] `build status` on b.o.o for `ppg:common:deps` shows geos315, proj98, proj96, libgeotiff17, librttopo, libspatialite50, gdal38 and gdal313 as `succeeded` (or `disabled`/`excluded`) on every repo × arch, with no `failed`/`unresolvable`/`broken`
- [ ] The same holds on labs for the UBI_8/9/10 repos
- [ ] The existing `geos`/`proj`/`sfcgal` packages are unaffected (still `succeeded`)
- [ ] The user merged the PR

**Verify:** `venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:common:deps` and `venv/bin/python -m percona_obs -P labsmain -R isv:percona:PR:pr-<N> build status ppg:common:deps` → no `failed`, `unresolvable` or `broken` for the eight new packages

**Steps:**

- [ ] **Step 1:** Ask the user: "Push branch `postgis-gis-stack` to `percona` and open PR 'common:deps: PGDG GIS library stack (geos315, proj98/96, libgeotiff17, librttopo, libspatialite50, gdal313/38)'?" Wait for a yes.
- [ ] **Step 2:** `git push -u percona postgis-gis-stack`, then `gh pr create --repo percona/obs-packaging --base main --head postgis-gis-stack`. The body summarizes the spec §1 and links the spec file. No Claude attribution, no `obs-sync` label.
- [ ] **Step 3:** `gh pr checks <N> --watch` until the sync job finishes.
- [ ] **Step 4:** Run both Verify commands and capture the output. For each failure, read the build log (`venv/bin/osc -A https://api.opensuse.org buildlog isv:percona:PR:pr-<N>:ppg:common:deps <pkg> <repo> <arch> | tail -80`), fix it in a new commit on the same branch, push (the user already approved pushes to this PR branch; ask again if in doubt) and repeat. Typical fixes: a BuildRequires name differing on a distro, a RUNPATH check finding an object without RUNPATH.
- [ ] **Step 5:** When everything is green, post the captured status output in chat and ask the user to merge. The task closes when `gh pr view <N> --json state -q .state` → `MERGED`.

```json:metadata
{"files": [], "verifyCommand": "venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:common:deps", "acceptanceCriteria": ["user approved push+PR", "PR sync job green", "8 new packages succeeded on all b.o.o repos x arches", "UBI repos green on labs", "existing geos/proj/sfcgal unaffected", "PR merged"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

---

### Task 10: PostGIS specs switch to the PGDG stack (+ GEOS 3.15 backport)

**Goal:** Both `percona-postgis` specs select geos315 + gdal313/proj98 (gdal38/proj96
on EL8) + libgeotiff17 + libspatialite50 + SFCGAL 2.3 through one block with pins,
link GDAL by RUNPATH, and 3.5 carries PGDG's GEOS 3.15 backport on both RPM and deb.

**Files:**
- Modify: `root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec`
- Create: `root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch`
- Create: `root/ppg/staging/_shared/percona-postgis/debian/patches/series`
- Create: `root/ppg/staging/_shared/percona-postgis/debian/patches/geos315-backport`
- Modify: `root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec`

**Acceptance Criteria:**
- [ ] Neither spec contains `gdal3.4`, `geos-devel`, `proj-devel`, `pgdg-srpm-macros`, `Requires:	hdf5` or `geos proj libgeotiff`
- [ ] The rendered el9 spec requires `geos315 >= 3.15.0`, `proj98 >= 9.8.1`, `gdal313-libs >= 3.13.3` and `libgeotiff17`; el8 requires `proj96 >= 9.6.2` and `gdal38-libs >= 3.8.5`
- [ ] `%build` LDFLAGS carry `-Wl,-rpath,%{gdalinstdir}/lib`, and `%install` asserts the postgis_raster `.so` RUNPATH contains `%{gdalinstdir}/lib` (when `%{raster}`)
- [ ] The 3.5 spec has `Patch0: postgis35-3.5.7-geos315-backport.patch` applied by `%patch -P 0 -p1`; the 3.7 spec has no such patch
- [ ] The debian `series` lists `geos315-backport`; `debian/control` is unchanged
- [ ] Parse is OK for both specs (PG 18 macros for `_shared`, PG 19 for 19) on all four targets

**Verify:** `for p in root/ppg/staging/18:root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec root/ppg/staging/19:root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec; do $S/parse-spec.sh ${p%%:*} ${p#*:} || exit 1; done; ! grep -nE 'gdal3\.4|geos-devel|proj-devel|pgdg-srpm|Requires:\s+hdf5|geos proj libgeotiff' root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec` → two OK lines, no grep output

**Steps:**

- [ ] **Step 1: New worktree for PR B** (after PR A merged):
`git -C /home/rdias/Work/percona-obs-packaging fetch percona && git -C /home/rdias/Work/percona-obs-packaging worktree add -b postgis-gis-specs .claude/worktrees/postgis-gis-specs percona/main`, then `cd` there and link `venv`.

- [ ] **Step 2: Selection block (both specs).** Replace everything from the line `#%pgdg_set_gis_variables` through the `%endif` that closes the `libspatialitemajorversion` `%if/%else` (just before `%ifarch ppc64 ppc64le s390 s390x armv7hl`) with:
```
# PERCONA: GIS library selection mirrors PGDG's postgis35/postgis37
# headers (pgdg-rpms e38918e8). Versions come from root/macros.yaml
# (GIS_*); the libraries are built in ppg:common:deps. EL8 follows PGDG's
# EL-8 choice (gdal38 + proj96); PGDG dropped EL8 from postgis37, we keep it.
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
%if 0%{?rhel} == 8
%global projmajorversion %!{GIS_PROJ_EL8_MAJOR}
%global projfullversion %!{GIS_PROJ_EL8_VERSION}
%global gdalmajorversion %!{GIS_GDAL_EL8_MAJOR}
%global gdalfullversion %!{GIS_GDAL_EL8_VERSION}
%else
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%global gdalmajorversion %!{GIS_GDAL_MAJOR}
%global gdalfullversion %!{GIS_GDAL_VERSION}
%endif
%global projinstdir /usr/proj%{projmajorversion}
%global gdalinstdir /usr/gdal%{gdalmajorversion}
%global libgeotiffmajorversion 17
%global libgeotiffinstdir /usr/libgeotiff%{libgeotiffmajorversion}
%global libspatialitemajorversion 50
%global libspatialiteinstdir /usr/libspatialite%{libspatialitemajorversion}
%global sfcgalfullversion %!{GIS_SFCGAL_VERSION}
```

- [ ] **Step 3: Dependency blocks (both specs).** Make each replacement below; the 3.7 spec may differ in whitespace or SUSE guards, so match by content.

GEOS + geotiff:
```
%if 0%{?rhel} && 0%{?rhel} >= 8
BuildRequires:	geos-devel libgeotiff-devel
%else
BuildRequires:	geos%{geosmajorversion}-devel >= %{geosfullversion}
BuildRequires:	libgeotiff%{libgeotiffmajorversion}-devel
%if !0%{?suse_version}
BuildRequires:	pgdg-srpm-macros >= 1.0.53
%endif
%endif
```
→
```
BuildRequires:	geos%{geosmajorversion}-devel >= %{geosfullversion}
BuildRequires:	libgeotiff%{libgeotiffmajorversion}-devel
```

PROJ + json-c (the whole `%if 0%{?suse_version}` … `%endif` block containing `proj%{projmajorversion}-devel`):
```
BuildRequires:	proj%{projmajorversion}-devel >= %{projfullversion} flex
%if 0%{?suse_version}
BuildRequires:	libjson-c-devel
%else
BuildRequires:	json-c-devel
%endif
```

SFCGAL (inside `%if %{sfcgal}`): `SFCGAL SFCGAL-devel >= 2.1.0` → `SFCGAL-devel >= %{sfcgalfullversion}, SFCGAL-devel < 2.4`. In the `suse_version >= 1600` (3.7: `== 1600`) branch, `sfcgal sfcgal-devel` → `sfcgal-devel >= %{sfcgalfullversion}, sfcgal-devel < 2.4`. Leave the `suse_version 1500` branch as it is.

GDAL (the `%if %{raster}` block):
```
%if %{raster}
BuildRequires:	gdal%{gdalmajorversion}-devel >= %{gdalfullversion}
Requires:	gdal%{gdalmajorversion}-libs >= %{gdalfullversion}
%endif
```

Runtime: delete `Requires:	hdf5`, the two `%if 0%{?rhel} ... Requires: gdal3.4-libs / gdal-libs` blocks, and the `%if 0%{?rhel} && 0%{?rhel} >= 8 / Requires: geos proj libgeotiff / %else ... %endif` block. Put in their place:
```
Requires:	geos%{geosmajorversion} >= %{geosfullversion}
Requires:	proj%{projmajorversion} >= %{projfullversion}
Requires:	libgeotiff%{libgeotiffmajorversion}
```

- [ ] **Step 4: RUNPATH for GDAL (both specs).** In `%build`, after the `LDFLAGS="-Wl,-rpath,%{libspatialiteinstdir}/lib ${LDFLAGS}"` line, add:
```
# PERCONA: no /etc/ld.so.conf.d for the GIS libs; postgis_raster must find
# libgdal (and the tools libgeotiff) through RUNPATH.
LDFLAGS="-Wl,-rpath,%{gdalinstdir}/lib -Wl,-rpath,%{libgeotiffinstdir}/lib ${LDFLAGS}" ; export LDFLAGS
```
At the end of `%install`, add:
```
%if %{raster}
# PERCONA: assert the raster module resolves GDAL without ld.so.conf.d.
readelf -d %{buildroot}%{pginstdir}/lib/postgis_raster-%{postgissomajorversion}.so \
  | grep -qE '\((RUNPATH|RPATH)\).*%{gdalinstdir}/lib' \
  || { echo "PERCONA: postgis_raster lacks RUNPATH to %{gdalinstdir}/lib"; exit 1; }
%endif
```

- [ ] **Step 5: Backport patch (3.5 only).**
```bash
curl -fsSL https://raw.githubusercontent.com/pgdg-packaging/pgdg-rpms/e38918e895bcd74d083b33ccb440f3afd21a5c97/rpm/redhat/main/non-common/postgis35/main/postgis35-3.5.7-geos315-backport.patch \
  -o root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch
mkdir -p root/ppg/staging/_shared/percona-postgis/debian/patches
cp root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch root/ppg/staging/_shared/percona-postgis/debian/patches/geos315-backport
printf 'geos315-backport\n' > root/ppg/staging/_shared/percona-postgis/debian/patches/series
```
In the `_shared` spec, after `Source4:` add:
```
# PERCONA: PGDG's GEOS 3.15 support for 3.5.7 (stable-3.5 !445 + !465; ST_Split
# of a line by points). Inert below GEOS 3.15. Drop with PostGIS 3.5.8.
Patch0:		postgis35-3.5.7-geos315-backport.patch
```
and in `%prep`, after `%setup -q -n percona-postgis-%{version}`, add `%patch -P 0 -p1`.

Then check the patch applies to the 3.5.7 tree:
```bash
tmp=$(mktemp -d) && git clone -q --depth 1 --branch 3.5.7 https://github.com/postgis/postgis.git $tmp/p && git -C $tmp/p apply --check $(pwd)/root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch && echo APPLIES
```
Expected: `APPLIES`.

- [ ] **Step 6: Verify** — run the Verify command, then render the el9 spec and check the Requires:
`OUTDIR=$S/r18 venv/bin/python $S/render-spec.py root/ppg/staging/18 root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec >/dev/null && rpmspec -q --requires --undefine fedora --define 'rhel 9' --define 'dist .el9' $S/r18/percona-postgis.spec 2>/dev/null | grep -E 'geos|proj|gdal|geotiff'`
Expected lines include `geos315 >= 3.15.0`, `proj98 >= 9.8.1`, `gdal313-libs >= 3.13.3` and `libgeotiff17`. Repeat with `rhel 8` and expect `proj96 >= 9.6.2` and `gdal38-libs >= 3.8.5`.

- [ ] **Step 7: Commit**

```bash
git add root/ppg/staging/_shared/percona-postgis root/ppg/staging/19/percona-postgis
git commit -s -m "percona-postgis: link the PGDG GIS stack (geos315, proj98/96, gdal313/38) with RUNPATH

3.5 carries PGDG's GEOS 3.15 backport (stable-3.5 !445 + !465) on RPM
and deb until PostGIS 3.5.8."
```

```json:metadata
{"files": ["root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec", "root/ppg/staging/_shared/percona-postgis/rpm/postgis35-3.5.7-geos315-backport.patch", "root/ppg/staging/_shared/percona-postgis/debian/patches/series", "root/ppg/staging/_shared/percona-postgis/debian/patches/geos315-backport", "root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec"], "verifyCommand": "for p in root/ppg/staging/18:root/ppg/staging/_shared/percona-postgis/rpm/percona-postgis.spec root/ppg/staging/19:root/ppg/staging/19/percona-postgis/rpm/percona-postgis.spec; do $S/parse-spec.sh ${p%%:*} ${p#*:} || exit 1; done", "acceptanceCriteria": ["no distro/EPEL GIS names left", "el9/el8 rendered Requires as specified", "GDAL RUNPATH in build + install assertion", "3.5 Patch0 applied, 3.7 none", "debian series lists backport", "parse OK both specs"], "modelTier": "standard"}
```

---

### Task 11: PR B on OBS (PostGIS)

**Goal:** PR B builds `percona-postgis` green in `ppg:staging:14`…`19` on every RPM
repo × arch and on the deb repos, against the new libraries.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none

**Acceptance Criteria:**
- [ ] The user approved the push and the PR
- [ ] `percona-postgis` (and on 19 also `percona-postgis-tiger-geocoder`/`percona-address-standardizer`, if they rebuild) shows `succeeded` on every enabled repo × arch for majors 14–19 on b.o.o and on labs (UBI)
- [ ] An el9 build log shows `geos315-devel`, `proj98-devel` and `gdal313-devel` installed; an el8 log shows `proj96-devel` and `gdal38-devel`
- [ ] The dependency cascade promoted only `percona-postgis` and its dependents (no unrelated packages), per the PR's sync job summary
- [ ] The user merged the PR

**Verify:** `for v in 14 15 16 17 18 19; do venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:staging:$v percona-postgis; done` → no `failed`/`unresolvable`/`broken`

**Steps:**

- [ ] **Step 1:** Ask the user to approve pushing `postgis-gis-specs` and opening PR "percona-postgis: link the PGDG GIS stack". Wait for a yes.
- [ ] **Step 2:** Push to `percona` and open the PR (no attribution, no label). Run `gh pr checks <N> --watch`.
- [ ] **Step 3:** Run the Verify loop plus the labs equivalent (`-P labsmain -R isv:percona:PR:pr-<N>`). Check the dependencies in one log: `venv/bin/osc -A https://api.opensuse.org buildlog isv:percona:PR:pr-<N>:ppg:staging:18 percona-postgis RockyLinux_9 x86_64 | grep -E 'geos315|proj98|gdal313' | head`.
- [ ] **Step 4:** Fix failures with new commits on the branch (same loop as Task 9). Post the captured status in chat and ask the user to merge. Done when the PR state is `MERGED`.

```json:metadata
{"files": [], "verifyCommand": "for v in 14 15 16 17 18 19; do venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:staging:$v percona-postgis; done", "acceptanceCriteria": ["user approved push+PR", "postgis succeeded all majors/repos/arches incl. labs", "build logs show new -devel packages", "cascade promoted only postgis + dependents", "PR merged"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

---

### Task 12: Aggregates into staging; retire unversioned geos/proj

**Goal:** Every `ppg:staging:<ver>` aggregates the new runtime libraries on the
right repos. The old `geos`/`proj` aggregates and common:deps packages, and the
Debian 11-only geos deb packaging, are removed.

**Files:**
- Create: `root/ppg/staging/_shared/{geos315,proj98,proj96,libgeotiff17,librttopo,libspatialite50,gdal313,gdal38}/{package.yaml,obs/_aggregate}`
- Create: symlinks `root/ppg/staging/{14,15,16,17,18,19}/<each of the 8>` → `../_shared/<pkg>`
- Delete: `root/ppg/staging/_shared/geos`, `root/ppg/staging/_shared/proj`, and their 6+6 symlinks
- Delete: `root/ppg/common/deps/geos`, `root/ppg/common/deps/proj`

**Acceptance Criteria:**
- [ ] 8 `_aggregate` files, each pointing at `${OBS_ROOTPRJ}:ppg:common:deps` with the matching `<package>`
- [ ] Each aggregate's `package.yaml` `build:` flags equal the source package's (copy them verbatim), so EL8-only, non-EL8 and no-deb scoping match
- [ ] 48 new symlinks resolve (`find root/ppg/staging -maxdepth 2 -xtype l` prints nothing)
- [ ] No `geos`/`proj` directories or symlinks remain under `root/ppg/staging` or `root/ppg/common/deps`; `sfcgal` is untouched
- [ ] `grep -rnE 'gdal-libs|gdal3\.4|\bgeos\b|\bproj\b' root/common/containers root/ppg/staging/*/containers root/ppg/staging/_shared/*containers* 2>/dev/null` shows no package-name use in image recipes (documentation comments are fine)
- [ ] `percona-obs project verify --no-scm-validate` passes

**Verify:** `ls root/ppg/staging/_shared/*/obs/_aggregate | wc -l && find root/ppg/staging -maxdepth 2 -xtype l | wc -l && test ! -e root/ppg/staging/_shared/geos && test ! -e root/ppg/common/deps/proj && venv/bin/python -m percona_obs project verify --no-scm-validate` → aggregate count includes the 8 new ones, `0` dangling links, verify exit 0

**Steps:**

- [ ] **Step 1: New worktree for PR C** (after PR B merged): branch `postgis-gis-aggregates`, the same commands as Task 10 Step 1.

- [ ] **Step 2: Generate the aggregates**
```bash
for p in geos315 proj98 proj96 libgeotiff17 librttopo libspatialite50 gdal313 gdal38; do
  d=root/ppg/staging/_shared/$p; mkdir -p $d/obs
  cat > $d/obs/_aggregate <<EOF
<aggregatelist>
  <aggregate project="\${OBS_ROOTPRJ}:ppg:common:deps">
    <package>$p</package>
  </aggregate>
</aggregatelist>
EOF
  { echo "# Publishes ppg:common:deps/$p in this staging major; repo scoping"
    echo "# mirrors root/ppg/common/deps/$p/package.yaml (copy changes there too)."
    sed -n '/^build:/,$p' root/ppg/common/deps/$p/package.yaml; } > $d/package.yaml
  for v in 14 15 16 17 18 19; do ln -s ../_shared/$p root/ppg/staging/$v/$p; done
done
```
Check that one generated `_aggregate` is byte-identical in shape to `root/ppg/staging/_shared/sfcgal/obs/_aggregate`, apart from the package name: `diff <(sed s/geos315/sfcgal/ root/ppg/staging/_shared/geos315/obs/_aggregate) root/ppg/staging/_shared/sfcgal/obs/_aggregate` → no output.

- [ ] **Step 3: Retire the old packages**
```bash
for v in 14 15 16 17 18 19; do git rm -q root/ppg/staging/$v/geos root/ppg/staging/$v/proj; done
git rm -rq root/ppg/staging/_shared/geos root/ppg/staging/_shared/proj root/ppg/common/deps/geos root/ppg/common/deps/proj
```

- [ ] **Step 4: Check for leftover references** —
`grep -rnE 'common:deps:?/?(geos|proj)\b|/_shared/(geos|proj)\b' root docs .github | grep -v superpowers`
Each hit must be fixed (or be a historical comment, left as is). Run the container recipe grep from the Acceptance Criteria.

- [ ] **Step 5: Verify and commit**
```bash
git add -A root/ppg/staging root/ppg/common/deps
git commit -s -m "staging: aggregate the PGDG GIS libraries; retire unversioned geos/proj"
```

```json:metadata
{"files": ["root/ppg/staging/_shared/geos315/obs/_aggregate", "root/ppg/staging/_shared/gdal313/obs/_aggregate", "root/ppg/staging/_shared/gdal38/obs/_aggregate", "root/ppg/staging/_shared/proj98/obs/_aggregate", "root/ppg/staging/_shared/proj96/obs/_aggregate", "root/ppg/staging/_shared/libgeotiff17/obs/_aggregate", "root/ppg/staging/_shared/librttopo/obs/_aggregate", "root/ppg/staging/_shared/libspatialite50/obs/_aggregate"], "verifyCommand": "find root/ppg/staging -maxdepth 2 -xtype l | wc -l && venv/bin/python -m percona_obs project verify --no-scm-validate", "acceptanceCriteria": ["8 aggregates to common:deps", "build flags copied from source package", "48 symlinks resolve", "geos/proj retired, sfcgal untouched", "no container recipe uses old names", "project verify passes"], "modelTier": "mechanical"}
```

---

### Task 13: PR C on OBS + install check

**Goal:** The staging repos publish the new libraries, `dnf` resolves
`percona-postgis35_<V>` from them on EL 8/9/10 with no EPEL GIS packages, and
the retired packages are gone from OBS.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none

**Acceptance Criteria:**
- [ ] The user approved the push and the PR
- [ ] All 8 aggregates show `succeeded` (or disabled) per repo in `ppg:staging:14..19` on both instances
- [ ] In a `rockylinux:8`, `rockylinux:9` and `rockylinux:10` container, `dnf install --assumeno percona-postgis35_18` against the PR's staging:18 repo (plus EPEL) lists `geos315`, the `proj9X`, `gdal3XX-libs` and `libgeotiff17`, and **no** package named exactly `gdal-libs`, `gdal3.4-libs`, `geos` or `proj`
- [ ] After merge: `osc ls isv:percona:ppg:common:deps` and `osc ls isv:percona:ppg:staging:18` no longer list `geos`/`proj`. If they do, ask the user to run the deletion (production write) and record their answer
- [ ] The user merged the PR

**Verify:** `podman run --rm rockylinux:9 bash -c '<repo setup from project install>; dnf -y install epel-release; dnf install --assumeno percona-postgis35_18 2>&1 | grep -E "^ (geos|proj|gdal|libgeotiff)"'` → shows `geos315`, `proj98`, `gdal313-libs`, `libgeotiff17` and nothing unversioned

**Steps:**

- [ ] **Step 1:** Ask for push/PR approval; push `postgis-gis-aggregates` and open PR "staging: publish the PGDG GIS libraries". Watch `gh pr checks <N>`.
- [ ] **Step 2:** `for v in 14 15 16 17 18 19; do venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:staging:$v; done | grep -E 'geos315|proj9|gdal3|libgeotiff|librttopo|libspatialite'`, plus the same with `-P labsmain`.
- [ ] **Step 3:** Get the repo setup with `venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> project install ppg:staging:18` and use its EL8/9/10 repo lines in the container command from Verify. Run it for each of `rockylinux:8`, `rockylinux:9` and `rockylinux:10`. These only run OBS-built artifacts, no local builds.
- [ ] **Step 4:** Post the outputs, ask the user to merge, then do the post-merge `osc ls` checks.

```json:metadata
{"files": [], "verifyCommand": "podman run --rm rockylinux:9 bash -c '<repo setup>; dnf -y install epel-release; dnf install --assumeno percona-postgis35_18'", "acceptanceCriteria": ["user approved push+PR", "aggregates succeeded all majors both instances", "dnf resolves new libs, no unversioned EPEL GIS on el8/9/10", "old geos/proj gone from OBS or user-run deletion recorded", "PR merged"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

---

### Task 14: Tarball percona-proj to 9.6.2 / 9.8.1

**Goal:** `ppg:common:deps:tarballs/percona-proj` builds PROJ 9.6.2 on
RockyLinux_8 (ssl1.1) and 9.8.1 on RockyLinux_9.6/RockyLinux_9 (ssl3/ssl3.5),
under `/opt/percona-proj`, `libproj.so.25`.

**Files:**
- Modify: `root/ppg/common/deps/tarballs/percona-proj/rpm/percona-proj.spec`
- Modify: `root/ppg/common/deps/tarballs/percona-proj/obs/_service`
- Modify: `root/ppg/common/deps/tarballs/percona-proj/package.yaml` (description text only)

**Acceptance Criteria:**
- [ ] `proj_version` is `%!{GIS_PROJ_EL8_VERSION}` on `rhel == 8` and `%!{GIS_PROJ_VERSION}` otherwise; `proj_soname` is 25 for both
- [ ] The EL8 branch uses the CMake build path (the autotools `./configure` branch for 6.3.2 is removed); the 9.x path keeps the plain-cmake comment and flags
- [ ] `_service` downloads both versions (two `download_url` entries, macro-driven); the old 6.3.2/9.6.0 entries are gone
- [ ] Parse is OK on el8 and el9

**Verify:** `$S/parse-spec.sh root/ppg/common/deps/tarballs root/ppg/common/deps/tarballs/percona-proj/rpm/percona-proj.spec | grep -qE '^OK el8 OK el9'` → exit 0

**Steps:**

- [ ] **Step 1: New worktree for PR D** (after PR C merged): branch `postgis-gis-tarballs`, the same commands as Task 10 Step 1.
- [ ] **Step 2:** Read `percona-proj.spec` lines 1–180. In the per-base `%if` that sets `proj_version 6.3.2` / `proj_srcidx 0` / `proj_soname 15` and `proj_version 9.6.0` / `proj_srcidx 1` / `proj_soname 25`, set:
```
%if 0%{?rhel} == 8
%global proj_version %!{GIS_PROJ_EL8_VERSION}
%global proj_srcidx 0
%else
%global proj_version %!{GIS_PROJ_VERSION}
%global proj_srcidx 1
%endif
%global proj_soname 25
```
- [ ] **Step 3:** In `%build`, delete the `./configure` branch (6.3.2 autotools, around line 108) so that every base takes the existing plain-`cmake ..` path (line ~127). If the PROJ 9.6 C23 check on EL8 needs gcc-toolset-14 (as `root/ppg/common/deps/proj` did), copy that `gts_version` block from `root/ppg/common/deps/proj96/rpm/proj96.spec` (Task 3).
- [ ] **Step 4:** In `obs/_service`, replace the two download entries with:
```xml
  <service name="download_url">
    <param name="host">download.osgeo.org</param>
    <param name="protocol">https</param>
    <param name="path">/proj/proj-%!{GIS_PROJ_EL8_VERSION}.tar.gz</param>
    <param name="filename">proj-%!{GIS_PROJ_EL8_VERSION}.tar.gz</param>
  </service>
  <service name="download_url">
    <param name="host">download.osgeo.org</param>
    <param name="protocol">https</param>
    <param name="path">/proj/proj-%!{GIS_PROJ_VERSION}.tar.gz</param>
    <param name="filename">proj-%!{GIS_PROJ_VERSION}.tar.gz</param>
  </service>
```
and make the spec's `Source0`/`Source1` names match. If the spec ships proj-data grids as separate sources, keep them.
- [ ] **Step 5:** Update the version wording in `package.yaml` `description` and the spec header comment (EL8 9.6.2, EL9 bases 9.8.1, both `libproj.so.25`, matching proj96/proj98 that PostGIS links). Add the changelog entry. Verify, then commit:
```bash
git add root/ppg/common/deps/tarballs/percona-proj
git commit -s -m "tarballs: percona-proj follows proj96/proj98 (9.6.2 EL8, 9.8.1 EL9)"
```

```json:metadata
{"files": ["root/ppg/common/deps/tarballs/percona-proj/rpm/percona-proj.spec", "root/ppg/common/deps/tarballs/percona-proj/obs/_service", "root/ppg/common/deps/tarballs/percona-proj/package.yaml"], "verifyCommand": "$S/parse-spec.sh root/ppg/common/deps/tarballs root/ppg/common/deps/tarballs/percona-proj/rpm/percona-proj.spec | grep -qE '^OK el8 OK el9'", "acceptanceCriteria": ["macro-driven versions, soname 25", "EL8 on cmake path, autotools removed", "_service downloads both new versions", "parse OK el8/el9"], "modelTier": "standard"}
```

---

### Task 15: Tarball percona-gdal to 3.8.5 / 3.13.3 (CMake) + gis-compat shim

**Goal:** `percona-gdal` builds GDAL 3.8.5 (EL8, `libgdal.so.34`) and 3.13.3 (EL9
bases, `libgdal.so.39`) under `/opt/percona-gdal` with CMake. It keeps the same
minimal driver set, uses bundled libgeotiff and links geos315.
`percona-gis-compat` `Provides:` the new by-name Requires of PostGIS.

**Files:**
- Modify: `root/ppg/common/deps/tarballs/percona-gdal/rpm/percona-gdal.spec`
- Modify: `root/ppg/common/deps/tarballs/percona-gdal/obs/_service`
- Modify: `root/ppg/common/deps/tarballs/percona-gdal/package.yaml` (description)
- Modify: `root/ppg/common/deps/tarballs/percona-gis-compat/rpm/percona-gis-compat.spec`
- Modify: `root/ppg/staging/_shared/tarballs/project.yaml` (comments only)

**Acceptance Criteria:**
- [ ] The `%build` section uses `cmake` with `-DGDAL_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_BUILD_OPTIONAL_DRIVERS=OFF` and an explicit `-DGDAL_USE_<X>=ON` for exactly the libraries in the current `BuildRequires` "driver set" list (zlib, curl, libxml2, openssl, zstd, xz/lzma, jpeg, tiff, png, sqlite, freexl, expat, json-c, pcre/pcre2, lz4). Every other `GDAL_USE_*` is OFF via `-DGDAL_USE_EXTERNAL_LIBS=OFF`
- [ ] `-DGDAL_USE_GEOTIFF_INTERNAL=ON` is set and `libgeotiff-devel` is dropped; `libspatialite-devel` is dropped (`-DGDAL_USE_SPATIALITE=OFF`); `geos-devel` → `geos315-devel` with `-DGEOS_DIR=/usr/geos315/lib64/cmake/GEOS` (or `CMAKE_PREFIX_PATH=/usr/geos315`)
- [ ] The data dir is still compiled to `%{gdal_datadir}` (`-DGDAL_RESOURCE_PATH` / `-DCMAKE_INSTALL_DATADIR` as needed) and PROJ comes from `/opt/percona-proj`
- [ ] `gdal_soname` is 34 on EL8 and 39 otherwise; `_service` downloads `gdal-%!{GIS_GDAL_EL8_VERSION}.tar.xz` and `gdal-%!{GIS_GDAL_VERSION}.tar.xz` from download.osgeo.org
- [ ] The `percona-gis-compat` Provides on EL8 are `proj96 = %!{GIS_PROJ_EL8_VERSION}`, `gdal38-libs = %!{GIS_GDAL_EL8_VERSION}`, `libgeotiff17` and `libspatialite50`; elsewhere `proj98 = %!{GIS_PROJ_VERSION}`, `gdal313-libs = %!{GIS_GDAL_VERSION}`, `libgeotiff17` and `libspatialite50`. The old `proj = …`, `gdal-libs = …` and `gdal3.4-libs = …` are removed
- [ ] Parse is OK for both specs on el8 and el9

**Verify:** `for s in percona-gdal percona-gis-compat; do $S/parse-spec.sh root/ppg/common/deps/tarballs root/ppg/common/deps/tarballs/$s/rpm/$s.spec | grep -qE '^OK el8 OK el9' || exit 1; done; ! grep -nE '^\./configure|libgeotiff-devel|libspatialite-devel|gdal3\.4-libs|gdal-libs =' root/ppg/common/deps/tarballs/percona-gdal/rpm/percona-gdal.spec root/ppg/common/deps/tarballs/percona-gis-compat/rpm/percona-gis-compat.spec` → exit 0

**Steps:**

- [ ] **Step 1:** Read `percona-gdal.spec` in full (336 lines) and record the "driver set" BuildRequires block (lines ~103–128) and every `--with-*`/`--without-*` flag of the autotools `./configure` call (line ~187 on). The new CMake call must enable exactly those libraries.
- [ ] **Step 2:** Version globals:
```
%if 0%{?rhel} == 8
%global gdal_version %!{GIS_GDAL_EL8_VERSION}
%global gdal_srcidx 0
%global gdal_soname 34
%else
%global gdal_version %!{GIS_GDAL_VERSION}
%global gdal_srcidx 1
%global gdal_soname 39
%endif
%global gdal_datadir %{gdal_prefix}/share/gdal
```
- [ ] **Step 3:** Replace the `./configure ... && make` build with:
```
mkdir -p build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=%{gdal_prefix} \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_INSTALL_RPATH="%{gdal_prefix}/lib;%{proj_prefix}/lib64;/usr/geos315/lib64" \
  -DGDAL_RESOURCE_PATH=%{gdal_datadir} \
  -DPROJ_ROOT=%{proj_prefix} \
  -DCMAKE_PREFIX_PATH="%{proj_prefix};/usr/geos315" \
  -DBUILD_APPS=OFF -DBUILD_TESTING=OFF \
  -DBUILD_PYTHON_BINDINGS=OFF -DBUILD_JAVA_BINDINGS=OFF -DBUILD_CSHARP_BINDINGS=OFF \
  -DGDAL_USE_EXTERNAL_LIBS=OFF \
  -DGDAL_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_BUILD_OPTIONAL_DRIVERS=OFF \
  -DGDAL_USE_GEOTIFF_INTERNAL=ON -DGDAL_USE_TIFF_INTERNAL=OFF \
  -DGDAL_USE_ZLIB=ON -DGDAL_USE_CURL=ON -DGDAL_USE_LIBXML2=ON -DGDAL_USE_OPENSSL=ON \
  -DGDAL_USE_ZSTD=ON -DGDAL_USE_LIBLZMA=ON -DGDAL_USE_JPEG=ON -DGDAL_USE_TIFF=ON \
  -DGDAL_USE_PNG=ON -DGDAL_USE_SQLITE3=ON -DGDAL_USE_FREEXL=ON -DGDAL_USE_EXPAT=ON \
  -DGDAL_USE_JSONC=ON -DGDAL_USE_PCRE2=ON -DGDAL_USE_LZ4=ON -DGDAL_USE_GEOS=ON \
  -DGDAL_USE_SPATIALITE=OFF
%make_build
```
Then reconcile against Step 1's list. If the old configure enabled a library not in the list above (e.g. `--with-pcre` = PCRE1 on EL8), add the matching `-DGDAL_USE_<X>=ON`. If it disabled one that is on above, set it OFF. Re-enable individually any driver that the official tarball's libgdal provably used (the spec header documents it; it was derived from `readelf -d`): `-DGDAL_ENABLE_DRIVER_<NAME>=ON` / `-DOGR_ENABLE_DRIVER_<NAME>=ON`, with at least `GTiff`, `PNG`, `JPEG`, `MEM`, `VRT` and `raw` for PostGIS raster. `%install`: `cd build && %make_install`. Keep the existing `%files` paths, adjusting `lib` vs `lib64` to `CMAKE_INSTALL_LIBDIR=lib`. Add `BuildRequires: cmake >= 3.16` and `geos315-devel`; remove `libgeotiff-devel`, `libspatialite-devel` and `geos-devel`.
- [ ] **Step 4:** `_service`: replace the 3.0.4 and 3.4.3 entries with:
```xml
  <service name="download_url">
    <param name="host">download.osgeo.org</param>
    <param name="protocol">https</param>
    <param name="path">/gdal/%!{GIS_GDAL_EL8_VERSION}/gdal-%!{GIS_GDAL_EL8_VERSION}.tar.xz</param>
    <param name="filename">gdal-%!{GIS_GDAL_EL8_VERSION}.tar.xz</param>
  </service>
  <service name="download_url">
    <param name="host">download.osgeo.org</param>
    <param name="protocol">https</param>
    <param name="path">/gdal/%!{GIS_GDAL_VERSION}/gdal-%!{GIS_GDAL_VERSION}.tar.xz</param>
    <param name="filename">gdal-%!{GIS_GDAL_VERSION}.tar.xz</param>
  </service>
```
- [ ] **Step 5: gis-compat.** In `percona-gis-compat.spec`, replace the EL8 `Provides: proj = 6.3.2` / `Provides: gdal-libs = 3.0.4` and the EL9 `Provides: proj = 9.6.0` / `Provides: gdal3.4-libs = 3.4.3` with:
```
%if 0%{?rhel} == 8
Provides:       proj%!{GIS_PROJ_EL8_MAJOR} = %!{GIS_PROJ_EL8_VERSION}
Provides:       gdal%!{GIS_GDAL_EL8_MAJOR}-libs = %!{GIS_GDAL_EL8_VERSION}
%else
Provides:       proj%!{GIS_PROJ_MAJOR} = %!{GIS_PROJ_VERSION}
Provides:       gdal%!{GIS_GDAL_MAJOR}-libs = %!{GIS_GDAL_VERSION}
%endif
Provides:       libgeotiff17 = %!{GIS_LIBGEOTIFF_VERSION}
Provides:       libspatialite50 = %!{GIS_LIBSPATIALITE_VERSION}
```
Keep `Requires: percona-gdal` and `Requires: percona-proj`. Add `Requires: geos315` (PostGIS requires it by name, and it is bundled as-is). Update the spec header comment to describe the new names.
- [ ] **Step 6:** In `root/ppg/staging/_shared/tarballs/project.yaml`, update the comment text that names `gdal-libs`/`gdal3.4-libs`/`geos proj libgeotiff` (lines ~186–220 and ~253–290) to the new names. `Prefer:` lines stay unchanged.
- [ ] **Step 7:** Verify, then commit:
```bash
git add root/ppg/common/deps/tarballs/percona-gdal root/ppg/common/deps/tarballs/percona-gis-compat root/ppg/staging/_shared/tarballs/project.yaml
git commit -s -m "tarballs: percona-gdal 3.8.5/3.13.3 on CMake with bundled geotiff; shim provides PGDG names"
```

```json:metadata
{"files": ["root/ppg/common/deps/tarballs/percona-gdal/rpm/percona-gdal.spec", "root/ppg/common/deps/tarballs/percona-gdal/obs/_service", "root/ppg/common/deps/tarballs/percona-gdal/package.yaml", "root/ppg/common/deps/tarballs/percona-gis-compat/rpm/percona-gis-compat.spec", "root/ppg/staging/_shared/tarballs/project.yaml"], "verifyCommand": "for s in percona-gdal percona-gis-compat; do $S/parse-spec.sh root/ppg/common/deps/tarballs root/ppg/common/deps/tarballs/$s/rpm/$s.spec | grep -qE '^OK el8 OK el9' || exit 1; done", "acceptanceCriteria": ["CMake minimal driver set equal to previous", "bundled geotiff, no spatialite, geos315", "data dir compiled to /opt, PROJ from /opt", "soname 34/39, _service new versions", "shim provides new names, old removed", "parse OK el8/el9"], "modelTier": "frontier"}
```

---

### Task 16: PR D on OBS (tarballs)

**Goal:** The ssl1.1, ssl3 and ssl3.5 tarballs build green for every staging
major with the new stack, and the existing guards pass.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none

**Acceptance Criteria:**
- [ ] The user approved the push and the PR
- [ ] `percona-proj`, `percona-gdal` and `percona-gis-compat` show `succeeded` in `ppg:common:deps:tarballs` (RockyLinux_8, RockyLinux_9.6, RockyLinux_9)
- [ ] The tarball simpleimage builds of `ppg:staging:<V>:tarballs` show `succeeded` on ssl1.1, ssl3 and ssl3.5 for 14–19
- [ ] A tarball build log contains no `FATAL` from `build-tarball.sh` section 0a and no SSL-ABI audit failure
- [ ] The user merged the PR

**Verify:** `for v in 14 15 16 17 18 19; do venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:staging:$v:tarballs; done` → all `succeeded`

**Steps:**

- [ ] **Step 1:** Ask for push/PR approval; push `postgis-gis-tarballs` and open PR "tarballs: follow the PGDG GIS stack". Watch checks.
- [ ] **Step 2:** Run Verify, plus `venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:common:deps:tarballs`.
- [ ] **Step 3:** `venv/bin/osc -A https://api.opensuse.org buildlog isv:percona:PR:pr-<N>:ppg:staging:18:tarballs <tarball-pkg> ssl3 x86_64 | grep -nE 'FATAL|SSL-ABI|libgdal|libproj|libgeos'` (read the package name from `osc ls`). Expected: no `FATAL`, and bundled `libgdal.so.39`, `libproj.so.25` and `libgeos_c.so.1`.
- [ ] **Step 4:** Fix, iterate, post the evidence, ask the user to merge. Done when the PR is `MERGED`.

```json:metadata
{"files": [], "verifyCommand": "for v in 14 15 16 17 18 19; do venv/bin/python -m percona_obs -P isv -R isv:percona:PR:pr-<N> build status ppg:staging:$v:tarballs; done", "acceptanceCriteria": ["user approved push+PR", "tarball deps succeeded", "ssl1.1/ssl3/ssl3.5 tarballs succeeded 14-19", "no 0a FATAL / SSL-ABI failure", "PR merged"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

---

### Task 17: ppg-testing postgis role (QA repo)

**Goal:** `Percona-QA/ppg-testing` `postgis/setup/tasks/main.yml` installs build
deps derived from the shipped package and, for 3.5.7, applies the upstream
SFCGAL test fixes and the GEOS 3.15 backport to the git checkout.

**Files:**
- Modify (in a clone of `https://github.com/Percona-QA/ppg-testing.git`, branch `postgis-gis-stack`): `postgis/setup/tasks/main.yml`

**Acceptance Criteria:**
- [ ] The hardcoded `gdal311`, `gdal311-devel`, `geos311`, `geos311-devel`, `proj95` and `proj95-devel` entries are removed
- [ ] A new task derives the `-devel` names with `rpm -q --requires {{ postgis_rhel_package_name_prefix }}` and installs them together with `SFCGAL-devel`
- [ ] A new task after "Clone postgis sources matching the packaged version" applies `8b3fcf54a572b5e84071d8fc6661003e3113b35f`, `fb149e149967fa10bed9d823d043c3c83d3b9b81` (regress files only) and PGDG's backport patch, only when `COMPONENT_REF == '3.5.7'`
- [ ] `ansible-playbook --syntax-check` (or `ansible-lint postgis/setup/tasks/main.yml`) passes
- [ ] The user approved push and PR creation on the QA repo before they happened

**Verify:** `ansible-lint postgis/setup/tasks/main.yml` (in the QA clone) → no errors; `grep -nE 'gdal311|geos311|proj95' postgis/setup/tasks/main.yml` → no output

**Steps:**

- [ ] **Step 1:** Clone into the scratchpad:
`git clone https://github.com/Percona-QA/ppg-testing.git $S/ppg-testing && git -C $S/ppg-testing checkout -b postgis-gis-stack`.
- [ ] **Step 2:** Before "Install PostGIS build dependencies, version-matched…", insert:
```yaml
  - name: Derive the GIS -devel packages the shipped PostGIS was built against
    shell: |
      set -o pipefail
      rpm -q --requires {{ postgis_rhel_package_name_prefix }} \
        | awk '{print $1}' \
        | grep -E '^(geos|proj|gdal|libgeotiff|libspatialite)[0-9]+(-libs)?$' \
        | sed -E 's/-libs$//; s/$/-devel/' | sort -u
    args:
      executable: /bin/bash
    register: gis_devel_pkgs
    changed_when: false
```
In the install task's `packages` list, delete the six `gdal311…proj95-devel` lines and their comment, and change `name: "{{ packages }}"` to `name: "{{ packages + gis_devel_pkgs.stdout_lines }}"`. Keep `SFCGAL` and `SFCGAL-devel` in the list.
- [ ] **Step 3:** After the clone task, insert:
```yaml
  # PostGIS 3.5.7's own regression tests predate SFCGAL 2.3 and GEOS 3.15.
  # Upstream fixed them on stable-3.5; apply the same fixes the package
  # carries until 3.5.8 is tagged, then delete this task.
  - name: Apply stable-3.5 test fixes for SFCGAL 2.3 / GEOS 3.15 (3.5.7 only)
    shell: |
      set -euo pipefail
      for c in 8b3fcf54a572b5e84071d8fc6661003e3113b35f fb149e149967fa10bed9d823d043c3c83d3b9b81; do
        curl -fsSL "https://gitea.osgeo.org/postgis/postgis/commit/$c.patch" \
          | git apply --include='sfcgal/regress/*'
      done
      curl -fsSL "https://raw.githubusercontent.com/pgdg-packaging/pgdg-rpms/e38918e895bcd74d083b33ccb440f3afd21a5c97/rpm/redhat/main/non-common/postgis35/main/postgis35-3.5.7-geos315-backport.patch" \
        | git apply
    args:
      chdir: /tmp/postgis
      executable: /bin/bash
    become_user: postgres
    when: lookup('env', 'COMPONENT_REF') == '3.5.7'
```
- [ ] **Step 4:** Check locally that the patches apply to the 3.5.7 tree: run the shell body above in a fresh `git clone --depth 1 --branch 3.5.7 https://github.com/postgis/postgis.git` → exit 0.
- [ ] **Step 5:** Lint (Verify), commit with `git commit -s`, then **ask the user** whether to push and open a PR against `Percona-QA/ppg-testing` (or hand the branch to QA). Do it only on a yes.

```json:metadata
{"files": ["postgis/setup/tasks/main.yml"], "verifyCommand": "cd $S/ppg-testing && ansible-lint postgis/setup/tasks/main.yml && ! grep -nE 'gdal311|geos311|proj95' postgis/setup/tasks/main.yml", "acceptanceCriteria": ["hardcoded 311/95 names removed", "-devel list derived from rpm requires", "3.5.7-only patch task with 2 commits + backport", "lint passes", "user approved push/PR"], "modelTier": "standard"}
```

---

### Task 18: End-to-end QA acceptance and PG-2864

**Goal:** The component-generic-parallel postgis job passes on every staging
major against the new stack, and PG-2864 gets the outcome.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none

**Acceptance Criteria:**
- [ ] With the user's approval, component-generic-parallel postgis runs with `USE_OBS_REPO=true` and `OBS_PROJECT=isv:percona:ppg:staging:<V>` for V in 14–19 (TEST_BRANCH = the merged ppg-testing branch)
- [ ] Each rhel-9 run's "Shipped percona-postgis… reports:" line shows `GEOS="3.15.`, `PROJ="9.8.`, `GDAL="GDAL 3.13.` and `SFCGAL 2.3.0`. On rhel-8 runs it shows PROJ 9.6 / GDAL 3.8
- [ ] Each run's installcheck reports 0 failed tests (`grep -E 'failed=[1-9]|tests? failed'` on the console finds nothing)
- [ ] A PG-2864 comment (text approved by the user before posting) states the outcome: libraries aligned with the PostGIS matrix by mirroring PGDG, the test patches in ppg-testing until 3.5.8, and the job links

**Verify:** `P=$(sed -nE 's/^password\s*=\s*//p' ~/.jenkins_jobs.ini); curl -s -u "rjd15372:$P" https://pg.cd.percona.com/job/component-generic-parallel/<build>/consoleText | grep -E 'Shipped percona-postgis|failed=[1-9]'` → the reports line with the new versions, no `failed=N>0`

**Steps:**

- [ ] **Step 1:** Ask the user to approve triggering the six postgis QA runs (Jenkins write). On a yes, use `venv/bin/python -m percona_obs -P isv qa ...` for the `percona-postgis` package `qa:` block per major (see `venv/bin/python -m percona_obs qa --help`), or let the user trigger them.
- [ ] **Step 2:** Collect each build's console with the Verify command and record the reports line and the result per major.
- [ ] **Step 3:** Draft the PG-2864 comment in chat. Post it with the Atlassian tool only after the user approves the text.

```json:metadata
{"files": [], "verifyCommand": "curl -s -u rjd15372:$P https://pg.cd.percona.com/job/component-generic-parallel/<build>/consoleText | grep -E 'Shipped percona-postgis|failed=[1-9]'", "acceptanceCriteria": ["user-approved QA runs 14-19", "rhel-9 shows GEOS 3.15/PROJ 9.8/GDAL 3.13/SFCGAL 2.3; rhel-8 PROJ 9.6/GDAL 3.8", "0 failed tests", "user-approved PG-2864 comment posted"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

---

## Dependencies

- Tasks 2–8 depend on Task 1. Task 4 depends on 3; 5 on 2; 6 on 2, 3 and 5; 7 on 2, 3, 4 and 6; 8 on 2, 3, 4 and 6.
- Task 9 depends on 1–8. Task 10 on 9; 11 on 10; 12 on 11; 13 on 12; 14 on 13; 15 on 14; 16 on 15.
- Task 17 can start after Task 9; its PR should merge together with Task 11.
- Task 18 depends on 13, 16 and 17.
