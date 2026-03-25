# Adding a New Package from Scratch

This guide walks through creating a new package in this repository from scratch — without
importing from `percona/postgres-packaging`. Use this when packaging software that has never
been packaged here before, or when you want full control over the packaging files.

The example used throughout is **`percona-pgbadger`**, a simple Perl-based PostgreSQL log
analyser with no Go modules or PostgreSQL extension complexity.

---

## Overview

A package needs three things:

1. **`debian/`** — Debian packaging files
2. **`rpm/`** — an RPM `.spec` file (and any extra sources it references)
3. **`obs/_service`** — tells OBS where to fetch sources

Optionally:
- **`obs/_multibuild`** — for packages that build against multiple PostgreSQL versions
- **`package.yaml`** — human-readable title/description shown in OBS; also controls per-repo
  `build` and `publish` flags

Where the package lives in `root/` determines which OBS subproject it belongs to:

| Location | OBS subproject |
|---|---|
| `root/ppg/17/<pkg>/` | `<rootprj>:ppg:17` |
| `root/common/deps/runtime/<pkg>/` | `<rootprj>:common:deps:runtime` |
| `root/common/deps/build/<pkg>/` | `<rootprj>:common:deps:build` |

See [root/README.md](../root/README.md) for the full project hierarchy.

---

## Step 1 — Create the directory skeleton

```bash
PKG=percona-pgbadger
mkdir -p root/ppg/17/$PKG/debian/source
mkdir -p root/ppg/17/$PKG/rpm
mkdir -p root/ppg/17/$PKG/obs
```

---

## Step 2 — Write `debian/control`

`control` defines the source package and all binary packages it produces.

```
Source: percona-pgbadger
Section: database
Priority: optional
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper, libjson-xs-perl, libtext-csv-xs-perl

Package: percona-pgbadger
Architecture: any
Depends: libjson-xs-perl, libtext-csv-xs-perl, ${misc:Depends}, ${perl:Depends}
Provides: pgbadger
Description: Fast PostgreSQL log analysis report
 pgBadger is a PostgreSQL log analyzer built for speed with fully detailed
 reports from your PostgreSQL log file.
```

Key points:
- `Source:` must match the source package name used throughout all `debian/` files.
- `Maintainer:` is always `Percona Development Team <info@percona.com>`.
- `Build-Depends:` must list every package needed at build time (not at runtime).
- List every binary package as a `Package:` stanza.

---

## Step 3 — Write `debian/rules`

The minimal `rules` file for a standard `debhelper` build:

```makefile
#!/usr/bin/make -f

%:
	dh $@

override_dh_builddeb:
	dh_builddeb -- -Zgzip

override_dh_auto_test:
```

The `override_dh_builddeb` line forces gzip compression (OBS expects `.deb` files compressed
with gzip, not xz). The empty `override_dh_auto_test` suppresses test runs that may fail in
the OBS build environment.

---

## Step 4 — Write `debian/changelog`

A minimal changelog. The version here is a placeholder; OBS overwrites it with the version
extracted from the upstream source tag at build time.

```
percona-pgbadger (13.2-1) unstable; urgency=low

  * Update to 13.2 version.

 -- Percona Development Team <info@percona.com>  Tue, 10 Mar 2026 00:00:00 +0000
```

The source name in the first line must exactly match the `Source:` field in `control`.

---

## Step 5 — Write `debian/compat`

```
10
```

Use `10` unless the `rules` file uses features that require a higher debhelper compat level.
Alternatively, declare `debhelper-compat (= 13)` directly in `Build-Depends` — in that case
do **not** create a `compat` file.

---

## Step 6 — Write `debian/source/format` and `debian/source/options`

**`debian/source/format`** — use `3.0 (quilt)` when quilt patches are applied on top of the
upstream source (i.e. `debian/patches/` exists). Use `3.0 (native)` when there are no patches:

```
3.0 (quilt)
```

**`debian/source/options`** — always ignore the `rpm/` directory so `dpkg-source` does not
include RPM files in the Debian diff:

```
extend-diff-ignore = rpm/
```

For Go packages that use a `vendor/` directory, also add:

```
extend-diff-ignore = (vendor/|rpm/)
```

---

## Step 7 — Write `debian/debian.dsc`

This is the OBS-specific DSC file. It is **not** a standard Debian DSC — it is an input for
OBS's `debtransform` service. OBS reads it to know which tarballs to bundle into the generated
source package.

```
Format: 3.0 (quilt)
Source: percona-pgbadger
Binary: percona-pgbadger
Architecture: all
Version: 1.0.0
Maintainer: Percona Development Team <info@percona.com>
Build-Depends: debhelper (>= 9), perl, libjson-xs-perl, libtext-csv-xs-perl
Debtransform-Release: 1
Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz
```

- `Version:` is always `1.0.0` — a placeholder replaced by OBS at service run time.
- `Binary:` lists all binary package names from `control`, space-separated.
- `Debtransform-Files-Tar:` lists the tarballs OBS must produce. Always include `debian.tar.gz`
  and `rpm.tar.gz`. For Go packages with vendored modules, also list the vendor tarballs
  (e.g. `vendor-server.tar.gz`).

