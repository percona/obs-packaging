# PERCONA PACKAGE for ppg:common:deps:tarballs (RockyLinux_8, RockyLinux_9.6, RockyLinux_9).
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
# Version is per base and follows the PGDG-mirrored PROJ that the shipped
# PostGIS RPMs link on that base (ppg:common:deps:postgis proj96/proj98,
# root/macros.yaml GIS_PROJ_*). Our library must be a drop-in for that one,
# because the tarball simply substitutes the bundled file:
#
#     RHEL 8 (ssl1.1 tarball):        PROJ 9.6.2 (proj96) -> libproj.so.25
#     RHEL 9 (ssl3/ssl3.5 tarballs):  PROJ 9.8.1 (proj98) -> libproj.so.25
#
# We deliberately do NOT filter the auto-generated
# libproj.so.NN()(64bit) Provides: the ssl chroots that assemble the
# tarball use a project-config `Prefer:` to let this package satisfy
# PostGIS's SONAME Requires instead of proj96/proj98. Everything
# installs under /opt/percona-proj, so nothing shadows a system package
# on a normal install, and ppg:common:deps is publish=false project-wide.
#
# Not to be confused with ppg:common:deps `proj` — that package is a
# Debian-only distro shadow (a newer PROJ for old Debian bases) built to
# /usr with the distro name. This one is a differently named, /opt-only
# tarball runtime and the two never meet in a chroot.

%global proj_prefix /opt/percona-proj

# PERCONA: base-specific upstream version + which Source to unpack. Both
# are CMake-only (PROJ dropped autotools in 9.0), so every base takes the
# same %%build/%%install path below.
%if 0%{?rhel} == 8
%global proj_version %!{GIS_PROJ_EL8_VERSION}
%global proj_srcidx 0
%else
%global proj_version %!{GIS_PROJ_VERSION}
%global proj_srcidx 1
%endif
%global proj_soname 25

# PERCONA: same compiler as proj96/proj98 (PGDG): PROJ 9.6+/9.8 needs
# gcc-toolset-14 on EL8 and EL9 for its C23 cmake check. RHEL 10 ships
# gcc 14 natively.
%if 0%{?rhel} && 0%{?rhel} < 10
%global gts_version 14
%endif

Name:           percona-proj
Version:        %{proj_version}
Release:        1%{?dist}
Summary:        PROJ runtime under /opt/percona-proj for the Percona PostgreSQL binary tarball
License:        MIT
URL:            https://proj.org/
# PERCONA: both tarballs are always fetched by the _service; the %%prep
# section unpacks only the one that matches the base being built.
Source0:        proj-%!{GIS_PROJ_EL8_VERSION}.tar.gz
Source1:        proj-%!{GIS_PROJ_VERSION}.tar.gz

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc
BuildRequires:  gcc-toolset-%{gts_version}-gcc-c++
BuildRequires:  gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
BuildRequires:  cmake >= 3.16
BuildRequires:  sqlite-devel
# PERCONA: the sqlite3 CLI builds proj.db from the .sql sources at build
# time — without it there is no database to find at the compiled path.
BuildRequires:  sqlite
# TIFF + curl are the (default-on) remote/TIFF grid backends and are what
# proj96/proj98's libproj.so.25 links too — no extra library lands in the
# tarball, libtiff and libcurl are bundled for GDAL anyway.
BuildRequires:  libtiff-devel
BuildRequires:  libcurl-devel

%description
PROJ %{version} built from the upstream source with the install prefix
/opt/percona-proj, so libproj's compiled-in PROJ_DATA default is
/opt/percona-proj/share/proj and proj.db resolves without any
environment variables. The upstream version is picked per base so the
SONAME matches the libproj that the shipped PostGIS RPMs linked
against (RHEL 8: 9.6.2 like proj96, RHEL 9: 9.8.1 like proj98, both
libproj.so.25), making this a drop-in replacement inside the Percona
PostgreSQL binary tarball. Consumed by the tarball build; not intended
for standalone installation.

%prep
# PERCONA: -T -b %%{proj_srcidx} — unpack only the base-matching tarball.
%setup -q -T -b %{proj_srcidx} -n proj-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
# PERCONA: plain cmake, not %%cmake — the distro macro forces
# /usr + lib64 and we need a self-contained /opt tree.
# CMAKE_INSTALL_LIBDIR=lib: GNUInstallDirs would pick lib64 on EL, and
# the tarball builder and percona-gdal (CMAKE_PREFIX_PATH, rpath) expect
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

%install
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
make -C build install DESTDIR=%{buildroot}

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
* Sun Oct 18 2026 Percona Development <info@percona.com> - %{version}-%{release}
- Follow the PGDG-mirrored PROJ that PostGIS now links: 9.6.2 on RHEL 8
  (proj96) and 9.8.1 on RHEL 9 (proj98), both libproj.so.25, versions
  from root/macros.yaml. RHEL 8 drops the 6.3.2 autotools build for the
  common CMake path; gcc-toolset-14 on EL8/EL9 as in proj96/proj98.

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
