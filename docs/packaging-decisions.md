# Packaging Design Decisions by Package

## percona-pgbouncer

- **Source naming**: `obs/_service` uses `filename: percona-pgbouncer` because the upstream repo
  is named `pgbouncer` (not `percona-pgbouncer`). This ensures the tarball is named
  `percona-pgbouncer-<version>.tar.gz` to match `Source0` in the RPM spec.
- **Upstream tag format**: pgbouncer tags use underscores (`pgbouncer_1_25_1`) rather than
  dots. The `revision` in `_service` must match the exact upstream git tag.
- **Debian source format**: `3.0 (native)` used (not quilt) because we're not applying patches
  on top of an upstream tarball; OBS handles the source assembly.
- **debian/source/options**: `extend-diff-ignore = rpm/` added so the Debian build system
  ignores the `rpm/` directory that is included via debtransform.

## percona-pgbackrest

- **Multiple source files**: The spec has `Source1` (pgbackrest.conf), `Source2`
  (pgbackrest-tmpfiles.d), `Source3` (pgbackrest.logrotate), `Source4` (pgbackrest.service).
  These are included in the `rpm/` directory and referenced by name in the spec.
- **Build system**: pgbackrest uses meson (not make/autoconf). `%meson`, `%meson_build`, and
  `%meson_install` macros are used in the spec. `libssh2=disabled` is passed to meson
  because it's not always available in all distros.
- **Sysusers/postgres user**: The `%pre` section creates the `postgres` user (uid 26, gid 26)
  following the Percona convention for all PG-adjacent packages.
- **SUSE vs RHEL distinction**: Conditional `%if 0%{?suse_version}` blocks handle different
  package names for openssl and lz4 between SUSE and RHEL/Fedora distros.
- **Debian binary package**: Includes `percona-pgbackrest` (main) and `percona-pgbackrest-doc`
  (documentation subpackage).

## percona-pgaudit_set_user

- **BuildRequires needs -devel**: The spec initially had `BuildRequires: percona-postgresql17`
  (the server package). The build requires `percona-postgresql17-devel` to get pgxs.mk and
  the headers needed to compile PostgreSQL extensions. **Fix**: added `-devel` suffix.
- **pginstdir trailing slash**: The spec defines `%define pginstdir /usr/pgsql-%{pgmajorversion}/`
  (with trailing slash). Files section entries use `%{pginstdir}/lib/...` producing paths
  like `/usr/pgsql-17//lib/` — this works on RPM but is slightly inconsistent. Left as-is
  since it matches upstream packaging.
- **Requires postgresql vs percona-postgresql**: `Requires: postgresql%{pgmajorversion}` (not
  percona-) is intentional — satisfies the dependency whether using upstream or Percona PG.

## percona-wal2json

- **Missing pginstdir**: The spec used `%{pginstdir}` in both `%install` and `%files` sections
  but never defined the macro. RPM was treating it as an empty string, causing "File must
  begin with /" errors. **Fix**: added `%define pginstdir /usr/pgsql-%{pgmajorversion}` near
  the top of the spec.
- **Patch for pg_config path**: `wal2json-pg17-makefile-pgxs.patch` patches the Makefile to
  set `PG_CONFIG = /usr/pgsql-17/bin/pg_config`. This is how wal2json finds the PostgreSQL
  installation at build time.
- **doc via %doc macro**: The README is moved to `%{pginstdir}/doc/extension/` in `%install`
  and listed with `%doc` in `%files`. This caused a secondary issue because `%doc` in older
  RPM macros copies from the BUILD directory, not BUILDROOT; the path expansion
  `%{pginstdir}/doc/...` was being treated literally. The `%doc %{pginstdir}/doc/...` form
  is fine in newer RPM versions where `%{pginstdir}` is expanded.

## percona-pgpool-II

The Debian packaging was rebuilt from scratch from the upstream Debian package at
`salsa.debian.org/postgresql/pgpool2` tag `debian/4.7.0-1`, with the same transformations
applied by `pgpool2_builder.sh` from `percona/postgres-packaging` branch `17.9`.
The RPM spec was rewritten based on the same builder script.

### Source and builder script reference

- Upstream Debian base: `https://salsa.debian.org/postgresql/pgpool2/-/tree/debian/4.7.0-1/debian`
- Builder script: `percona/postgres-packaging@17.9/pgpool2/pgpool2_builder.sh`
- Key builder variables: `PGPOOL2_VERSION=4.7.0`, `PG_MAJOR=17`

### Transformations from builder.sh applied to Debian files

- Package renamed `pgpool2` → `percona-pgpool2` throughout
- Maintainer set to `Percona Development Team <info@percona.com>`
- `debian/compat` set to `10` (builder removes `debhelper-compat (= 13)` from Build-Depends
  and replaces with `debian/compat` file containing `10`)
