%global _vpath_builddir .

%global		sname geos
%global		_geosversion	315
%global		geosinstdir /usr/%{sname}%{_geosversion}
%global		_geoslibdir lib64

Name:		%{sname}%{_geosversion}
Version:	%!{GIS_GEOS_VERSION}
Release:	1%{?dist}
Summary:	GEOS is a C++ port of the Java Topology Suite

License:	LGPLv2
URL:		https://libgeos.org/
Vendor:		Percona LLC
Packager:	Percona LLC
Source0:	%{sname}-%{version}.tar.bz2

BuildRequires:	cmake >= 3.15
%if 0%{?suse_version} >= 1500
BuildRequires:	cmake-full
%else
BuildRequires:	cmake-rpm-macros
%endif
BuildRequires:	libtool gcc-c++ binutils
%if 0%{?suse_version} == 1500
# %%build and %%install use GCC 13 there
BuildRequires:  gcc13 gcc13-c++
%endif
Provides:	geos%{_geosversion}-python >= %{version}

%description
GEOS (Geometry Engine - Open Source) is a C++ port of the Java Topology
Suite (JTS). As such, it aims to contain the complete functionality of
JTS in C++. This includes all the OpenGIS "Simple Features for SQL" spatial
predicate functions and spatial operators, as well as specific JTS topology
functions such as IsValid()

%package devel
Summary:	Development files for GEOS
Requires:	%{name} = %{version}-%{release}
Obsoletes:	geos36 <= 3.6.4 geos37 <= 3.7.3
Provides:	geos36 <= 3.6.4 geos37 <= 3.7.3

%description devel
GEOS (Geometry Engine - Open Source) is a C++ port of the Java Topology
Suite (JTS). As such, it aims to contain the complete functionality of
JTS in C++. This includes all the OpenGIS "Simple Features for SQL" spatial
predicate functions and spatial operators, as well as specific JTS topology
functions such as IsValid()

This package contains the development files to build applications that
use GEOS

%prep
%setup -q -n %{sname}-%{version}

%build
# Use a newer GCC on SLES 15 to install this version of GDAL:
%if 0%{?suse_version} == 1500
export CC=/usr/bin/gcc-13
export CXX=/usr/bin/g++-13
%endif
%cmake .. \
	-DCMAKE_INSTALL_PREFIX:PATH=%{geosinstdir} -DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
	-DCMAKE_SKIP_RPATH:BOOL=OFF \
	-DCMAKE_INSTALL_RPATH:STRING=%{geosinstdir}/%{_geoslibdir} \
	-D LIB_INSTALL_DIR=%{_lib} .

%cmake_build

%install
# Use a newer GCC on SLES 15 to install this version of GDAL:
%if 0%{?suse_version} == 1500
export CC=/usr/bin/gcc-13
export CXX=/usr/bin/g++-13
%endif

%cmake_install

# Remove files we don't ship:
%{__rm} -f %{buildroot}%{geosinstdir}/lib64/cmake/GEOS/geos-config*cmake
%{__rm} -f %{buildroot}%{geosinstdir}/lib64/cmake/GEOS/geos-targets*cmake

# PERCONA: PGDG registers %{geosinstdir} in /etc/ld.so.conf.d; we do not
# (system-wide linker path stays untouched). Every ELF object must find
# its siblings through RUNPATH instead.
for f in $(find %{buildroot}%{geosinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{geosinstdir}/%{_geoslibdir}' \
    || { echo "PERCONA: no RUNPATH to %{geosinstdir}/%{_geoslibdir} in ${f#%{buildroot}}"; exit 1; }
done

%files
%defattr(-,root,root,-)
%doc AUTHORS COPYING README.md
%{geosinstdir}/bin/geosop
%{geosinstdir}/%{_geoslibdir}/libgeos.so.%{version}
%{geosinstdir}/%{_geoslibdir}/libgeos.so
%{geosinstdir}/%{_geoslibdir}/libgeos_c.so*
%if 0%{?rhel} && 0%{?rhel} >= 8
%exclude %{geosinstdir}/%{_geoslibdir}/*.a
%endif

%files devel
%defattr(-,root,root,-)
%{geosinstdir}/bin/geos-config
%{geosinstdir}/include/*
%{geosinstdir}/%{_geoslibdir}/pkgconfig/%{sname}.pc

%changelog
* Fri Oct 16 2026 Percona Development <info@percona.com> - 3.15.0-1
- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead

* Mon Oct 5 2026 Devrim Gunduz <devrim@gunduz.org> - 3.15.0-2PGDG
- Build using GCC 13 on SLES 15.

* Tue Sep 1 2026 Devrim Gunduz <devrim@gunduz.org> - 3.15.0-1PGDG
- Initial packaging of 3.15.X for the PostgreSQL RPM Repository:
  https://github.com/libgeos/geos/releases/tag/3.15.0

