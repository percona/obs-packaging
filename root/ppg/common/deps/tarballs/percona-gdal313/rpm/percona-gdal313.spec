# PERCONA PACKAGE for ppg:common:deps:tarballs (RockyLinux_8, RockyLinux_9.6, RockyLinux_9).
#
# /opt-prefixed GDAL runtime consumed by the Percona PostgreSQL binary
# tarball (2026-07 tarball QA round, task 22).
#
# Why this exists: the tarball bundles the RPM-built postgis_raster.so,
# which links libgdal.so.NN, so the tarball has to carry a libgdal. Using
# EPEL's was a disaster on two counts:
#
#   1. EPEL builds GDAL with every optional driver enabled, so libgdal
#      drags ~70 surplus shared objects into the tarball (armadillo,
#      poppler, hdf4/hdf5, netcdf, OPeNDAP, xerces, libkml, unixODBC,
#      mariadb, cfitsio, ogdi, jasper/openjpeg, ...). Among them is a
#      BLAS/LAPACK chain via armadillo whose FlexiBLAS ELF constructor
#      abort()s on Rocky hosts because its dlopen'ed backend plugin is
#      not (and cannot sanely be) bundled, and it pulls libtirpc /
#      libexpat / libpcre2-posix which minimal target hosts lack.
#   2. EPEL's libgdal has its data directory compiled to /usr/share/gdal,
#      a path that does not exist on the tarball's target hosts.
#
# This package builds GDAL from source with the prefix /opt/percona-gdal
# and exactly the external libraries the OFFICIAL Percona tarball's libgdal
# links (derived from `readelf -d` on the official artifact's
# libgdal.so.36) and every other external library off
# (GDAL_USE_EXTERNAL_LIBS=OFF). All built-in drivers are compiled, as the
# autotools build did; the ones that need a library outside that set are
# left out by GDAL's CMake (see %%build). Two deliberate departures from that list: libgeotiff is GDAL's
# bundled copy (no libgeotiff17 in the tarball) and libspatialite is not
# used at all. The data directory is compiled to
# /opt/percona-gdal/share/gdal, so GDAL finds its resource files with ZERO
# environment variables, and PROJ comes from percona-proj, whose proj.db
# likewise resolves from a compiled-in path. GEOS is the PGDG-mirrored
# geos315 (/usr/geos315) that PostGIS links too; the tarball bundles it.
#
# Version is per base and follows the PGDG-mirrored GDAL that the shipped
# PostGIS RPMs link on that base (ppg:common:deps:postgis gdal38/gdal313,
# root/macros.yaml GIS_GDAL_*) — the tarball just substitutes the bundled
# file, so ours must be a drop-in:
#
#     RHEL 8 (ssl1.1 tarball):       GDAL 3.8.5  (gdal38)  -> libgdal.so.34
#     RHEL 9 (ssl3/ssl3.5 tarballs): GDAL 3.13.3 (gdal313) -> libgdal.so.39
#
# We deliberately do NOT filter the auto-generated
# libgdal.so.NN()(64bit) Provides: the ssl chroots that assemble the
# tarball use a project-config `Prefer:` to let this package satisfy
# PostGIS's SONAME Requires instead of gdal38-libs/gdal313-libs. Everything
# installs under /opt/percona-gdal, so nothing shadows a system package
# on a normal install, and ppg:common:deps is publish=false project-wide.

%global gdal_prefix /opt/percona-gdal
%global proj_prefix /opt/percona-proj

# PERCONA: no link-time optimization. RHEL 9's %%optflags carry -flto=auto,
# and libgdal is big enough that the final link degenerates into
# "lto-wrapper: using serial compilation of 128 LTRANS jobs" — minutes of
# single-threaded work that risks an OBS build timeout for no benefit.
# Upstream does not enable LTO by default either. (RHEL 8's optflags do
# not enable LTO, so this is a no-op there.)
%global _lto_cflags %{nil}

# PERCONA: one package per tarball base (percona-gdal38: RHEL 8,
# percona-gdal313: RHEL 9), each with a single upstream version.
%global gdal_version %!{GIS_GDAL_VERSION}
%global gdal_soname 39
# GDAL's CMake build installs the resource files to, and compiles INST_DATA
# as, <prefix>/<CMAKE_INSTALL_DATADIR>/gdal (gdal.cmake sets
# GDAL_RESOURCE_PATH itself, so it cannot be overridden from the command
# line). CMAKE_INSTALL_DATADIR=share below makes that this path.
%global gdal_datadir %{gdal_prefix}/share/gdal
# geos315 from ppg:common:deps:postgis, the GEOS PostGIS links.
%global geos_prefix /usr/geos315

