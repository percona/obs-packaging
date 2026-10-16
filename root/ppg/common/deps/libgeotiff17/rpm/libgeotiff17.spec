%global _vpath_builddir .
%global	sname libgeotiff
%global	libgeotiffversion 17

%global libgeotiffinstdir /usr/%{sname}%{libgeotiffversion}
%if 0%{?rhel} == 8
%global projmajorversion %!{GIS_PROJ_EL8_MAJOR}
%global projfullversion %!{GIS_PROJ_EL8_VERSION}
%else
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%endif
%global projinstdir /usr/proj%{projmajorversion}

Name:		%{sname}%{libgeotiffversion}
Version:	%!{GIS_LIBGEOTIFF_VERSION}
Release:	1%{?dist}
Vendor:		Percona LLC
Packager:	Percona LLC
Summary:	GeoTIFF format library
License:	MIT
URL:		https://github.com/OSGeo/%{sname}
Source0:	%{sname}-%{version}.tar.gz
Patch0:		%{sname}_cmake.patch
Patch1:		%{sname}-1.7.4-proj.patch
BuildRequires:	libtiff-devel libjpeg-devel proj%{projmajorversion}-devel >= %{projfullversion} zlib-devel
BuildRequires:	cmake gcc gcc-c++ ccache binutils

%description
GeoTIFF represents an effort by over 160 different remote sensing,
GIS, cartographic, and surveying related companies and organizations
to establish a TIFF based interchange format for georeferenced
raster imagery.

%package devel
Summary:	Development Libraries for the GeoTIFF file format library
Requires:	pkgconfig libtiff-devel
Requires:	%{name} = %{version}-%{release}

%description devel
The GeoTIFF library provides support for development of geotiff image format.

%prep
%setup -q -n %{sname}-%{version}
%patch -P 0 -p0
%patch -P 1 -p0

# fix wrongly encoded files from tarball
set +x
for f in `find . -type f` ; do
   if file $f | grep -q ISO-8859 ; then
      set -x
      iconv -f ISO-8859-1 -t UTF-8 $f > ${f}.tmp && \
	mv -f ${f}.tmp $f
      set +x
   fi
   if file $f | grep -q CRLF ; then
      set -x
      sed -i -e 's|\r||g' $f
      set +x
   fi
done
set -x

%build

%{__install} -d build
pushd build
# PERCONA: PGDG installs bin/makegeo from the build tree, so build-tree binaries
# must already carry the install RPATH (BUILD_WITH_INSTALL_RPATH).
cmake .. -DCMAKE_C_COMPILER_LAUNCHER=ccache \
	-DCMAKE_BUILD_WITH_INSTALL_RPATH:BOOL=ON \
	-DCMAKE_SKIP_RPATH:BOOL=OFF \
	-DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
	-DCMAKE_INSTALL_RPATH:STRING="%{libgeotiffinstdir}/lib;%{projinstdir}/lib64" \
	-DPROJ_LIBRARY=%{projinstdir}/lib64/libproj.so \
	-DPROJ_INCLUDE_DIR=%{projinstdir}/include \
	-DCMAKE_INSTALL_INCLUDEDIR=%{libgeotiffinstdir}/include \
	-DCMAKE_INSTALL_BINDIR=%{libgeotiffinstdir}/bin \
	-DCMAKE_INSTALL_LIBDIR=%{libgeotiffinstdir}/lib \
	-DCMAKE_INSTALL_MANDIR=%{libgeotiffinstdir}/man \
	-DCMAKE_INSTALL_DOCDIR=%{_docdir}/%{name}

%{__make} -C "%{_vpath_builddir}" %{?_smp_mflags}
popd

%install
# install libgeotiff
pushd build
%{__make} -C "%{_vpath_builddir}" %{?_smp_mflags} install DESTDIR=%{buildroot}

# install some files manually
%{__mkdir} -p %{buildroot}%{libgeotiffinstdir}/bin
%{__install} -p -m 755 bin/makegeo %{buildroot}%{libgeotiffinstdir}/bin
popd

# install pkgconfig file
cat > %{name}.pc <<EOF
prefix=%{libgeotiffinstdir}
exec_prefix=%{libgeotiffinstdir}
libdir=%{libgeotiffinstdir}/lib
includedir=%{libgeotiffinstdir}/include

Name: %{name}
Description: GeoTIFF file format library
Version: %{version}
Libs: -L\${libdir} -lgeotiff
Cflags: -I\${includedir}
EOF

%{__mkdir} -p %{buildroot}%{libgeotiffinstdir}/lib/pkgconfig/
%{__install} -p -m 644 %{name}.pc %{buildroot}%{libgeotiffinstdir}/lib/pkgconfig/

