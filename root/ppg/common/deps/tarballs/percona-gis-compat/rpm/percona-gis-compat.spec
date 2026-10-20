# PERCONA: tarball-only compatibility shim.  No payload, no sources.
#
# Why this package exists (finding of 2026-08-26)
# -----------------------------------------------
# The simpleimage tarball chroots (ppg:staging:NN:tarballs, repos ssl1.1 =
# Rocky 8, ssl3 = Rocky 9.6, ssl3.5 = Rocky 9) must NOT contain the
# fully-optioned PGDG-mirrored GDAL/PROJ that PostGIS links on user systems
# (gdal38-libs/gdal313-libs, proj96/proj98, libgeotiff17 from
# ppg:common:deps:postgis, aggregated into ppg:staging:NN): the GDAL with
# every driver drags dozens of surplus shared objects into the artifact
# (the armadillo/BLAS chain, whose FlexiBLAS ELF constructor abort()s on
# Rocky hosts, plus hdf/netcdf/poppler/xerces/ODBC/...) and both have their
# resource directories compiled to /usr/<name>/share, a path no tarball
# host has.  The tarball uses the lean /opt-prefixed percona-gdal /
# percona-proj from ppg:common:deps:tarballs instead.
#
# percona-postgis<MAJOR>_NN's automatic soname Requires
# (libgdal.so.NN()(64bit) / libproj.so.NN()(64bit)) are a "have choice"
# between the PGDG-mirrored packages and ours, which the project config's
# `Prefer: percona-gdal` / `Prefer: percona-proj` resolve in our favour.
# But that spec ALSO requires them BY NAME (rpmspec -q --requires, every
# PG major):
#
#   EL8: gdal38-libs >= 3.8.5, proj96 >= 9.6.2, geos315 >= 3.15.0, libgeotiff17
#   EL9: gdal313-libs >= 3.13.3, proj98 >= 9.8.1, geos315 >= 3.15.0, libgeotiff17
#
# A by-name Requires has exactly one provider, so there is no tie for
# `Prefer:` to break and the fat packages land in the chroot regardless.
# The obvious fix — a scoped `Ignore: percona-postgis35_NN:gdal-libs,proj`
# in the project config — was tried (commit b90ac24) and PROVEN NOT TO WORK
# on 2026-08-26: OBS does not apply `Ignore:` rules when expanding
# image-type recipes (the effective prjconf carried the lines; the then
# EPEL GDAL (EL8 and EL9 compat names) and Rocky's proj were installed, and
# build-tarball.sh section 0a FATALed as designed).  `Prefer:` IS honoured
# for image-type expansion (proven by `Prefer: hdf-libs` and by
# percona-gdal/percona-proj/percona-psql all landing in the chroot).
#
# Hence this shim: it Provides those NAMES itself, which turns each
# by-name Requires into a genuine have-choice that `Prefer:
# percona-gis-compat` (project config, every ssl block) then resolves — and
# it Requires the real percona-gdal/percona-proj so the runtimes PostGIS
# actually needs are still pulled in.
#
# libgeotiff17 is provided because percona-gdal uses GDAL's bundled
# libgeotiff: nothing in the tarball links the real one.  geos315 is NOT
# provided: the real geos315 package is what the tarball bundles (its
# libgeos_c is what PostGIS and percona-gdal link), so the shim Requires it
# instead.  libspatialite50 is not provided either: PostGIS does not require
# it by name, and percona-gdal does not use SpatiaLite.
#
# Deliberately NO Conflicts:/Obsoletes: — the OBS dependency expander does
# not resolve choices via conflicts, so they would buy nothing here.
#
# proj-data / proj-datumgrid are deliberately NOT provided: nothing in the
# chroot requires them by name; they were only ever pulled in as
# dependencies of the distro `proj` package the first version of this shim
# replaced.
#
# This package is built ONLY in ppg:common:deps:tarballs, an unpublished
# subproject whose repos are pathed solely by the ssl* tarball repos.  That
# is what keeps these fake Provides: invisible to every other project.

