%global	_vpath_builddir .
%global sname proj

%global projinstdir /usr/%{sname}98

Name:		%{sname}98
Version:	%!{GIS_PROJ_VERSION}
Release:	1%{?dist}
Vendor:		Percona LLC
Packager:	Percona LLC
Summary:	Cartographic projection software (PROJ)

License:	MIT
URL:		https://proj.org
Source0:	%{sname}-%{version}.tar.gz

BuildRequires:	sqlite-devel >= 3.7 libcurl-devel cmake >= 3.16 sqlite
BuildRequires:	binutils
BuildRequires:	libtiff-devel

# Default GCC version on SLES 15 is not sufficient to build PROJ 9.8,
# so use a newer one:
%if 0%{?suse_version} == 1500
BuildRequires:	gcc12-c++
%else
# The rest is safe:
BuildRequires:	gcc-c++
%endif

%if 0%{?suse_version} >= 1500
# SLES ships the libraries with -devel subpackage:
Requires:	sqlite3-devel >= 3.7
%else
# All other sane distributions have a separate -libs subpackage:
Requires:	sqlite-libs >= 3.7
%endif

%package devel
Summary:	Development files for PROJ
Requires:	%{name} = %{version}-%{release}

%description
PROJ is a generic coordinate transformation software that transforms
geospatial coordinates from one coordinate reference system (CRS) to another.
This includes cartographic projections as well as geodetic transformations.

%description devel
This package contains libproj and the appropriate header files and man pages.

%prep
%setup -q -n %{sname}-%{version}

%build

%{__install} -d build
pushd build
LDFLAGS="-Wl,-rpath,%{projinstdir}/lib64 ${LDFLAGS}" ; export LDFLAGS
SHLIB_LINK="$SHLIB_LINK -Wl,-rpath,%{projinstdir}/lib64" ; export SHLIB_LINK

%if 0%{?suse_version} == 1500
export CXX=/usr/bin/g++-12
%endif

cmake ..\
	-DCMAKE_INSTALL_PREFIX:PATH=%{projinstdir} \
	-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
	-DCMAKE_SKIP_RPATH:BOOL=OFF \
	-DCMAKE_INSTALL_RPATH:STRING=%{projinstdir}/lib64 \
	-DCMAKE_C_FLAGS="${RPM_OPT_FLAGS}" \
	-DCMAKE_CXX_FLAGS="${RPM_OPT_FLAGS}"

%{__make} -C "%{_vpath_builddir}" %{?_smp_mflags}
popd

%install
pushd build
%{__make} -C "%{_vpath_builddir}" %{?_smp_mflags} install/fast \
	DESTDIR=%{buildroot}
popd

%{__install} -d %{buildroot}%{projinstdir}/share/%{sname}
%{__install} -d %{buildroot}%{projinstdir}/share/doc/
%{__install} -p -m 0644 NEWS.md AUTHORS.md COPYING README.md ChangeLog %{buildroot}%{projinstdir}/share/doc/

# PERCONA: no /etc/ld.so.conf.d drop-in; RUNPATH must cover our lib dir.
for f in $(find %{buildroot}%{projinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{projinstdir}/lib64' \
    || { echo "PERCONA: no RUNPATH to %{projinstdir}/lib64 in ${f#%{buildroot}}"; exit 1; }
done

%post
/sbin/ldconfig

%postun
/sbin/ldconfig

%files
%defattr(-,root,root,-)
%doc %{projinstdir}/share/doc/*
%{projinstdir}/share/bash-completion/completions/projinfo
%{projinstdir}/bin/*
%{projinstdir}/share/man/man1/*.1
%{projinstdir}/share/proj/*
%{projinstdir}/lib64/libproj.so.25*

%files devel
%defattr(-,root,root,-)
%{projinstdir}/share/man/man1/*.1
%{projinstdir}/include/*.h
%{projinstdir}/include/proj/*
%{projinstdir}/lib64/*.so
%attr(0755,root,root) %{projinstdir}/lib64/pkgconfig/%{sname}.pc
%{projinstdir}/lib64/cmake/%{sname}/*cmake
%{projinstdir}/lib64/cmake/%{sname}4/*cmake

%changelog
* Fri Oct 16 2026 Percona Development <info@percona.com> - 9.8.1-1
- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead

* Sat Apr 11 2026 Devrim Gündüz <devrim@gunduz.org> - 9.8.1-1PGDG
- Update to 9.8.1 per changes described at:
  https://github.com/OSGeo/PROJ/releases/tag/9.8.1

* Tue Mar 10 2026 Devrim Gündüz <devrim@gunduz.org> - 9.8.0-1PGDG
- Initial 9.8 packaging for the PostgreSQL RPM Repository.