---

## Step 8 — Write the RPM spec (`rpm/<name>.spec`)

The spec file is the RPM equivalent of all the Debian files combined.

```spec
%global debug_package %{nil}
%global sname pgbadger

Summary:    A fast PostgreSQL log analyzer
Name:       percona-pgbadger
Version:    1.0.0
Release:    1%{?dist}
License:    PostgreSQL
Source0:    %{name}-%{version}.tar.gz
URL:        https://github.com/darold/%{sname}
BuildRequires: perl make
Requires:   perl-Text-CSV_XS perl
Provides:   pgbadger
Epoch:      1
Packager:   Percona Development Team <https://jira.percona.com>
Vendor:     Percona, LLC

%description
pgBadger is a PostgreSQL log analyzer built for speed with fully detailed
reports from your PostgreSQL log file.

%prep
%setup -q

%build
%{__perl} Makefile.PL INSTALLDIRS=vendor
%{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
%{__make} pure_install PERL_INSTALL_ROOT=%{buildroot}

%files
%doc README
%license LICENSE
%attr(755,root,root) %{_bindir}/%{sname}
%{_mandir}/man1/%{sname}.1p.gz

%changelog
* Tue Mar 10 2026 Percona Development Team <info@percona.com> 13.2-1
- Initial build
```

Important conventions:
- `Version:` is always `1.0.0` — OBS's `set_version` service overwrites it.
- `Release:` must be a hardcoded value like `1%{?dist}`. Using `%{release}` without defining
  it causes an empty string under OBS.
- `Source0:` is `%{name}-%{version}.tar.gz` — OBS generates this tarball automatically from
  the upstream `obs_scm` fetch. **Do not add this file to `rpm/`.**
- Only add `Source1`, `Source2`, … files to `rpm/` for supplementary sources the spec
  references explicitly (systemd units, config files, patches, etc.).

---

## Step 9 — Create `obs/_service`

The `_service` file tells OBS how to fetch packaging files and the upstream source.

```xml
<services>
  <service name="obs_scm">
    <param name="url">${PERCONA_OBS_PACKAGING_REPO}</param>
    <param name="scm">git</param>
    <param name="revision">${PERCONA_OBS_PACKAGING_BRANCH}</param>
    <param name="version">_none_</param>
    <param name="extract">*.dsc</param>
    <param name="subdir">${DEBIAN_PACKAGE_DIRECTORY}</param>
    <param name="filename">debian</param>
  </service>

  <service name="obs_scm">
    <param name="url">${PERCONA_OBS_PACKAGING_REPO}</param>
    <param name="scm">git</param>
    <param name="revision">${PERCONA_OBS_PACKAGING_BRANCH}</param>
    <param name="version">_none_</param>
    <param name="extract">*</param>
    <param name="subdir">${RPM_PACKAGE_DIRECTORY}</param>
    <param name="filename">rpm</param>
  </service>

  <service name="obs_scm">
    <param name="url">https://github.com/darold/pgbadger.git</param>
    <param name="scm">git</param>
    <param name="revision">v13.2</param>
    <param name="versionformat">@PARENT_TAG@</param>
    <param name="versionrewrite-pattern">v(.*)</param>
    <param name="filename">percona-pgbadger</param>
  </service>

  <service mode="buildtime" name="tar" />

  <service mode="buildtime" name="recompress">
    <param name="file">*.tar</param>
    <param name="compression">gz</param>
  </service>

  <service mode="buildtime" name="set_version" />
</services>
```

The first two `obs_scm` services always use the same env-var template — `percona-obs` injects
the correct paths automatically. Only the third service (the upstream source fetch) is
package-specific.

**Upstream source service parameters:**

| Situation | Use |
|---|---|
| Upstream tags as `vX.Y.Z` | `versionformat=@PARENT_TAG@` + `versionrewrite-pattern=v(.*)` |
| Upstream tags as plain `X.Y.Z` | `version=13.2` directly |
| Pinning to a specific commit | `revision=<full-sha>` + `versionformat=@PARENT_TAG@` |

The `filename` param sets the stem of the tarball OBS produces. It must match the
`Name:` field in the spec (which sets `Source0: %{name}-%{version}.tar.gz`).

---

## Step 10 — Optional: `package.yaml`

Create `package.yaml` in the package root to set the OBS title/description and to control
per-repo build and publish flags.

```bash
cat > root/ppg/17/percona-pgbadger/package.yaml << 'EOF'
title: percona-pgbadger
description: |
  Fast PostgreSQL log analyser built for speed with fully detailed reports.
EOF
```

### Disabling a build on a specific repository

If the package does not build on a particular distro (e.g. `Debian_13`), add a `build` map:

```yaml
title: percona-pgbadger
description: |
  Fast PostgreSQL log analyser built for speed with fully detailed reports.

build:
  Debian_13: false
```

`build: <repo>: false` emits `<build><disable repository="Debian_13"/></build>` in the OBS
package meta. Setting a value to `true` explicitly re-enables a repo that was disabled at the
project level.

### Disabling publishing on a specific repository

