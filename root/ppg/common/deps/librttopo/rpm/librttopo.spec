%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}

Name:		librttopo
Version:	%!{GIS_LIBRTTOPO_VERSION}
# PERCONA: keep PGDG's release base so this build outranks EPEL's/distro librttopo (which links the distro GEOS)
Release:	45%{?dist}
Vendor:		Percona LLC
Packager:	Percona LLC
Summary:	Create and manage SQL/MM topologies
License:	GPLv2+
URL:		https://git.osgeo.org/gitea/rttopo/%{name}
Source0:	%{name}-%{version}.tar.gz

BuildRequires:	autoconf automake gcc libtool make
BuildRequires:	binutils
BuildRequires:	geos%{geosmajorversion}-devel >= %{geosfullversion}
Requires:	geos%{geosmajorversion} >= %{geosfullversion}
%if 0%{?suse_version}
# PERCONA: openSUSE ships the same library as librttopo1 (/usr/lib64/librttopo.so.1, linked to the distro GEOS). Replace it so geos315's build wins and the two never conflict on file paths.
Provides:	librttopo1 = %{version}-%{release}
Obsoletes:	librttopo1 < %{version}-%{release}
%endif

%description
The RT Topology Library exposes an API to create and manage standard
(ISO 13249 aka SQL/MM) topologies using user-provided data stores.

%package	devel
Summary:	Development files for %{name}
Requires:	%{name}%{?_isa} = %{version}-%{release}

%description	devel
The %{name}-devel package contains libraries and header files for
developing applications that use %{name}.

%prep
%autosetup -p1 -n %{name}

%build
CFLAGS="$CFLAGS -I%{geosinstdir}/include -g -fPIE"; export CFLAGS
autoreconf -ifv
export PATH=%{geosinstdir}/bin:$PATH
LDFLAGS="${LDFLAGS:-%{?build_ldflags}} -Wl,-rpath,%{geosinstdir}/lib64" ; export LDFLAGS
%configure --disable-static
%make_build

%install
%make_install
find %{buildroot} -name '*.la' -exec rm -f {} ';'

# PERCONA: librttopo links geos315 outside the system linker path.
for f in %{buildroot}%{_libdir}/librttopo.so.*; do
  [ -L "$f" ] && continue
  readelf -d "$f" | grep -qE '\((RUNPATH|RPATH)\).*%{geosinstdir}/lib64' \
    || { echo "PERCONA: librttopo lacks RUNPATH to %{geosinstdir}/lib64"; exit 1; }
done

%files
%license COPYING
%doc CREDITS NEWS.md README.md TODO
%{_libdir}/%{name}.so.*
%{_libdir}/%{name}.so

%files devel
%{_includedir}/%{name}.h
%{_includedir}/%{name}_geom.h
%{_libdir}/pkgconfig/rttopo.pc

%changelog
* Fri Oct 16 2026 Percona Development <info@percona.com> - 1.1.0-45
- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead

* Mon Oct 12 2026 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-45PGDG
- Rebuild against GEOS 3.15. Per
  https://github.com/pgdg-packaging/pgdg-rpms/issues/359

* Mon Oct 5 2026 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-44PGDG
- Embed the GeOS library path as an rpath, so that librttopo uses GeOS
  3.14 also when other GeOS versions are installed: it was
  passed in SHLIB_LINK, which configure ignores.
- Require the GeOS package that we build against.

* Thu May 7 2026 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-43PGDG
- Rebuild against GeOS 3.14

* Tue Dec 17 2024 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-42PGDG
- Beat EPEL package per report from Sagar Yedida.

* Sun Sep 22 2024 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-4PGDG
- Rebuild against GeOS 3.13

* Thu Jan 18 2024 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-3PGDG
- Rebuild against GeOS 3.12.x
- Add PGDG branding

* Wed Jul 13 2022 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-2
- Build with GeOS 3.11.x

* Mon Feb 15 2021 Devrim Gündüz <devrim@gunduz.org> - 1.1.0-1
- Initial packaging for PostgreSQL RPM repository to satisfy
  libspatialite50 packaging, per Fedora spec file written by
  Sandro Mani (ours is a bit different then that spec file).
