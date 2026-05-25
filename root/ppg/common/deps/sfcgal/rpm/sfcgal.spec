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

Name:           %{pkgname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        C++ wrapper library around CGAL for ISO 19107:2013 geometry operations
License:        LGPL-2.0-or-later
URL:            https://sfcgal.gitlab.io/SFCGAL/
Source0:        %{srcname}-%{version}.tar.gz
Patch0:         boost.patch
Patch1:         647.patch
Vendor:         Percona LLC
Packager:       Percona LLC

BuildRequires:  cmake
BuildRequires:  gcc-c++
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
%if 0%{?rhel} && 0%{?rhel} >= 8
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

# openSUSE memory constraints
%if 0%{?suse_version}
BuildRequires:  memory-constraints
%endif

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

%if 0%{?rhel} && 0%{?rhel} >= 8 && 0%{?rhel} < 9
# Boost 1.73+ throw_exception wraps in wrapexcept<E> which needs a copy ctor.
# SFCGAL 2.x deleted copy ctors; restore them (Exception holds only std::string).
find . -name 'Exception.h' -exec perl -i -0777 \
  -pe 's/\)\s*noexcept\s*=\s*(delete|default)/) = default/g' {} \;
%endif

%build
%if 0%{?suse_version}
%limit_build -m 6400
%define _lto_cflags %{nil}
%endif

%cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DSFCGAL_BUILD_TESTS=OFF \
  -DSFCGAL_BUILD_EXAMPLES=OFF \
  -DSFCGAL_WITH_OSG=OFF \
  -DCMAKE_GMP_ENABLE_CXX=ON \
  -DSFCGAL_CHECK_VALIDITY=TRUE

%cmake_build

%install
%cmake_install

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
