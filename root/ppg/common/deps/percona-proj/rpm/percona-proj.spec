# PERCONA PACKAGE for ppg:common:deps (RockyLinux_8 and RockyLinux_9 only).
#
# /opt-prefixed PROJ runtime consumed by the Percona PostgreSQL binary
# tarball (2026-07 tarball QA round, task 22).
#
# Why this exists: the tarball bundles the RPM-built postgis-*.so, which
# links libproj.so.NN, so the tarball has to carry a libproj. EPEL's
# libproj has its PROJ_DATA (formerly PROJ_LIB) default compiled to
# /usr/share/proj, a path that does not exist on the tarball's target
# hosts, so proj.db is never found and every ST_Transform() fails unless
# the server is started through an env-exporting wrapper (PROJ_DATA/
# PROJ_LIB) — and QA proved any wrapper bypass breaks it. This package
# builds PROJ from source with the prefix /opt/percona-proj, so the
# compiled-in data path is /opt/percona-proj/share/proj, proj.db sits
# right there, and reprojection works with ZERO environment variables —
# the official tarball's mechanism.
#
# Version is per base, chosen so the SONAME matches the libproj that the
# shipped PostGIS RPMs were linked against on that base. Our library must
# be a drop-in for EPEL's, because the tarball simply substitutes the
# bundled file:
#
#     RHEL 8 (ssl1.1 tarball): PROJ 6.3.2 -> libproj.so.15
#     RHEL 9 (ssl3   tarball): PROJ 9.6.0 -> libproj.so.25
#
# (both verified against the libproj.so.* real filenames in the built
# tarball artifacts: libproj.so.15.3.2 and libproj.so.25.9.6.0).
#
# We deliberately do NOT filter the auto-generated
# libproj.so.NN()(64bit) Provides: the ssl chroots that assemble the
# tarball use a project-config `Prefer:` to let this package satisfy
# PostGIS's SONAME Requires instead of EPEL's proj-libs. Everything
# installs under /opt/percona-proj, so nothing shadows a system package
# on a normal install, and ppg:common:deps is publish=false project-wide.
#
# Not to be confused with ppg:common:deps `proj` — that package is a
# Debian-only distro shadow (a newer PROJ for old Debian bases) built to
# /usr with the distro name. This one is a differently named, /opt-only
# tarball runtime and the two never meet in a chroot.

%global proj_prefix /opt/percona-proj

# PERCONA: base-specific upstream version + which Source to unpack.
# 6.3.2 is autotools-only-in-practice (its CMake build predates the
# TIFF/curl options); 9.6.0 is CMake-only (PROJ dropped autotools in 9.0),
# hence the two %%build/%%install paths below.
%if 0%{?rhel} == 8
%global proj_version 6.3.2
%global proj_srcidx 0
%global proj_soname 15
%else
%global proj_version 9.6.0
%global proj_srcidx 1
%global proj_soname 25
%endif

Name:           percona-proj
Version:        %{proj_version}
Release:        1%{?dist}
Summary:        PROJ runtime under /opt/percona-proj for the Percona PostgreSQL binary tarball
License:        MIT
URL:            https://proj.org/
# PERCONA: both tarballs are always fetched by the _service; the %%prep
# section unpacks only the one that matches the base being built.
Source0:        proj-6.3.2.tar.gz
Source1:        proj-9.6.0.tar.gz

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  sqlite-devel
# PERCONA: the sqlite3 CLI builds proj.db from the .sql sources at build
# time — without it there is no database to find at the compiled path.
BuildRequires:  sqlite
%if 0%{?rhel} == 8
# 6.3.2 has no TIFF/curl grid support at all (matches EPEL 8's proj-libs,
# whose only non-libc NEEDED entry is libsqlite3.so.0), so nothing else
# is needed here.
%else
BuildRequires:  cmake >= 3.16
# 9.6.0: TIFF + curl are the (default-on) remote/TIFF grid backends and
# are what EPEL 9's libproj.so.25 links too — no extra library lands in
# the tarball, libtiff and libcurl are bundled for GDAL anyway.
BuildRequires:  libtiff-devel
BuildRequires:  libcurl-devel
%endif

