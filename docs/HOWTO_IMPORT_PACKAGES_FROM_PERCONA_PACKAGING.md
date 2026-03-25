# Importing a Package from `percona/postgres-packaging`

This guide explains how to port a package from the
[`percona/postgres-packaging`](https://github.com/percona/postgres-packaging/tree/17.9)
repository into this OBS packaging repository.

For adding a package from scratch (without an existing `percona/postgres-packaging` source),
see [PACKAGING_HOWTO.md](PACKAGING_HOWTO.md) instead.

---

## Background

`percona/postgres-packaging` (branch `17.9`) is a **CI builder** repository. Each
package directory there contains:

- A `*_builder.sh` — orchestrates fetching the upstream source, applying Percona
  overrides, and building RPMs/DEBs on a CI host.
- A Percona `.spec` file for RPM.
- Minimal DEB files: `control`, `rules`, sometimes `.install` files.
- Optional patch files (e.g. `spec.patch`, `rules.patch`).
- `versions.sh` at the root — defines all version constants used by every builder.

**We do not run the builder scripts.** Instead, we store the *merged result* of
what the builder would assemble and let OBS fetch sources and build directly.

---

## Resulting Package Structure

Every package under `root/ppg/17/` follows this layout:

```
root/ppg/17/<package-name>/
├── debian/
│   ├── debian.dsc          # OBS-specific DSC (see below)
│   ├── changelog           # Minimal Debian changelog
│   ├── compat              # debhelper compat level (9 or 10)
│   ├── control             # Package definitions (Percona version from postgres-packaging)
│   ├── copyright           # Upstream license text
│   ├── rules               # Build rules (Percona version from postgres-packaging)
│   ├── source/
│   │   ├── format          # "3.0 (quilt)" or "3.0 (native)"
│   │   └── options         # extend-diff-ignore directives
│   ├── [pkg].install       # File installation lists (optional)
│   ├── [pkg].postinst      # Post-install scripts (optional)
│   ├── [pkg].prerm         # Pre-remove scripts (optional)
│   └── patches/            # Quilt patch series (only for quilt-format packages)
│       ├── series
│       └── *.patch
├── rpm/
│   ├── [package-name].spec # RPM spec from postgres-packaging
│   ├── [package-name].service  # systemd unit (if applicable)
│   └── [other files]       # Config files, patches, extra sources cited in the spec
└── obs/
    ├── _service            # OBS service file (fetches packaging + upstream source)
    └── _multibuild         # Only for PostgreSQL extensions (multi-PG-version builds)
```

---

## Step-by-Step Guide

### Step 1 — Understand the upstream package

Open the `percona/postgres-packaging` directory for the package you want to port,
e.g. `patroni/`.

Read `versions.sh` to find the relevant version constants:

```bash
# From versions.sh (branch 17.9)
PATRONI_VERSION=4.1.0
```

Read `*_builder.sh` and note:

| Variable | Meaning |
|---|---|
| `PKGNAME_SRC_REPO` | Upstream source git URL |
| `PKGNAME_SRC_BRANCH` or `PKGNAME_SRC_TAG` | Tag/branch to check out |
| `PKGNAME_SRC_REPO_DEB` | External Debian packaging repo (if any) |
| `PKG_RAW_URL/pkgname/` | Files fetched from postgres-packaging itself |

The builder's `get_sources()` function shows:
1. Which external **DEB packaging repo** is cloned and at what tag.
2. Which files from `postgres-packaging` **replace** the ones from that DEB repo.
3. Which `sed` substitutions are applied (e.g. `@@PGMAJOR@@` → `17`).
4. What ends up in `rpm/` (usually the `.spec`, `.service`, config files).

---

### Step 2 — Create the directory skeleton

```bash
PKG=<package-name>
mkdir -p root/ppg/17/$PKG/debian/source
mkdir -p root/ppg/17/$PKG/rpm
mkdir -p root/ppg/17/$PKG/obs
```

---

### Step 3 — Assemble `debian/`

#### 3a. Get the base Debian packaging

If the builder clones an **external DEB packaging repo**, clone it locally at the
same tag the builder uses, then copy its `debian/` directory as your starting
point:

```bash
git clone <PKGNAME_SRC_REPO_DEB> /tmp/deb-base
cd /tmp/deb-base && git checkout <DEB_PACKAGING_TAG>
cp -r /tmp/deb-base/debian/* root/ppg/17/$PKG/debian/
```

If there is no external DEB packaging repo (the builder creates the `debian/`
directory from scratch), construct it manually using the files available in
`postgres-packaging/<pkg>/`.

#### 3b. Apply Percona overrides

The builder always replaces certain files from the external DEB repo with Percona
versions. Copy those from `postgres-packaging/<pkg>/`:

```bash
# Always overridden:
cp <postgres-packaging>/<pkg>/control  root/ppg/17/$PKG/debian/control
cp <postgres-packaging>/<pkg>/rules    root/ppg/17/$PKG/debian/rules

# Apply sed substitutions the builder performs, e.g.:
sed -i "s/@@PGMAJOR@@/17/g" root/ppg/17/$PKG/debian/control
```

Apply any patch files listed in the builder (e.g. `rules.patch`):

```bash
patch -p1 < <postgres-packaging>/<pkg>/rules.patch
```

#### 3c. Add OBS-required files

**`debian/compat`** — debhelper compat level:

```
10
```

**`debian/changelog`** — a minimal changelog is sufficient. The format must be
valid Debian changelog syntax. The version here is a placeholder; OBS sets the
real version from the upstream source tag.

```
<source-name> (1.0.0-1) unstable; urgency=low

  * Initial build.

 -- Percona Development Team <info@percona.com>  Mon, 01 Jan 2024 00:00:00 +0000
```

**`debian/source/format`** — choose based on whether Debian patches are applied
on top of the upstream source:

- `3.0 (quilt)` — use when the `debian/patches/` directory exists and quilt
  patches are applied to the upstream source during build.
- `3.0 (native)` — use when there are no upstream patches (all changes are
  already in the source tree or applied by the build rules directly).

**`debian/source/options`** — tells `dpkg-source` to ignore certain directories
when building the diff. Always ignore `rpm/`; also ignore `vendor/` for Go
packages:

```
# Standard packages:
extend-diff-ignore = rpm/

# Go packages (etcd-style):
extend-diff-ignore = (vendor/|rpm/)
```

---

### Step 4 — Create `debian/debian.dsc`

This is the key OBS-specific file. It is **not** a standard Debian DSC — it is
an input for OBS's `debtransform` service. OBS fetches it (via the `extract:
*.dsc` parameter in `_service`) and uses it to know what tarballs to bundle into
the generated source package.

The `Version:` field is a **placeholder** (`1.0.0`) — OBS replaces it at service
run time using the version extracted from the upstream source tag.

**Template:**

```
Format: 3.0 (quilt)
Source: <source-name>
Binary: <space-separated list of all binary packages from control>
Architecture: <any|all|any all>
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: <copy from control's Build-Depends>
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz
```

**`Debtransform-Files-Tar`** must list every tarball OBS needs to produce the
source package. At minimum: `debian.tar.gz rpm.tar.gz`. For Go packages that use
vendored modules, also list those vendor tarballs (see etcd as an example):

```
Debtransform-Files-Tar: debian.tar.gz vendor-server.tar.gz vendor-etcdctl.tar.gz vendor-etcdutl.tar.gz rpm.tar.gz
```

For PostgreSQL extension packages that use multibuild, the `Binary:` and
`Build-Depends:` fields use the `@BUILD_FLAVOR@` placeholder which OBS expands
per flavor:

```
Binary: percona-pg-telemetry@BUILD_FLAVOR@
Build-Depends: debhelper (>= 9), percona-postgresql-server-dev-@BUILD_FLAVOR@
```

---

### Step 5 — Assemble `rpm/`

Take the `.spec` file directly from `postgres-packaging/<pkg>/`. Then add every
additional file referenced in the spec's `Source*` lines:

```spec
Source0:  %{name}-%{version}.tar.gz   # generated by OBS — do NOT add this
Source1:  patroni.service             # ← add this
```

For `patroni`, the builder also creates `patroni-customizations.tar.gz` by
packing together `patroni.service`, `patroni-watchdog.service`, and
`postgres-telia.yml`. If the spec references this tarball as a Source, include it
pre-built in `rpm/`.

Any patches applied to the spec via `spec.patch` in the builder should be applied
manually — the resulting patched spec is what goes into `rpm/`.

---

### Step 6 — Create `obs/_service`

**Standard pattern (all packages):**

```xml
<services>
  <service name="obs_scm">
    <param name="url">https://github.com/rjd15372/percona-obs-packaging.git</param>
    <param name="scm">git</param>
    <param name="revision">main</param>
    <param name="version">_none_</param>
    <param name="extract">*.dsc</param>
    <param name="subdir">root/ppg/17/<PKG>/debian</param>
    <param name="filename">debian</param>
  </service>

  <service name="obs_scm">
    <param name="url">https://github.com/rjd15372/percona-obs-packaging.git</param>
    <param name="scm">git</param>
    <param name="revision">main</param>
    <param name="version">_none_</param>
    <param name="extract">*</param>
    <param name="subdir">root/ppg/17/<PKG>/rpm</param>
    <param name="filename">rpm</param>
  </service>

  <!-- Upstream source: use 'version' when you know the exact version string -->
  <service name="obs_scm">
    <param name="url"><UPSTREAM_GIT_URL></param>
    <param name="scm">git</param>
    <param name="revision"><TAG_OR_BRANCH></param>
    <param name="version"><VERSION_STRING></param>
    <param name="filename"><PKG></param>
  </service>

  <service mode="buildtime" name="tar" />
  <service mode="buildtime" name="recompress">
    <param name="file">*.tar</param>
    <param name="compression">gz</param>
  </service>
  <service mode="buildtime" name="set_version" />
</services>
```

**When the version is derived from a git tag** (e.g. tag `v4.1.0` → version
`4.1.0`), use `versionformat` + `versionrewrite-pattern` instead of `version`:

```xml
  <service name="obs_scm">
    <param name="url">https://github.com/zalando/patroni.git</param>
    <param name="scm">git</param>
    <param name="revision">v4.1.0</param>
    <param name="versionformat">@PARENT_TAG@</param>
    <param name="versionrewrite-pattern">v(.*)</param>
  </service>
```

**For Go packages with vendored modules** (e.g. etcd), add `go_modules` services
after the main services. These run in `mode="manual"` (i.e. they are run
separately to pre-populate the vendor tarballs):

```xml
  <service name="go_modules" mode="manual">
    <param name="archive">*etcd-*.obscpio</param>
    <param name="subdir">server</param>
    <param name="vendorname">vendor-server</param>
  </service>
```

---

### Step 7 — PostgreSQL extensions: add `obs/_multibuild`

If the package is a PostgreSQL extension that should build against multiple PG
versions, add `obs/_multibuild`:

```xml
<multibuild buildemptyflavor="false">
  <flavor>17</flavor>
</multibuild>
```

This causes OBS to build the package once per flavor, substituting `@BUILD_FLAVOR@`
with `17` in the `debian.dsc`, `debian/control`, and `debian/rules` at build
time.

---

## Step 8 — Test the build in OBS

Testing is done on a feature branch so that the `_service` points to that branch
and any fixes can be iterated without touching `main`.

### 8a. Create a feature branch and update `_service`

```bash
git checkout -b <package-name>
```

Edit `obs/_service` and change both `revision=main` entries (the ones fetching
from this repo) to `revision=<package-name>`:

```xml
<param name="revision">ydiff</param>   <!-- was: main -->
```

### 8b. Commit, push, and sync to OBS

```bash
git add root/ppg/17/<pkg>/
git commit -s -m "Add <pkg> <version> package for ppg/17"
git push -u origin <package-name>
./percona-obs -P dev sync push ppg:17 <pkg>
```

### 8c. Monitor build status

```bash
./percona-obs -P dev build status ppg:17 <pkg>
```

Targets are listed with status icons: `✔ succeeded`, `✗ failed`, `● building`,
`◌ scheduled`.

### 8d. Investigate failures

When a target shows `✗ failed`, retrieve the build log with `osc`:

```bash
osc -A <apiurl> buildlog <project> <pkg> <repo> <arch>
# Example:
osc -A http://192.168.1.103:3000 buildlog home:Admin:percona:ppg:17 ydiff RockyLinux_9 x86_64
```

The end of the log contains the RPM or dpkg-buildpackage error. Fix the relevant
file in `debian/` or `rpm/`, then iterate from 8b.

### 8e. Trigger a rebuild after fixing packaging files

After pushing a fix, the `_service` file itself has not changed so
`sync push` will report everything as unchanged. Trigger OBS to re-run
its services and rebuild explicitly:

```bash
./percona-obs -P dev build trigger ppg:17 <pkg>
```

### 8f. Prepare the branch for merging when all targets succeed

Once every target shows `✔ succeeded`:

1. Switch the `obs/_service` `revision` entries back to `main`.
2. Commit and push to the feature branch.

**Do NOT merge the feature branch into `main` yourself.** Leave the branch open
and let the repository owner handle the merge manually.

---

## Quick Reference: Patterns by Package Type

| Package type | `source/format` | `debian.dsc` extra tarballs | `_multibuild` | Example |
|---|---|---|---|---|
| Plain app | `3.0 (quilt)` | none | no | `etcd` |
| PG extension | `3.0 (native)` | none | yes | `percona-pg-telemetry` |
| Go app with vendored deps | `3.0 (quilt)` | `vendor-*.tar.gz` | no | `etcd` |
| Upstream DEB packaging patched | `3.0 (quilt)` | none | no | `percona-postgresql17` |
| Standalone package, no upstream patches | `3.0 (native)` | none | no | `percona-postgresql-common` |

---

## Common Pitfalls

- **`debian.dsc` version is a placeholder.** Always use `Version: 1.0.0`. OBS
  overwrites it with the version it extracts from the upstream source.
- **`Debtransform-Files-Tar` must be complete.** Every tarball that OBS needs to
  assemble the source package must be listed. Forgetting `rpm.tar.gz` will cause
  OBS to produce a DEB source package with no RPM spec.
- **`source/options` must ignore `rpm/`.** Without `extend-diff-ignore = rpm/`,
  `dpkg-source` will include the RPM directory in the Debian diff, causing build
  failures.
- **Apply all builder sed substitutions manually.** The builder replaces
  `@@PGMAJOR@@`, `@@PGMAJORVERSION@@`, etc. at runtime. In our repo those
  substitutions must already be applied before committing (or use `@BUILD_FLAVOR@`
  if it is a multibuild extension that needs per-flavor substitution by OBS).
- **The spec's `Source0` tarball is auto-generated by OBS.** Never add
  `<pkg>-<version>.tar.gz` to `rpm/`. OBS produces it from the upstream `obs_scm`
  fetch. Only add the *supplementary* sources listed as `Source1`, `Source2`, etc.
- **`obs/_service` `revision` should be `main`** (not a feature branch) once the
  packaging is ready to build in OBS.
- **`distutils` is gone in Python 3.12 (RockyLinux 9).** Upstream specs that use
  `from distutils.sysconfig import get_python_lib` will fail. Replace with the
  `sysconfig` form used in the patroni spec:
  ```
  %global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")
  ```
- **`python3-setuptools` must be in `BuildRequires` for `setup.py`-based packages.**
  Python 3.12 no longer bundles `setuptools`. Add
  `BuildRequires: python%{python3_pkgversion}-setuptools` explicitly.
- **`Release:` field must be hardcoded in the spec.** The upstream postgres-packaging
  specs often use `Release: %{release}%{?dist}` which expands to nothing under OBS
  (the `%{release}` macro is undefined). Use a hardcoded value like `Release: 1%{?dist}`.
- **`obs_scm` `filename` param must match the spec's `Source0` stem.** If the upstream
  git repo is named differently from the package (e.g. repo `patroni` but spec
  `Source0: percona-patroni-%{version}.tar.gz`), set
  `<param name="filename">percona-patroni</param>` so OBS names the tarball correctly.
  Without this OBS produces `patroni-4.1.0.tar.gz` while the spec expects
  `percona-patroni-4.1.0.tar.gz`, failing with "No such file or directory".
- **`debian.dsc` must have a `Binary:` field.** debtransform requires it to know which
  binary packages are produced. Copy the space-separated list of all binary package
  names from `debian/control`.
- **`debian/changelog` source name must match `debian/control`'s `Source:` field.**
  If they differ (e.g. `patroni` vs `percona-patroni`), dpkg-source will fail with
  "source package has two conflicting values". Always use the Percona package name in
  both files.
- **Sphinx docs extensions unavailable in OBS build environments.** If the package
  builds Sphinx documentation that uses non-standard extensions (like
  `sphinx_github_style`), those extensions may not be in the OBS build environment.
  The upstream builder typically works around this with a `sed` substitution at CI
  time. In OBS, apply the same change as a proper quilt patch:
  1. Create `debian/patches/<name>.patch` with the correct diff (use `patch --fuzz=0`
     to verify it applies cleanly — RPM builds use `--fuzz=0`).
  2. Add the patch name to `debian/patches/series`.
  3. Copy the same `.patch` file into `rpm/` so it lands in RPM's SOURCES directory.
  4. Declare it in the spec: `Patch0: <name>.patch` (after `Source*` lines) and
     apply it in `%prep`: `%patch0 -p1`.
- **Patch hunk headers must be exact for RPM builds.** RPM's `%patch` macro passes
  `--fuzz=0` to `patch`. If the hunk offset or line count in `@@ -N,M +N,M @@` is
  wrong the patch will fail even if it applied with fuzz on the command line. Always
  test locally with `patch --dry-run --fuzz=0 -p1 < file.patch` before committing.
- **Only include files in `rpm/` that are actually referenced by the spec.** Extra
  `.tar.gz` files in `rpm/` get extracted into OBS SOURCES and confuse debtransform,
  which will fail with "too many files looking like a usable source tarball". Remove
  any legacy artifacts not referenced by the current spec.