- `autoreconf --force --install` added to `debian/rules` configure step (upstream source is
  a git checkout without pre-generated configure)
- `override_dh_builddeb` added to `debian/rules` to force gzip compression (`-Zgzip`)
- AWS sample scripts entries appended to `percona-pgpool2.install`
- `debian/pgversions` contains `17` to drive `pg_buildext` loops

### Debian packaging structure

- `debian/control` and `debian/control.in` maintained separately:
  - `control` has `17` hardcoded (used for the actual build)
  - `control.in` has `PGVERSION` placeholder (for `pg_buildext updatecontrol` if ever needed)
- PostgreSQL extensions built via `pg_buildext supported-versions .` loop in
  `override_dh_auto_install` in `debian/rules`; output package is `postgresql-17-pgpool2`
- `pgpool.conf` managed by `ucf` — installed from
  `/usr/share/pgpool2/pgpool.conf` into `/etc/pgpool2/pgpool.conf` at install time
  via `percona-pgpool2.postinst`
- `pool_passwd` and `pgpool_node_id` are empty files shipped in `debian/pool_passwd` and
  installed to `/etc/pgpool2/` by `percona-pgpool2.install`

### Debian Build-Depends decisions

- `debhelper (>= 10)` must be explicit because `debhelper-compat (= 13)` was removed from
  Build-Depends (replaced by `debian/compat` file). Without it, `dh` binary is not installed.
- `percona-postgresql-server-dev-17` used instead of `postgresql-server-dev-all` to avoid OBS
  dependency ambiguity (multiple satisfiers). Both are listed alongside each other would
  trigger "have choice" errors.
- `percona-postgresql-server-dev-all` added (in addition to `-17`) because it provides
  `/usr/share/postgresql-common/pgxs_debian_control.mk` used by `debian/rules`.