Summary:        GDAL/PROJ name-compatibility shim for the binary tarball chroot
Name:           percona-gis-compat
Version:        1.0.0
Release:        2%{?dist}
License:        Apache-2.0
Group:          Development/Tools/Building
URL:            https://www.percona.com/software/postgresql-distribution
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC
BuildArch:      noarch

# The names and versions come from the same root/macros.yaml GIS_* macros
# as the PGDG-mirrored packages, percona-proj and percona-gdal, so they move
# together.  PostGIS carries VERSIONED by-name Requires (`gdal313-libs >=
# 3.13.3`, ...), so a Provides: below that floor would leave the chroot
# unresolvable.
# Nested %%if/%%else rather than %%elif: EL8 ships rpm 4.14, which has no
# %%elif (added in rpm 4.15, i.e. EL9) and fails with "Unknown tag: %%elif".
%if 0%{?rhel} == 8
# proj96 / gdal38-libs on EL8 (percona-proj and percona-gdal build the
# same versions there).
Provides:       proj%!{GIS_PROJ_EL8_MAJOR} = %!{GIS_PROJ_EL8_VERSION}
Provides:       gdal%!{GIS_GDAL_EL8_MAJOR}-libs = %!{GIS_GDAL_EL8_VERSION}
%else
%if 0%{?rhel} == 9
# proj98 / gdal313-libs on EL9 (ssl3 and ssl3.5).
Provides:       proj%!{GIS_PROJ_MAJOR} = %!{GIS_PROJ_VERSION}
Provides:       gdal%!{GIS_GDAL_MAJOR}-libs = %!{GIS_GDAL_VERSION}
%else
%{error:percona-gis-compat: unsupported base (rhel=%{?rhel}); only EL8 and EL9 tarball chroots are defined}
%endif
%endif

Provides:       libgeotiff17 = %!{GIS_LIBGEOTIFF_VERSION}

# The real runtimes this shim stands in for, plus the real geos315 that the
# tarball bundles as-is.
%if 0%{?rhel} == 8
Requires:       percona-gdal%!{GIS_GDAL_EL8_MAJOR}
Requires:       percona-proj%!{GIS_PROJ_EL8_MAJOR}
%else
Requires:       percona-gdal%!{GIS_GDAL_MAJOR}
Requires:       percona-proj%!{GIS_PROJ_MAJOR}
%endif
Requires:       geos%!{GIS_GEOS_MAJOR}

%description
Empty compatibility package for the Percona Software for PostgreSQL binary
tarball build chroots.  It provides the PGDG-mirrored GDAL/PROJ/libgeotiff
package names that percona-postgis<MAJOR>_NN requires by name (gdal38-libs,
proj96 and libgeotiff17 on EL8; gdal313-libs, proj98 and libgeotiff17 on
EL9) so that the OBS dependency expander sees a choice it can resolve — via
the project config's `Prefer: percona-gis-compat` — in favour of the lean
/opt-prefixed percona-gdal / percona-proj runtimes the tarball actually
bundles, instead of installing the fully-optioned GDAL and its surplus
shared objects.

It ships no files and is never published outside the tarballs project.

%files

%changelog
* Sun Oct 18 2026 Percona Development <info@percona.com> - 1.0.0-2
- Provide the PGDG-mirrored names PostGIS now requires: proj96 and
  gdal38-libs on EL8, proj98 and gdal313-libs on EL9, libgeotiff17 on
  both (versions from root/macros.yaml); drop the old EPEL/Rocky proj
  and GDAL names. Require the real geos315, which the tarball bundles.

* Wed Aug 26 2026 Ricardo Dias <ricardo.dias@percona.com> - 1.0.0-1
- Initial package: name-compatibility shim so Prefer: can redirect
  percona-postgis35_NN's by-name distro GDAL/PROJ Requires (prjconf
  Ignore: is not applied to image-type expansion).
