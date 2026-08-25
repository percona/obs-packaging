# PERCONA PACKAGE for ppg:common:deps (RockyLinux_8 and RockyLinux_9 only).
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
# and exactly the driver set the OFFICIAL Percona tarball's libgdal links
# (derived from `readelf -d` on the official artifact's libgdal.so.36),
# with an explicit --without- for everything else. The data directory is
# compiled to /opt/percona-gdal/share/gdal, so GDAL finds its resource
# files with ZERO environment variables, and PROJ comes from
# percona-proj, whose proj.db likewise resolves from a compiled-in path.
#
# Version is per base, chosen so the SONAME matches the libgdal that the
# shipped PostGIS RPMs were linked against on that base — the tarball
# just substitutes the bundled file, so ours must be a drop-in:
#
#     RHEL 8 (ssl1.1 tarball): GDAL 3.0.4 -> libgdal.so.26
#     RHEL 9 (ssl3   tarball): GDAL 3.4.3 -> libgdal.so.30
#
# (both verified against the libgdal.so.* real filenames in the built
# tarball artifacts: libgdal.so.26.0.4 and libgdal.so.30.0.3).
#
# We deliberately do NOT filter the auto-generated
# libgdal.so.NN()(64bit) Provides: the ssl chroots that assemble the
# tarball use a project-config `Prefer:` to let this package satisfy
# PostGIS's SONAME Requires instead of EPEL's gdal-libs. Everything
# installs under /opt/percona-gdal, so nothing shadows a system package
# on a normal install, and ppg:common:deps is publish=false project-wide.

%global gdal_prefix /opt/percona-gdal
%global proj_prefix /opt/percona-proj

# PERCONA: no link-time optimization. RHEL 9's %%optflags carry -flto=auto,
# and libgdal is big enough that the final link degenerates into
# "lto-wrapper: using serial compilation of 128 LTRANS jobs" — minutes of
# single-threaded work that risks an OBS build timeout for no benefit.
# Upstream's own --enable-lto is off by default and the autotools build is
# not LTO-tested. (RHEL 8's optflags do not enable LTO, so this is a no-op
# there.)
%global _lto_cflags %{nil}

# PERCONA: base-specific upstream version + which Source to unpack.
%if 0%{?rhel} == 8
%global gdal_version 3.0.4
%global gdal_srcidx 0
# GDAL 3.0.4 uses --datadir verbatim as the GDAL data dir.
%global gdal_datadir %{gdal_prefix}/share/gdal
%else
%global gdal_version 3.4.3
%global gdal_srcidx 1
# GDAL 3.4.3 APPENDS "/gdal" to --datadir (3.0.4 does not), so passing
# <prefix>/share/gdal here would install to — and compile INST_DATA as —
# <prefix>/share/gdal/gdal. Self-consistent, but a path nobody expects;
# pass the parent so both bases land on <prefix>/share/gdal.
%global gdal_datadir %{gdal_prefix}/share
%endif

Name:           percona-gdal
Version:        %{gdal_version}
Release:        1%{?dist}
Summary:        GDAL runtime under /opt/percona-gdal for the Percona PostgreSQL binary tarball
License:        MIT
URL:            https://gdal.org/
# PERCONA: both tarballs are always fetched by the _service; %%prep
# unpacks only the one that matches the base being built.
Source0:        gdal-3.0.4.tar.xz
Source1:        gdal-3.4.3.tar.xz

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
# PERCONA: our own /opt PROJ — same SONAME as the libproj PostGIS linked,
# with the data path compiled to /opt/percona-proj/share/proj.
BuildRequires:  percona-proj
# The driver set, one BuildRequires per NEEDED entry of the official
# tarball's libgdal (see the header comment).
BuildRequires:  zlib-devel
BuildRequires:  libcurl-devel
BuildRequires:  libxml2-devel
BuildRequires:  openssl-devel
BuildRequires:  libzstd-devel
BuildRequires:  xz-devel
BuildRequires:  libjpeg-turbo-devel
BuildRequires:  libtiff-devel
BuildRequires:  libgeotiff-devel
BuildRequires:  libpng-devel
BuildRequires:  sqlite-devel
BuildRequires:  libspatialite-devel
BuildRequires:  freexl-devel
BuildRequires:  expat-devel
BuildRequires:  geos-devel
BuildRequires:  json-c-devel
%if 0%{?rhel} == 8
# GDAL 3.0.4 has no --with-pcre2 (and no --with-lz4): PCRE1 is the only
# regexp backend it can use. libpcre.so.1 is already bundled in the
# tarball via libspatialite, so this costs nothing.
BuildRequires:  pcre-devel
%else
BuildRequires:  pcre2-devel
BuildRequires:  lz4-devel
%endif