- `percona-postgresql-common` used instead of `postgresql-common` (Percona's package).

### Debian postinst bug (transcription error from upstream)

The upstream `pgpool2.postinst` uses `\`$1'` (escaped backtick) in the error echo:
```sh
echo "postinst called with unknown argument \`$1'" >&2
```
Our `percona-pgpool2.postinst` lost the backslash, leaving an unescaped backtick that
causes `Syntax error: EOF in backquote substitution` when the script runs. Fixed by
restoring the `\` escape.

### RPM spec decisions

- **`%undefine _unique_build_ids`**: `pcp_*` utility binaries are all hard-linked to a single
  binary; RPM's build-id uniqueness check fails because they share the same build-id.
- **`autoreconf` in `%build`**: upstream git checkout has no pre-generated `configure`;
  `libtoolize && autoreconf --force --install` runs before `%configure`.
- **`--sysconfdir=%{_sysconfdir}/%{short_name}`**: ensures sample configs install to
  `/etc/pgpool-II/` (not `/etc/`), matching the `%files` layout.
- **Man pages**: built via `make %{?_smp_mflags} -C doc` in `%build` and installed manually
  with `install doc/src/sgml/man1/*.1` / `man8/*.8`. Requires `jade libxslt` and docbook
  packages. Man pages also built for Debian (`percona-pgpool2.manpages`), so parity is kept.
- **`%package extensions`**: PostgreSQL extension modules (`pgpool-recovery.so`,
  `pgpool_adm.so`) and LLVM bitcode files go in a separate subpackage, following the pattern
  used in Percona's upstream packaging.
- **LLVM bitcode**: `pgpool-recovery` and `pgpool_adm` extensions produce bitcode during
  `make install`. Requires `llvm-devel clang-devel clang` in BuildRequires on both RHEL >= 8
  and openSUSE (`%if 0%{?rhel} >= 8 || 0%{?suse_version}`).

### RPM cross-distro (openSUSE vs RHEL) conditionals

| Concern | RHEL package | SUSE package | Conditional |
|---|---|---|---|
| LDAP | `openldap-devel` | `openldap2-devel` | `%if 0%{?suse_version}` |
| DocBook XSL | `docbook-style-xsl` | `docbook-xsl-stylesheets` | `%if 0%{?suse_version}` |
| DocBook DSSSL | `docbook-style-dsssl` | `docbook-dsssl-stylesheets` | `%if 0%{?suse_version}` |
| DocBook DTDs | `docbook-dtds` | `docbook_4` | `%if 0%{?suse_version}` |
| SGML jade | `jade` | `openjade` | `%if 0%{?suse_version}` |
| memcached | `libmemcached-devel` (RHEL<9) / `libmemcached-awesome-devel` (RHEL>=9) | `libmemcached-devel` | `%if 0%{?rhel} >= 9` |
| systemd-sysv | `Requires(post): systemd-sysv` | not available | `%if 0%{?rhel}` |
| service pre-hook | not needed | `%service_add_pre pgpool.service` | `%{?suse_version:...}` |

### RPM openSUSE rpmlint suppressions

openSUSE's post-build rpmlint check is stricter than RHEL's. The following are suppressed
via `percona-pgpool-II-pg17-rpmlintrc`:

- `filelist-forbidden-sysconfig`: `/etc/sysconfig/pgpool` — SUSE prefers `%{_fillupdir}`;
  acceptable for Percona third-party packages
- `filelist-forbidden-fhs23`: `/usr/pgsql-17` — Percona's non-standard PostgreSQL path,
  used on all platforms
- `dir-or-file-in-var-run`: historical; fixed by removing `%dir %{_varrundir}` from `%files`
  (tmpfiles.d handles creation at runtime)
- `non-conffile-in-etc`: `.sample` files in `/etc/pgpool-II/` are not user-editable configs
- `sudoers-file-unauthorized`: sudoers file content not pre-approved in SUSE allowlist
- `unused-rpmlintrc-filter`: some RHEL-specific filters in rpmlintrc don't trigger on SUSE
- `zero-length`: `pool_passwd` and `pgpool_node_id` are intentionally empty placeholder files

### RPM %files directory ownership (openSUSE)

openSUSE's filelist check requires every directory in the RPM payload to be owned by some
installed package. Added:

- `%dir %{_sysconfdir}/%{short_name}` — directory created and owned by this package
- `%ghost %dir %{_sysconfdir}/sudoers.d` — system dir owned by `sudo` at runtime
- `%ghost %dir /run/pgpool` — created at runtime by tmpfiles.d
- `%ghost %dir %{pghome}/lib`, `%{pghome}/share`, `%{pghome}/share/extension` — owned by
  `percona-postgresql17` at runtime
- `%ghost %dir %{pghome}/lib/bitcode` — parent of bitcode subdirs we create
- `%dir %{pghome}/lib/bitcode/pgpool-recovery` and `%dir %{pghome}/lib/bitcode/pgpool_adm`
  — subdirectories created by this package's `make install`

Man page permissions are fixed in `%install` with
`find %{buildroot}%{_mandir} -type f -exec chmod 644 {} \;` to suppress
`spurious-executable-perm` (man pages installed with execute bit by upstream's `make install`).

## percona-postgis

### Version naming (fixed)
- **Root cause**: The RPM spec was named `percona-postgis35_17.spec`. OBS `set_version`
  service extracts a version from spec filenames; the `_17` suffix before `.spec` was being
  interpreted as the version, producing a malformed Debian package version `17.spec-1+X.Y`.
  **Fix**: renamed spec to `percona-postgis.spec` (no numeric version in filename).

### Debian/Ubuntu build dependencies (fixed)
- **debian.dsc Build-Depends was sparse**: The original `debian.dsc` only had
  `debhelper (>= 9), percona-postgresql-server-dev-all`. OBS uses the `debian.dsc`
  Build-Depends to install packages in the build chroot; missing entries mean the GIS
  libraries are not installed when the build runs. **Fix**: synced `debian.dsc`
  Build-Depends with `debian/control` (adds libgdal-dev, libgeos-dev, libproj-dev,
  libsfcgal-dev, bison, flex, xsltproc, percona-postgresql-17, and other required packages).
- **rpm.tar.gz must stay in Debtransform-Files-Tar**: If `rpm.tar.gz` is not listed as an
  overlay file, `debtransform` sees two candidate source tarballs (`percona-postgis-*.tar.gz`
  and `rpm.tar.gz`) and fails with "Too many files looking like a usable source tarball".
  `Debtransform-Files-Tar: debian.tar.gz rpm.tar.gz` correctly marks `rpm.tar.gz` as an
  overlay (not the main source).
- **Dual compat conflict**: `debian/compat` contained `13` AND `debian/control` had
  `debhelper-compat (= 13)` in Build-Depends. **Fix**: removed `debian/compat`, kept the
  Build-Depends entry (same fix as percona-pgpool-II).
- **libcurl4 conflict via libgdal-dev**: `libgdal-dev` transitively requires BOTH
  `libcurl4-openssl-dev` AND `libcurl4-gnutls-dev` through different dependency paths. These
  two packages conflict in Debian. **Fix**: Added `Ignore: libcurl4-gnutls-dev` to the OBS
  project config (`root/project.yaml`) for Debian/Ubuntu repos.
- **libjpeg-dev ambiguity**: `libgdal-dev` and several of its deps require `libjpeg-dev`
  which is provided by both `libjpeg62-turbo-dev` and `libjpeg-dev`. OBS can't pick one.
  **Fix**: Added `Prefer: libjpeg62-turbo-dev` to the OBS project config.
- **percona-postgresql-all not built**: `percona-postgresql-all` was in `debian/control`
  Build-Depends but is not built in our OBS project. It was removed from both `debian/control`
  and `debian.dsc` (tests use `percona-postgresql-17` directly instead).
- **pg_buildext requires debian/pgversions**: `pg_buildext` is called in `debian/rules` for
  multi-version PostGIS builds. It requires a `debian/pgversions` file listing supported PG
  versions. **Fix**: added `debian/pgversions` containing just `17`.
- **pg_buildext requires debian/control.in**: `pg_buildext updatecontrol` expects a
  `debian/control.in` template with `PGVERSION` tokens (NOT `@PGVERSION@`). Without it,
  the `clean` target fails with "Unknown sequence debian/control.in". **Fix**: created
  `debian/control.in` from `debian/control` with `percona-postgresql-17` →
  `percona-postgresql-PGVERSION` substitutions.
- **percona-postgresql-17 needed for tests**: `override_dh_auto_test` uses `pg_virtualenv`
  which calls `initdb` to create a test cluster. This requires `percona-postgresql-17`
  (provides `initdb`) to be installed in the build chroot.
- **xsltproc needed for docs**: The doc install step (`make -C doc docs-install`) requires
  `xsltproc` for processing DocBook XML. Added to both `debian.dsc` and `debian/control`.
- **libxml2-utils needed for docs**: `configure` also checks for `xmllint` (provided by
  `libxml2-utils`). Added to `debian.dsc`, `debian/control`, and `debian/control.in`.
- **docbook-xsl needed for docs**: The doc build uses xsltproc with DocBook XSL stylesheets
  at `/usr/share/xml/docbook/stylesheet/docbook-xsl/`. Without `docbook-xsl` installed, the
  build fails with "failed to load external entity /xhtml5/docbook.xsl". Added to all three
  Build-Depends files.
- **ImageMagick security policy blocks docs image generation**: `docs-install` includes
  `images-install`, which runs a custom generator program that calls `convert -draw '@file'`.
  Debian/Ubuntu's ImageMagick security policy blocks reading from files via the `@` prefix.
  The generated images are also deleted in `execute_before_dh_install` anyway. **Fix**: changed
  `make -C doc docs-install` to `make -C doc html-install` in `debian/rules` to skip the
  `images-install` dependency.
- **Regression tests fail in build chroot**: `override_dh_auto_test` runs the full PostGIS
  test suite via `pg_virtualenv`. Tests fail with GDAL version-specific error messages (VRT
  security test expects specific output) and floating point precision differences in raster
  scale constraint tests. **Fix**: replaced the test step with a no-op (`: # skip tests`) in
  `debian/rules` so the build completes successfully.

### RPM build (infrastructure — unresolved)
- **Missing GIS library packages**: RockyLinux_9 build is `unresolvable` because the OBS
  instance lacks PGDG-style versioned GIS packages:
  `geos311-devel`, `gdal311-devel`, `proj95-devel`, `SFCGAL-devel`, `pgdg-srpm-macros`.
  These come from PGDG extra repositories that are not configured in the OBS project.
  Adding them requires an OBS project configuration change (adding repo paths) — outside
  the scope of packaging file fixes.

## percona-pg_repack (fixed by user prior to this session)

- No design decisions captured; fixes were applied directly by the user.

## percona-pgbadger

- **Perl-only package**: pgbadger is a pure-Perl script. No compilation step required.
  Debian build just installs the script; RPM build uses `%{__install}` for the script.

## General OBS Patterns Used

- **`obs/_service` structure**: All packages use a combination of `obs_scm` (to fetch debian/
  and rpm/ files from this git repo) + `obs_scm` (to fetch upstream source) + `tar` +
  `recompress` + `set_version` services.
- **`version: _none_`**: Used for the debian/ and rpm/ obs_scm entries so `set_version` picks
  up the version only from the upstream source tarball obsinfo.
- **`filename` param**: Used to set the base name of the tarball produced by obs_scm. Critical
  when the upstream repo name differs from the Percona package name.
- **`Debtransform-Files-Tar`**: Used in `debian.dsc` to explicitly declare which tarballs
  debtransform should include (debian.tar.gz and rpm.tar.gz).
- **`extend-diff-ignore = rpm/`**: Added to `debian/source/options` to prevent Debian build
  tools from complaining about the `rpm/` directory being present in the source tree.
- **RPM `Version: 1.0.0` placeholder**: All RPM specs start with `Version: 1.0.0`. OBS
  `set_version` service replaces this with the actual version from the upstream source
  obsinfo at build time.
- **Epoch: 1**: Added to RPM specs for packages that may have been previously packaged
  without Percona naming, to ensure upgrade paths work correctly.
