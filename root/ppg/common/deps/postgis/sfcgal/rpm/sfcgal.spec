%define srcname sfcgal
%define _soversion 2

# Package naming convention: uppercase on RHEL/Fedora, lowercase on openSUSE
%if 0%{?rhel} || 0%{?fedora}
%global pkgname SFCGAL
%else
%global pkgname sfcgal
%endif

# ix86 excluded upstream (SFCGAL issues #258, #259)
ExcludeArch: %{ix86}

# SFCGAL 2.3 uses std::filesystem. gcc 8's libstdc++ keeps it in a separate
# static archive that upstream never links, so libSFCGAL.so ends up with
# undefined std::filesystem symbols that break every consumer link (PostGIS).
# gcc-toolset folds the newer symbols in statically via libstdc++_nonshared.a
# (same approach as proj and percona-postgis on EL8).
%if 0%{?rhel} == 8
%global gts_version 14
# EL8's Boost 1.78 Multiprecision provides a __float128 conversion in its GMP
# backend that no longer compiles with gcc >= 13 (C++23 extended-float rules
# made __float128 non-convertible; fixed upstream in Boost 1.82). CGAL pulls
# those headers in unless told not to. Numerically a no-op here: with
# CMAKE_GMP_ENABLE_CXX=ON CGAL already selects the GMPXX exact backend
# ahead of the Boost one, so Exact_rational stays mpq_class.
%global optflags %{optflags} -DCGAL_DO_NOT_USE_BOOST_MP
%endif

Name:           %{pkgname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        C++ wrapper library around CGAL for ISO 19107:2013 geometry operations
License:        LGPL-2.0-or-later
URL:            https://sfcgal.gitlab.io/SFCGAL/
Source0:        %{srcname}-%{version}.tar.gz
Vendor:         Percona LLC
Packager:       Percona LLC

BuildRequires:  cmake
BuildRequires:  gcc-c++
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
BuildRequires:  pkgconfig
BuildRequires:  gmp-devel
BuildRequires:  eigen3-devel

# CGAL
%if 0%{?suse_version}
BuildRequires:  libcgal-devel >= 5.6
%else
BuildRequires:  CGAL-devel >= 5.6
%endif

# Boost
%if 0%{?suse_version}
BuildRequires:  libboost_headers-devel >= 1.69
BuildRequires:  libboost_thread-devel >= 1.69
BuildRequires:  libboost_serialization-devel >= 1.69
%else
%if 0%{?rhel} && 0%{?rhel} >= 8 && 0%{?rhel} < 10
BuildRequires:  boost1.78-devel
%else
BuildRequires:  boost-devel >= 1.69
%endif
%endif

# MPFR
%if 0%{?suse_version}
BuildRequires:  pkgconfig(mpfr)
%else
BuildRequires:  mpfr-devel
%endif

# nlohmann/json
%if 0%{?suse_version}
BuildRequires:  pkgconfig(nlohmann_json)
%else
BuildRequires:  nlohmann-json-devel
%endif

# %%limit_build: clamp -j to the memory available in the build VM.
# openSUSE ships this in the distro; for RHEL-family repos it comes from
# common:deps:build (a _link to openSUSE:Factory/memory-constraints).
BuildRequires:  memory-constraints

%description
SFCGAL is a C++ wrapper library around CGAL with the aim of supporting
ISO 19107:2013 and OGC Simple Features Access 1.2 for 3D operations.

It provides standard compliant geometry types and operations, accessible
from its C or C++ APIs. PostGIS uses the C API to expose SFCGAL functions
in spatial databases.

Geometry coordinates have an exact rational number representation and can
be either 2D or 3D. Supported geometry types include Points, LineStrings,
Polygons, TriangulatedSurfaces, PolyhedralSurfaces, GeometryCollections,
and Solids.

%package devel
Summary:        Development files for SFCGAL
Requires:       %{name} = %{version}-%{release}
Requires:       pkgconfig

%description devel
Headers, pkg-config file, cmake modules, and the sfcgal-config tool for
building applications that use SFCGAL.

%prep
%autosetup -p1 -n %{srcname}-%{version}


%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
# CGAL template instantiation needs several GB per compile job; aarch64
# workers with little RAM per core OOM at -j$(nproc). Let %%limit_build pick
# a -j that fits (MemTotal+SwapTotal)/6400MB. No-op on well-provisioned hosts.
%limit_build -m 6400
%if 0%{?suse_version}
%define _lto_cflags %{nil}
%endif

%cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DSFCGAL_BUILD_TESTS=OFF \
  -DSFCGAL_BUILD_EXAMPLES=OFF \
  -DSFCGAL_WITH_OSG=OFF \
  -DCMAKE_GMP_ENABLE_CXX=ON \
  -DSFCGAL_CHECK_VALIDITY=TRUE \
%if 0%{?rhel} && 0%{?rhel} >= 10
  -DCMAKE_SKIP_INSTALL_RPATH=ON \
%endif
  %{nil}

%cmake_build

%install
%cmake_install

# A shared library links fine with dangling symbol references; they only
# blow up when a consumer (PostGIS) links an executable against it. Catch
# that here instead: ldd -r resolves every relocation and reports any
# undefined symbol.
if ldd -r %{buildroot}%{_libdir}/libSFCGAL.so.%{version} 2>&1 | grep 'undefined symbol'; then
  echo "libSFCGAL.so has unresolved symbols" >&2
  exit 1
fi

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files
%license LICENSE
%doc README.md AUTHORS NEWS
%{_libdir}/libSFCGAL.so.%{version}
%{_libdir}/libSFCGAL.so.%{_soversion}

%files devel
%license LICENSE
%{_libdir}/libSFCGAL.so
%{_libdir}/pkgconfig/sfcgal.pc
%{_libdir}/cmake/SFCGAL
%{_includedir}/SFCGAL
%{_bindir}/sfcgal-config

%changelog