%description
GDAL %{version} built from the upstream source with the prefix
/opt/percona-gdal and only the drivers the official Percona PostgreSQL
tarball's libgdal links, so the binary tarball carries a handful of
shared objects instead of the ~70 that EPEL's fully-optioned gdal-libs
drags in. The GDAL data directory is compiled to
/opt/percona-gdal/share/gdal and PROJ comes from percona-proj, so both
resolve their resource files without any environment variables. The
upstream version is picked per base so the SONAME matches the libgdal
that the shipped PostGIS RPMs linked against (RHEL 8: 3.0.4 /
libgdal.so.26, RHEL 9: 3.4.3 / libgdal.so.30), making this a drop-in
replacement inside the tarball. Consumed by the tarball build; not
intended for standalone installation.

%prep
# PERCONA: -T -b %%{gdal_srcidx} — unpack only the base-matching tarball.
%setup -q -T -b %{gdal_srcidx} -n gdal-%{version}

%build
# PERCONA: rpath to %%{proj_prefix}/lib so libgdal finds our libproj from
# a plain install (the tarball flattens everything into one lib dir, but
# the RPM has to work on its own for the dlopen smoke test).
export LDFLAGS="%{?__global_ldflags} -Wl,-rpath,%{proj_prefix}/lib"

# --datadir: the whole point of the /opt prefix — GDAL bakes an
#   -DINST_DATA=\"...\" into libgdal (see %%{gdal_datadir} above: 3.0.4
#   takes --datadir verbatim, 3.4.3 appends "/gdal"), so the resource files
#   (gdal_datum.csv, pcs.csv, gt_datum.csv, ...) are found with no
#   GDAL_DATA in the environment.
# --with-proj: our /opt PROJ, not the distro's.
# --with-hide-internal-symbols: upstream's recommended default; keeps
#   libgdal from re-exporting the internal libtiff/geotiff symbols.
# --with-libjson-c/libtiff/geotiff/png/jpeg/libz=/usr: force the SYSTEM
#   copies (GDAL defaults several of these to its bundled sources); the
#   official tarball's libgdal links all of them externally, and the
#   tarball already carries them for other components.
# --with-gif=internal and --with-qhull=internal: the official libgdal has
#   no libgif at all and we keep qhull internal too — same driver
#   functionality, two fewer shared objects in the tarball.
# CFLAGS/CXXFLAGS carry %%{optflags} (without them the redhat-hardened-ld
#   spec produces PIE links from non-PIC objects and configure's very
#   first "can I run a program" test fails) plus
#   -I%%{_includedir}/libgeotiff: libgeotiff-devel puts geo_normalize.h in
#   its own subdirectory, which GDAL's --with-geotiff=<path> does not add.
# Everything under "explicitly OFF" below is a driver whose external
# library the official libgdal does NOT link. armadillo is the important
# one: it is what drags the FlexiBLAS/BLAS/LAPACK chain whose ELF
# constructor abort()s on Rocky hosts.
./configure \
    --prefix=%{gdal_prefix} \
    --libdir=%{gdal_prefix}/lib \
    --datadir=%{gdal_datadir} \
    --disable-static \
    --enable-shared \
    --disable-rpath \
    --with-hide-internal-symbols \
    --with-threads \
    --with-libz=/usr \
    --with-libtiff=/usr \
    --with-geotiff=/usr \
    --with-png=/usr \
    --with-jpeg=/usr \
    --with-libjson-c=/usr \
    --with-gif=internal \
    --with-qhull=internal \
    --with-sqlite3 \
    --with-spatialite \
    --with-freexl \
    --with-expat \
    --with-geos \
    --with-proj=%{proj_prefix} \
    --with-curl \
    --with-xml2 \
    --with-crypto \
    --with-zstd \
    --with-liblzma \
