# PERCONA: tarball-only compatibility shim.  No payload, no sources.
#
# Why this package exists (finding of 2026-08-26)
# -----------------------------------------------
# The simpleimage tarball chroots (ppg:staging:NN:tarballs, repos ssl1.1 =
# Rocky 8 and ssl3 = Rocky 9) must NOT contain EPEL's fully-optioned
# gdal-libs/gdal3.4-libs or Rocky's proj: they drag ~70 surplus shared
# objects into the artifact (armadillo/BLAS, whose FlexiBLAS ELF constructor
# abort()s on Rocky hosts, plus hdf/netcdf/OPeNDAP/poppler/xerces/ODBC/
# mariadb) and have their resource directories compiled to
# /usr/share/{gdal,proj}, a path no tarball host has.  The tarball uses the
# lean /opt-prefixed percona-gdal / percona-proj from ppg:common:deps
# instead.
#
# percona-postgis35_NN's automatic soname Requires
# (libgdal.so.NN()(64bit) / libproj.so.NN()(64bit)) are a "have choice"
# between the distro packages and ours, which the project config's
# `Prefer: percona-gdal` / `Prefer: percona-proj` resolve in our favour.
# But that spec ALSO requires the distro packages BY NAME:
#
#   EL8: Requires: gdal-libs >= 3.0.4 / gdal-libs / geos proj libgeotiff
#   EL9: Requires: gdal3.4-libs >= 3.0.4 / gdal3.4-libs / geos proj libgeotiff
#
# A by-name Requires has exactly one provider, so there is no tie for
# `Prefer:` to break and the fat packages land in the chroot regardless.
# The obvious fix — a scoped `Ignore: percona-postgis35_NN:gdal-libs,proj`
# in the project config — was tried (commit b90ac24) and PROVEN NOT TO WORK
# on 2026-08-26: OBS does not apply `Ignore:` rules when expanding
# image-type recipes (the effective prjconf carried the lines; EPEL's
# gdal-libs/gdal3.4-libs and Rocky's proj were still installed, and
# build-tarball.sh section 0a FATALed as designed).  `Prefer:` IS honoured
# for image-type expansion (proven by `Prefer: hdf-libs` and by
# percona-gdal/percona-proj/percona-psql all landing in the chroot).
#
# Hence this shim: it Provides the distro NAMES itself, which turns each
# by-name Requires into a genuine have-choice that `Prefer:
# percona-gis-compat` (project config, both ssl blocks) then resolves — and
# it Requires the real percona-gdal/percona-proj so the runtimes PostGIS
# actually needs are still pulled in.
#
# Deliberately NO Conflicts:/Obsoletes: — the OBS dependency expander does
# not resolve choices via conflicts, so they would buy nothing here.
#
# proj-data / proj-datumgrid are deliberately NOT provided: nothing in the
# chroot requires them by name; they were only ever pulled in as
# dependencies of the distro `proj` package itself, which is exactly what
# this shim replaces.
#
# This package is built ONLY in this project's plain-RPM RockyLinux_8 /
# RockyLinux_9 repositories (see package.yaml, which disables ssl1.1/ssl3),
# which are unpublished and consumed solely through the same-project sibling
# repository path of each ssl repo.  That is what keeps these fake
# Provides: invisible to every other project.

Summary:        GDAL/PROJ name-compatibility shim for the binary tarball chroot
Name:           percona-gis-compat
Version:        1.0.0
Release:        1%{?dist}
License:        Apache-2.0
Group:          Development/Tools/Building
URL:            https://www.percona.com/software/postgresql-distribution
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC
BuildArch:      noarch

# The versions below MUST track root/ppg/common/deps/percona-proj/rpm/
# percona-proj.spec (%%global proj_version) and root/ppg/common/deps/
# percona-gdal/rpm/percona-gdal.spec (%%global gdal_version) for the same
# base.  PostGIS carries a VERSIONED `Requires: gdal*-libs >= 3.0.4`, so a
# Provides: below that floor would leave the chroot unresolvable.
# Nested %%if/%%else rather than %%elif: EL8 ships rpm 4.14, which has no
# %%elif (added in rpm 4.15, i.e. EL9) and fails with "Unknown tag: %%elif".
%if 0%{?rhel} == 8
# percona-proj 6.3.2, percona-gdal 3.0.4 on EL8.
Provides:       proj = 6.3.2
Provides:       gdal-libs = 3.0.4
%else
%if 0%{?rhel} == 9
# percona-proj 9.6.0, percona-gdal 3.4.3 on EL9.  The distro name is
# gdal3.4-libs here (EPEL 9's compat GDAL for PostGIS).
Provides:       proj = 9.6.0
Provides:       gdal3.4-libs = 3.4.3
%else
%{error:percona-gis-compat: unsupported base (rhel=%{?rhel}); only EL8 and EL9 tarball chroots are defined}
%endif
%endif

# The real runtimes this shim stands in for.
Requires:       percona-gdal
Requires:       percona-proj

%description
Empty compatibility package for the Percona Software for PostgreSQL binary
tarball build chroots.  It provides the distro GDAL/PROJ package names that
percona-postgis35_NN requires by name (gdal-libs/proj on EL8,
gdal3.4-libs/proj on EL9) so that the OBS dependency expander sees a choice
it can resolve — via the project config's `Prefer: percona-gis-compat` — in
favour of the lean /opt-prefixed percona-gdal / percona-proj runtimes the
tarball actually bundles, instead of installing EPEL's fully-optioned GDAL
and its ~70 surplus shared objects.

It ships no files and is never published outside the tarballs project.

%files

%changelog
* Wed Aug 26 2026 Ricardo Dias <ricardo.dias@percona.com> - 1.0.0-1
- Initial package: name-compatibility shim so Prefer: can redirect
  percona-postgis35_NN's by-name distro GDAL/PROJ Requires (prjconf
  Ignore: is not applied to image-type expansion).