# Do some manual installation:
%{__mkdir} -p %{buildroot}/%{_docdir}/%{name}
%{__mkdir} -p %{buildroot}%{libgeotiffinstdir}/lib
%{__mkdir} -p %{buildroot}%{libgeotiffinstdir}/man/man1

# PERCONA: no /etc/ld.so.conf.d drop-in; RUNPATH must reach our lib + PROJ.
for f in $(find %{buildroot}%{libgeotiffinstdir} -type f); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{libgeotiffinstdir}/lib %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files
%dir %{libgeotiffinstdir}/bin
%dir %{libgeotiffinstdir}/lib
%dir %{libgeotiffinstdir}/man
%dir %{libgeotiffinstdir}/man/man1
# PERCONA: AUTHORS is shipped empty upstream (openSUSE rpmlint: zero-length)
%doc ChangeLog LICENSE COPYING INSTALL README*
%dir %{libgeotiffinstdir}/
%{libgeotiffinstdir}/bin/applygeo
%{libgeotiffinstdir}/bin/geotifcp
%{libgeotiffinstdir}/bin/listgeo
%{libgeotiffinstdir}/bin/makegeo
%{libgeotiffinstdir}/lib/*
%exclude %{libgeotiffinstdir}/lib/pkgconfig
%{libgeotiffinstdir}/man/man1/listgeo.1
%{libgeotiffinstdir}/man/man1/geotifcp.1
%{libgeotiffinstdir}/man/man1/applygeo.1

%files devel
%dir %{libgeotiffinstdir}
%dir %{libgeotiffinstdir}/lib
%dir %{libgeotiffinstdir}/lib/pkgconfig
%dir %{libgeotiffinstdir}/include
%attr(0644,root,root) %{libgeotiffinstdir}/include/*.h
%attr(0644,root,root) %{libgeotiffinstdir}/include/*.inc
%{libgeotiffinstdir}/lib/pkgconfig/%{name}.pc

%changelog
* Fri Oct 16 2026 Percona Development <info@percona.com> - 1.7.4-1
- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead

* Thu Apr 16 2026 Devrim Gündüz <devrim@gunduz.org> - 1.7.4-5PGDG
- Rebuild against PROJ 9.8 on all platforms except RHEL 8.

* Mon Oct 13 2025 Devrim Gündüz <devrim@gunduz.org> - 1.7.4-4PGDG
- Fix mock builds. Per report from Christoph Berg.

* Tue Oct 7 2025 Devrim Gündüz <devrim@gunduz.org> - 1.7.4-3PGDG
- Rebuild against PROJ 9.7 on all platforms except RHEL 8.

* Thu Jul 17 2025 Devrim Gündüz <devrim@gunduz.org> - 1.7.4-2PGDG
- Rebuild against PROJ 9.6 on SLES 15 and RHEL 8 as well.

* Mon Jun 23 2025 Devrim Gündüz <devrim@gunduz.org> - 1.7.4-1PGDG
- Update to 1.7.4 per changes described at:
  https://github.com/OSGeo/libgeotiff/releases/tag/1.7.4
- Add a patch from upstream per:
  https://github.com/OSGeo/libgeotiff/issues/137

* Wed Apr 16 2025 Devrim Gündüz <devrim@gunduz.org> - 1.7.3-3PGDG
- Rebuild against PROJ 9.6

* Thu Sep 19 2024 Devrim Gündüz <devrim@gunduz.org> - 1.7.3-2PGDG
- Rebuild against PROJ 9.5

* Fri Jul 5 2024 Devrim Gündüz <devrim@gunduz.org> - 1.7.3-1PGDG
- Update to 1.7.3 per changes described at:
  https://github.com/OSGeo/libgeotiff/releases/tag/1.7.3
  https://github.com/OSGeo/libgeotiff/releases/tag/1.7.2

* Wed Apr 10 2024 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-6PGDG
- Rebuild against PROJ 9.4

* Mon Jan 29 2024 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-5PGDG
- Rebuild against Proj 9.3

* Thu Sep 21 2023 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-4PGDG
- Support SLES 15

* Mon Aug 28 2023 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-3PGDG
- Remove RHEL 7 bits
- Add PGDG branding
- Fix rpmlint and build warnings

* Thu Apr 6 2023 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-2
- Use Proj 9.2.X

* Wed Mar 23 2022 Devrim Gündüz <devrim@gunduz.org> - 1.7.1-1
- Update to 1.7.1

* Wed Sep 1 2021 Devrim Gündüz <devrim@gunduz.org> - 1.7.0-1
- Initial packaging for PostgreSQL RPM repository.