%description
PROJ %{version} built from the upstream source with the install prefix
/opt/percona-proj, so libproj's compiled-in PROJ_DATA default is
/opt/percona-proj/share/proj and proj.db resolves without any
environment variables. The upstream version is picked per base so the
SONAME matches the libproj that the shipped PostGIS RPMs linked
against (RHEL 8: 6.3.2 / libproj.so.15, RHEL 9: 9.6.0 /
libproj.so.25), making this a drop-in replacement inside the Percona
PostgreSQL binary tarball. Consumed by the tarball build; not intended
for standalone installation.

%prep
# PERCONA: -T -b %%{proj_srcidx} — unpack only the base-matching tarball.
%setup -q -T -b %{proj_srcidx} -n proj-%{version}

%build
%if 0%{?rhel} == 8
# PERCONA: autotools. --disable-static keeps the /opt tree to just the
# shared library. No --with-* flags exist for extra backends in 6.3.2,
# so the link surface is sqlite3 + libstdc++ only, exactly like EPEL's.
./configure \
    --prefix=%{proj_prefix} \
    --libdir=%{proj_prefix}/lib \
    --datarootdir=%{proj_prefix}/share \
    --disable-static \
    CFLAGS="%{optflags}" \
    CXXFLAGS="%{optflags}"
make %{?_smp_mflags}
%else
# PERCONA: plain cmake, not %%cmake — the distro macro forces
# /usr + lib64 and we need a self-contained /opt tree.
# CMAKE_INSTALL_LIBDIR=lib: GNUInstallDirs would pick lib64 on EL, and
# the tarball builder plus percona-gdal's --with-proj both expect
# <prefix>/lib.
# EMBED_PROJ_DATA_PATH is upstream's default ON and is the whole point of
# this package: it bakes -DPROJ_DATA="<prefix>/share/proj" into libproj.
# BUILD_TESTING=OFF avoids pulling googletest into the chroot.
mkdir -p build
cd build
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=%{proj_prefix} \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_C_FLAGS="%{optflags}" \
    -DCMAKE_CXX_FLAGS="%{optflags}" \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTING=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DEMBED_PROJ_DATA_PATH=ON \
    -DENABLE_TIFF=ON \
    -DENABLE_CURL=ON \
    -DNLOHMANN_JSON_ORIGIN=internal
make %{?_smp_mflags}
%endif

%install
%if 0%{?rhel} == 8
make install DESTDIR=%{buildroot}
# PERCONA: libtool leaves .la files that hardcode buildroot paths.
find %{buildroot}%{proj_prefix} -name '*.la' -delete
%else
make -C build install DESTDIR=%{buildroot}
%endif

# PERCONA: hard gates on the two properties the whole package exists for.
#
# 1. SONAME parity. The package is only useful as a drop-in for the libproj
#    the shipped PostGIS RPMs linked against, so assert the SONAME we
#    promised for this base actually came out. Without this, a source-URL
#    bump — or this spec being built on an unexpected %%{?rhel} where the
#    %%if picks the wrong branch — would silently produce a library that is
#    no longer ABI-compatible with PostGIS.
test -e %{buildroot}%{proj_prefix}/lib/libproj.so.%{proj_soname}
# 2. The compiled-in data path, and a proj.db sitting at it.
test -f %{buildroot}%{proj_prefix}/share/proj/proj.db
grep -q '%{proj_prefix}/share/proj' %{buildroot}%{proj_prefix}/lib/libproj.so.%{proj_soname}

%files
%license COPYING
%{proj_prefix}

%changelog
* Wed Sep 02 2026 Percona Build/Release Team <eng-build@percona.com> - %{version}-%{release}
- Drop ExcludeArch aarch64: the binary tarball (ppg:staging:NN:tarballs)
  now builds for aarch64 too, so this runtime is no longer dead weight
  on that arch.

* Tue Aug 25 2026 Percona Build/Release Team <eng-build@percona.com> - %{version}-%{release}
- Initial /opt/percona-proj runtime for the Percona PostgreSQL binary
  tarball: PROJ 6.3.2 on RHEL 8 (libproj.so.15) and PROJ 9.6.0 on
  RHEL 9 (libproj.so.25), both with the PROJ_DATA default compiled to
  /opt/percona-proj/share/proj so proj.db is found with zero
  environment variables (tarball QA task 22).