Name:           percona-gdal%!{GIS_GDAL_MAJOR}
Version:        %{gdal_version}
Release:        1%{?dist}
Summary:        GDAL runtime under /opt/percona-gdal for the Percona PostgreSQL binary tarball
License:        MIT
URL:            https://gdal.org/
Source0:        gdal-%!{GIS_GDAL_VERSION}.tar.xz

# PERCONA: an EXPLICIT dependency on our own PROJ, not just the automatic
# libproj.so.NN()(64bit) ELF requires. That auto-requires is ambiguous:
# proj96/proj98 (and EPEL's proj-libs on EL9) provide the very same
# libproj.so.25 symbol, so a plain `dnf install percona-gdal` could
# satisfy it with one of those, leaving
# /opt/percona-proj/lib absent, libgdal's rpath dead and the whole
# compiled-in-data-path mechanism broken. The point of this package is
# *our* libproj, not any libproj with a matching SONAME.
Requires:       percona-proj%!{GIS_PROJ_MAJOR}

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  cmake >= 3.16
# PERCONA: our own /opt PROJ — same SONAME as the libproj PostGIS linked,
# with the data path compiled to /opt/percona-proj/share/proj.
BuildRequires:  percona-proj%!{GIS_PROJ_MAJOR}
# The driver set, one BuildRequires per NEEDED entry of the official
# tarball's libgdal (see the header comment). libgeotiff is GDAL's bundled
# copy (GDAL_USE_GEOTIFF_INTERNAL) and libspatialite is not used, so
# no libgeotiff or libspatialite development package is needed here.
BuildRequires:  zlib-devel
BuildRequires:  libcurl-devel
BuildRequires:  libxml2-devel
BuildRequires:  openssl-devel
BuildRequires:  libzstd-devel
BuildRequires:  xz-devel
BuildRequires:  libjpeg-turbo-devel
BuildRequires:  libtiff-devel
BuildRequires:  libpng-devel
BuildRequires:  sqlite-devel
BuildRequires:  freexl-devel
BuildRequires:  expat-devel
# PERCONA: the PGDG-mirrored GEOS PostGIS links (ppg:common:deps:postgis),
# under /usr/geos315. Its package ships geos-config and geos_c.h but no
# CMake config, so GDAL's FindGEOS finds it through CMAKE_PREFIX_PATH.
BuildRequires:  geos315-devel
BuildRequires:  json-c-devel
BuildRequires:  pcre2-devel
BuildRequires:  lz4-devel

%description
GDAL %{version} built from the upstream source with the prefix
/opt/percona-gdal and only the external libraries the official Percona PostgreSQL
tarball's libgdal links, so the binary tarball carries a handful of
shared objects instead of the ~70 that EPEL's fully-optioned gdal-libs
drags in. The GDAL data directory is compiled to
/opt/percona-gdal/share/gdal and PROJ comes from percona-proj, so both
resolve their resource files without any environment variables. This is the
RHEL 9 build: its SONAME (libgdal.so.39) matches the libgdal
of gdal313 that the shipped PostGIS RPMs link, making it a drop-in
replacement inside the tarball. Consumed by the
tarball build; not intended for standalone installation.

%prep
%setup -q -n gdal-%{version}