%if 0%{?rhel} == 8
    --with-pcre \
    --without-epsilon \
    --without-sde \
%else
    --with-pcre2 \
    --without-pcre \
    --with-lz4 \
    --without-blosc \
    --without-brunsli \
    --without-exr \
    --without-heif \
    --without-jxl \
    --without-libdeflate \
    --without-rdb \
%endif
    --without-armadillo \
    --without-cfitsio \
    --without-charls \
    --without-cryptopp \
    --without-dds \
    --without-dods-root \
    --without-ecw \
    --without-fgdb \
    --without-fme \
    --without-grass \
    --without-libgrass \
    --without-gta \
    --without-hdf4 \
    --without-hdf5 \
    --without-hdfs \
    --without-idb \
    --without-ingres \
    --without-jasper \
    --without-java \
    --without-jp2mrsid \
    --without-kakadu \
    --without-kea \
    --without-libkml \
    --without-mdb \
    --without-mongocxx \
    --without-mongocxxv3 \
    --without-mrsid \
    --without-mrsid_lidar \
    --without-msg \
    --without-mysql \
    --without-netcdf \
    --without-oci \
    --without-odbc \
    --without-ogdi \
    --without-opencl \
    --without-openjpeg \
    --without-pdfium \
    --without-perl \
    --without-pg \
    --without-podofo \
    --without-poppler \
    --without-python \
    --without-rasdaman \
    --without-rasterlite2 \
    --without-sfcgal \
    --without-sosi \
    --without-teigha \
    --without-tiledb \
    --without-webp \
    --without-xerces \
    CFLAGS="%{optflags} -I%{_includedir}/libgeotiff" \
    CXXFLAGS="%{optflags} -I%{_includedir}/libgeotiff"

make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
# PERCONA: libtool .la files hardcode buildroot paths.
find %{buildroot}%{gdal_prefix} -name '*.la' -delete

# PERCONA: hard gates on the two properties this package exists for —
# the compiled-in data path, and a driver surface with none of the
# libraries the official tarball's libgdal does without.
# (the resource files must actually BE in the directory libgdal was told
# about — GDAL also carries a <prefix>/share/gdal fallback string, so
# grepping the library alone would pass even with a wrong --datadir. The
# second test catches the <prefix>/share/gdal/gdal doubling that
# GDAL 3.4.3's extra "/gdal" produces if --datadir is set like 3.0.4's.)
test -s %{buildroot}%{gdal_prefix}/share/gdal/gdalicon.png
test ! -d %{buildroot}%{gdal_prefix}/share/gdal/gdal
grep -q '%{gdal_prefix}/share/gdal' %{buildroot}%{gdal_prefix}/lib/libgdal.so.*.*.*
for bad in libarmadillo libflexiblas libpoppler libhdf5 libmfhdf libnetcdf \
           libdap libxerces libkmlbase libodbc libmariadb libcfitsio libogdi \
           libjasper libopenjp2 libtirpc libwebp libgta libpq; do
    if readelf -d %{buildroot}%{gdal_prefix}/lib/libgdal.so.*.*.* | grep -q "$bad"; then
        echo "ERROR: libgdal links $bad — driver set is not lean" >&2
        exit 1
    fi
done

%files
%license LICENSE.TXT
%{gdal_prefix}

%changelog
* Tue Aug 25 2026 Percona Build/Release Team <eng-build@percona.com> - %{version}-%{release}
- Initial /opt/percona-gdal runtime for the Percona PostgreSQL binary
  tarball: GDAL 3.0.4 on RHEL 8 (libgdal.so.26) and GDAL 3.4.3 on
  RHEL 9 (libgdal.so.30), restricted to the official tarball's driver
  set (no armadillo/FlexiBLAS, hdf, netcdf, OPeNDAP, poppler, xerces,
  libkml, ODBC, mariadb, ...) and with the GDAL data directory compiled
  to /opt/percona-gdal/share/gdal (tarball QA task 22).