To stop OBS from publishing the built binaries into a repo's download area:

```yaml
publish:
  Debian_13: false
```

Both `build` and `publish` can be combined in the same file:

```yaml
title: percona-pgbadger
description: |
  Fast PostgreSQL log analyser built for speed with fully detailed reports.

build:
  Debian_13: false

publish:
  openSUSE_Tumbleweed: false
```

### Project-level flags in `project.yaml`

The same `build` and `publish` keys work in `project.yaml` and apply to the entire subproject:

```yaml
title: Common Build Dependencies Project
description: |
  Build-time dependency packages used by multiple projects.

publish: false        # blanket disable — OBS does not publish any binaries from this project
```

`publish: false` (scalar) also hides the project from the `percona-obs project install`
output, since a project whose binaries are not published cannot be added to a system's
package manager repository list.

---

## Step 11 — Sync to OBS and test

> For a full reference on `percona-obs` commands, profiles, and options see
> [docs/PERCONA_OBS_TOOL.md](PERCONA_OBS_TOOL.md).

```bash
./percona-obs -P dev sync push ppg:17 percona-pgbadger
./percona-obs -P dev build status ppg:17 percona-pgbadger
```

When a build fails, retrieve the log:

```bash
osc -A <apiurl> buildlog <project> percona-pgbadger <repo> x86_64
# Example:
osc -A http://192.168.1.103:3000 buildlog home:Admin:percona:ppg:17 percona-pgbadger RockyLinux_9 x86_64
```

After fixing packaging files, trigger a rebuild (the `_service` file has not changed so
`sync push` alone will not queue a new build):

```bash
./percona-obs -P dev build trigger ppg:17 percona-pgbadger
```

---

## Adding a Package as an Aggregate in a Subproject

When a package is built in one subproject (e.g. `common:deps:runtime`) and consumed by
another (e.g. `ppg:17`), the `ppg:17` subproject should not re-build it. Instead it
references the already-built binaries using an **aggregate**.

### What an aggregate does

An `_aggregate` file in a package directory tells OBS to pull pre-built binaries from
another project's repository instead of building from source. No source is uploaded, no
build is queued — OBS serves the binaries from the referenced project directly.

### Example: `percona-telemetry-agent` in `ppg:17`

`percona-telemetry-agent` is built in `common:deps:runtime`. To make its binaries available
in the `ppg:17` repository without rebuilding:

**1. Create the aggregate package directory:**

```bash
mkdir -p root/ppg/17/percona-telemetry-agent/obs
```

**2. Create `obs/_aggregate`:**

```xml
<aggregatelist>
  <aggregate project="${OBS_ROOTPRJ}:common:deps:runtime">
    <package>percona-telemetry-agent</package>
  </aggregate>
</aggregatelist>
```

`${OBS_ROOTPRJ}` is injected automatically by `percona-obs` from the active profile's
`rootprj` field. This makes the file portable across environments without hardcoding the
OBS organisation prefix.

**3. Sync to OBS:**

```bash
./percona-obs -P dev sync push ppg:17 percona-telemetry-agent
```

OBS will show the package as `aggregate` in its package list and serve the binaries from
`<rootprj>:common:deps:runtime` immediately — no build is needed.

### When to use aggregates

- A utility or daemon used by packages in multiple subprojects (e.g. `percona-telemetry-agent`
  used by `ppg:17`, `psmdb`, etc.).
- A build dependency that is itself built in a `common:deps:build` subproject (OBS handles
  this automatically via the project's repository path configuration — `_aggregate` files
  are only needed for runtime binary reuse between sibling subprojects).

---

## Quick Reference: File Checklist

| File | Required | Notes |
|---|---|---|
| `debian/control` | yes | Source + binary package definitions |
| `debian/rules` | yes | Build rules; always override `dh_builddeb` to force gzip |
| `debian/changelog` | yes | Placeholder version `1.0.0`; source name must match `control` |
| `debian/compat` | yes* | Omit if `debhelper-compat (= N)` is in `Build-Depends` |
| `debian/debian.dsc` | yes | OBS-specific; `Version: 1.0.0`; `Debtransform-Files-Tar` must be complete |
| `debian/source/format` | yes | `3.0 (quilt)` or `3.0 (native)` |
| `debian/source/options` | yes | Always include `extend-diff-ignore = rpm/` |
| `debian/patches/` | if needed | Quilt patches applied to upstream source |
| `debian/*.install` | if needed | File installation lists for binary packages |
| `rpm/<name>.spec` | yes | `Version: 1.0.0`; `Release: 1%{?dist}`; no `Source0` file in `rpm/` |
| `rpm/<extra-sources>` | if needed | Only files referenced as `Source1`, `Source2`, … in the spec |
| `obs/_service` | yes | Use env-var template for packaging services; customise only the upstream service |
| `obs/_aggregate` | aggregates only | Replaces `_service`; references pre-built binaries from another project |
| `obs/_multibuild` | PG extensions only | One `<flavor>` per PostgreSQL major version |
| `package.yaml` | optional | Title/description; `build: <repo>: false` to skip a repo; `publish: <repo>: false` to suppress publishing |