%build
# PERCONA: plain cmake, not %%cmake — the distro macro forces /usr + lib64
# (and on EL8 CMAKE_SKIP_RPATH=ON), and we need a self-contained /opt tree
# with our own RUNPATH.
#
# RUNPATH (CMAKE_INSTALL_RPATH, a CMake ;-list; bindings are off, so no
#   Python build consumes it):
#   %%{proj_prefix}/lib — our libproj, in the RPM install layout.
#   $ORIGIN — libgdal's own directory, for the tarball, which flattens
#     libproj/libgeos_c into the same lib/ dir as libgdal. Not redundant:
#     postgis_raster-3.so's own RUNPATH does NOT help here, because
#     DT_RUNPATH is not inherited down the load chain — it applies only to
#     that object's own NEEDED entries.
#   %%{geos_prefix}/lib64 — geos315's libgeos_c, in the RPM install layout.
#   The tarball's build-tarball.sh rewrites all of this to $ORIGIN/../lib
#   once it has bundled the libraries.
# CMAKE_INSTALL_DATADIR=share: GDAL compiles INST_DATA as
#   <prefix>/share/gdal (see %%{gdal_datadir} above), so the resource files
#   (gdalicon.png, the .csv/.json tables, ...) are found with no GDAL_DATA
#   in the environment.
# CMAKE_PREFIX_PATH: our /opt PROJ (its CMake config, never a distro PROJ)
#   and geos315's geos-config/headers/library.
# GDAL_USE_EXTERNAL_LIBS=OFF: every external library is off unless named
#   below — the CMake form of the autotools build's long --without- list
#   (armadillo, the one that drags the FlexiBLAS/BLAS/LAPACK chain whose
#   ELF constructor abort()s on Rocky hosts, hdf4/5, netcdf, poppler,
#   xerces, libkml, ODBC, mysql, openjpeg, webp, PostgreSQL, ...).
#   GDAL_USE_<X>=ON then makes a missing library fatal instead of silently
#   dropping it. GDAL_USE_POSTGRESQL=OFF is spelled out anyway: the tarball
#   build never had the PostgreSQL driver (--without-pg).
# Internal copies: libgeotiff (GDAL_USE_GEOTIFF_INTERNAL, so libgeotiff17
#   does not enter the tarball), qhull and gif (as --with-qhull/gif=internal
#   did). zlib/tiff/png/jpeg/json-c
#   are the system libraries (GDAL_USE_*_INTERNAL default to OFF when the
#   external one is ON), as the old --with-<lib>=/usr forced.
# Drivers: GDAL_BUILD_OPTIONAL_DRIVERS/OGR_BUILD_OPTIONAL_DRIVERS=ON keep
#   the driver set of the autotools build, which compiled every built-in
#   driver. That does not widen the library set: a driver that needs an
#   external library is declared with gdal_dependent_format /
#   ogr_dependent_driver (cmake/helpers/GdalDriverHelper.cmake), whose
#   cmake_dependent_option forces GDAL_ENABLE_DRIVER_<X> / OGR_ENABLE_DRIVER_<X>
#   OFF unless its GDAL_USE_<LIB> condition holds, and every GDAL_USE_<LIB>
#   outside the list below is OFF through GDAL_USE_EXTERNAL_LIBS=OFF. No
#   driver is named here, so check_depend_condition never has a user-set
#   driver to fail on.
# GDAL_USE_ICONV=ON: glibc's iconv, which the autotools build picked up by
#   default (CPLRecode); no extra library.
# GDAL_HIDE_INTERNAL_SYMBOLS=ON: upstream's default, as
#   --with-hide-internal-symbols; keeps libgdal from re-exporting the
#   bundled geotiff/qhull symbols.
# BUILD_APPS=OFF: the CLI tools never reach the tarball (build-tarball.sh
#   deletes bin/).
mkdir -p build
cd build
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=%{gdal_prefix} \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_INSTALL_DATADIR=share \
    -DCMAKE_C_FLAGS="%{optflags}" \
    -DCMAKE_CXX_FLAGS="%{optflags}" \
    -DCMAKE_SHARED_LINKER_FLAGS="%{?__global_ldflags}" \
    -DCMAKE_INSTALL_RPATH='%{gdal_prefix}/lib;%{proj_prefix}/lib;$ORIGIN;%{geos_prefix}/lib64' \
    -DCMAKE_PREFIX_PATH="%{proj_prefix};%{geos_prefix}" \
    -DPROJ_ROOT=%{proj_prefix} \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_APPS=OFF \
    -DBUILD_TESTING=OFF \
    -DBUILD_PYTHON_BINDINGS=OFF \
    -DBUILD_JAVA_BINDINGS=OFF \
    -DBUILD_CSHARP_BINDINGS=OFF \
    -DGDAL_HIDE_INTERNAL_SYMBOLS=ON \
    -DGDAL_USE_EXTERNAL_LIBS=OFF \
    -DGDAL_BUILD_OPTIONAL_DRIVERS=ON \
    -DOGR_BUILD_OPTIONAL_DRIVERS=ON \
    -DGDAL_USE_GEOTIFF_INTERNAL=ON \
    -DGDAL_USE_TIFF_INTERNAL=OFF \
    -DGDAL_USE_QHULL_INTERNAL=ON \
    -DGDAL_USE_GIF_INTERNAL=ON \
    -DGDAL_USE_ZLIB=ON \
    -DGDAL_USE_CURL=ON \
    -DGDAL_USE_LIBXML2=ON \
    -DGDAL_USE_OPENSSL=ON \
    -DGDAL_USE_ZSTD=ON \
    -DGDAL_USE_LIBLZMA=ON \
    -DGDAL_USE_JPEG=ON \
    -DGDAL_USE_TIFF=ON \
    -DGDAL_USE_PNG=ON \
    -DGDAL_USE_SQLITE3=ON \
    -DGDAL_USE_FREEXL=ON \
    -DGDAL_USE_EXPAT=ON \
    -DGDAL_USE_JSONC=ON \
    -DGDAL_USE_GEOS=ON \
    -DGDAL_USE_ICONV=ON \
    -DGDAL_USE_PCRE2=ON \
    -DGDAL_USE_LZ4=ON \
    -DGDAL_USE_SPATIALITE=OFF \
    -DGDAL_USE_POSTGRESQL=OFF

make %{?_smp_mflags}

%install
make -C build install DESTDIR=%{buildroot}

# PERCONA: hard gates on the three properties this package exists for.
#
# 1. SONAME parity. The package is only useful as a drop-in for the libgdal
#    the shipped PostGIS RPMs linked against, so assert the SONAME we
#    promised for this base actually came out. Without this, a source-URL
#    bump — or this package being built on the wrong base — would silently
#    produce a library that is
#    no longer ABI-compatible with postgis_raster.
test -e %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname}
# 2. The compiled-in data path. The resource files must actually BE in the
#    directory libgdal was told about: GDAL also carries an independent
#    <prefix>/share/gdal fallback string, so grepping the library alone
#    would pass even with a wrong data dir. The third test catches a
#    <prefix>/share/gdal/gdal doubling (what GDAL 3.4.3's autotools build
#    produced with --datadir=<prefix>/share/gdal).
grep -q '%{gdal_datadir}' %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname}
test -s %{buildroot}%{gdal_datadir}/gdalicon.png
test ! -d %{buildroot}%{gdal_datadir}/gdal
# 3. A driver surface with none of the libraries the official tarball's
#    libgdal does without. libgeotiff and libspatialite joined the list
#    with the CMake build: geotiff is GDAL's bundled copy and spatialite
#    is off, so a NEEDED entry for either means the configuration slipped
#    (and would drag libgeotiff17/libspatialite50 into the tarball).
for bad in libarmadillo libflexiblas libpoppler libhdf5 libmfhdf libnetcdf \
           libdap libxerces libkmlbase libodbc libmariadb libcfitsio libogdi \
           libjasper libopenjp2 libtirpc libwebp libgta libpq \
           libgeotiff libspatialite; do
    if readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname} | grep -q "$bad"; then
        echo "ERROR: libgdal links $bad — driver set is not lean" >&2
        exit 1
    fi
done
# 4. The two GIS libraries libgdal must take from the right place: our
#    /opt PROJ (libproj.so.25) and geos315's libgeos_c, each reachable
#    through libgdal's own RUNPATH.
readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname} | grep -q 'NEEDED.*\[libproj\.so\.25\]'
readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname} | grep -q 'NEEDED.*\[libgeos_c\.so\.1\]'
readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname} | grep -E '\((RUNPATH|RPATH)\)' | grep -q '%{proj_prefix}/lib'
readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.%{gdal_soname} | grep -E '\((RUNPATH|RPATH)\)' | grep -q '%{geos_prefix}/lib64'

%files
%license LICENSE.TXT
%{gdal_prefix}

%changelog
* Tue Oct 20 2026 Percona Development <info@percona.com> - %{version}-%{release}
- Split percona-gdal into one package per tarball base so each OBS
  package builds a single version: percona-gdal38 (RHEL 8, GDAL 3.8.5)
  and percona-gdal313 (RHEL 9, GDAL 3.13.3). Install prefix unchanged.

* Sun Oct 18 2026 Percona Development <info@percona.com> - %{version}-%{release}
- Follow the PGDG-mirrored GDAL that PostGIS now links: 3.8.5 on RHEL 8
  (gdal38, libgdal.so.34) and 3.13.3 on RHEL 9 (gdal313,
  libgdal.so.39), versions from root/macros.yaml.
- Build with CMake (GDAL dropped autotools in 3.6): same external
  library set, every other one off; all built-in drivers, as before.
- GDAL's bundled libgeotiff instead of the system one, no
  libspatialite, GEOS from geos315 (/usr/geos315).

* Wed Sep 02 2026 Percona Build/Release Team <eng-build@percona.com> - %{version}-%{release}
- Drop ExcludeArch aarch64: the binary tarball (ppg:staging:NN:tarballs)
  now builds for aarch64 too, so this runtime is no longer dead weight
  on that arch.

* Tue Aug 25 2026 Percona Build/Release Team <eng-build@percona.com> - %{version}-%{release}
- Initial /opt/percona-gdal runtime for the Percona PostgreSQL binary
  tarball: GDAL 3.0.4 on RHEL 8 (libgdal.so.26) and GDAL 3.4.3 on
  RHEL 9 (libgdal.so.30), restricted to the official tarball's driver
  set (no armadillo/FlexiBLAS, hdf, netcdf, OPeNDAP, poppler, xerces,
  libkml, ODBC, mariadb, ...) and with the GDAL data directory compiled
  to /opt/percona-gdal/share/gdal (tarball QA task 22).
