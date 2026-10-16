%global sname gdal
%global gdalmajorversion 3.13

%if 0%{?fedora} >= 43 || 0%{?rhel} >= 9 || 0%{?suse_version} >= 1600
%global gdal_python_enabled 1
%{!?gdaljava:%global gdaljava 1}
%else
%global gdal_python_enabled 0
%{!?gdaljava:%global gdaljava 0}
%endif

%if 0%{?fedora} && 0%{?fedora} == 45
%global __ospython %{_bindir}/python3.15
%global python3_pkgversion 3.15
%endif
%if 0%{?fedora} && 0%{?fedora} <= 44
%global __ospython %{_bindir}/python3.14
%global python3_pkgversion 3.14
%endif
%if 0%{?rhel} && 0%{?rhel} <= 9
%global	__ospython %{_bindir}/python3.12
%global	python3_pkgversion 3.12
%global	pyver 3.12
%endif
%if 0%{?rhel} == 10
# PERCONA: EL10's python3 *is* 3.12; there is no python3.12-devel/-numpy.
%global	__ospython %{_bindir}/python3
%global	python3_pkgversion 3
%global	pyver 3.12
%endif
%if 0%{?amzn} == 2023
%global	__ospython %{_bindir}/python3.13
%global	python3_pkgversion 3.13
%endif
%if 0%{?suse_version} == 1500
%global	__ospython %{_bindir}/python3.11
%global	python3_pkgversion 311
%endif
# PERCONA: Tumbleweed (suse_version 1699, python3 = 3.13) follows PGDG's
# SLES 16 branch here and below; PGDG has no Tumbleweed target.
%if 0%{?suse_version} >= 1600
%global	__ospython %{_bindir}/python3.13
%global	python3_pkgversion 313
%global	pyver 3.13
%endif

# PERCONA: replaces %%pgdg_set_gis_variables (pgdg-srpm-macros); versions
# come from root/macros.yaml.
%global geosmajorversion %!{GIS_GEOS_MAJOR}
%global geosfullversion %!{GIS_GEOS_VERSION}
%global geosinstdir /usr/geos%{geosmajorversion}
%global projmajorversion %!{GIS_PROJ_MAJOR}
%global projfullversion %!{GIS_PROJ_VERSION}
%global projinstdir /usr/proj%{projmajorversion}
%global libgeotiffmajorversion 17
%global libgeotiffinstdir /usr/libgeotiff%{libgeotiffmajorversion}
%global libspatialitemajorversion 50
%global libspatialiteinstdir /usr/libspatialite%{libspatialitemajorversion}
%global gdalinstdir /usr/%{name}

# PERCONA: pyver is set statically above for the interpreters we pin, so the
# spec also parses where that interpreter is not installed (OBS's server-side
# parser, rpmspec checks); PGDG's shell probe remains the fallback.
%if %gdal_python_enabled
%{!?pyver:%{expand: %%global pyver %(echo `%{__ospython} -c "import sys; sys.stdout.write(sys.version[:4])"`)}}
%endif

%global bashcompletiondir %(pkg-config --variable=compatdir bash-completion)

%global gdalsomajorversion	39

# PERCONA: proj98 everywhere (gdal313 is not built on EL8, which uses gdal38
# on proj96); the GIS globals are defined above.

# PERCONA: Tumbleweed has no g2clib either; GRIB uses the bundled g2lib.
%if 0%{?suse_version} <= 1699
%global	g2clib_enabled 0
%else
%global	g2clib_enabled 1
%endif

# Enable/disable generating refmans
# texlive currently broken deps and FTBFS in rawhide
%global build_refman 0
# https://bugzilla.redhat.com/show_bug.cgi?id=1490492

Name:		%{sname}313
Version:	%!{GIS_GDAL_VERSION}
Release:	1%{?dist}
Vendor:		Percona LLC
Packager:	Percona LLC
Summary:	GIS file format library
License:	MIT
URL:		https://www.gdal.org
# Source0: https://download.osgeo.org/gdal/%%{version}/gdal-%%{version}.tar.xz
# See PROVENANCE.TXT-fedora and the cleaner script for details!

Source0:	https://download.postgresql.org/pub/repos/yum/sources/gdal/%{gdalmajorversion}/gdal-%{version}-fedora.tar.xz
Source4:	PROVENANCE.TXT-fedora

# Cleaner script for the tarball
Source5:	%{sname}-cleaner.sh

Patch0:		%{name}-cleanup.patch

# lz4 and bash-completion dependencies
%if 0%{?suse_version} >= 1500
BuildRequires:	liblz4-devel bash-completion-devel
Requires:	liblz4-1
%endif
%if 0%{?rhel} || 0%{?fedora}
BuildRequires:	lz4-devel bash-completion
Requires:	lz4
%endif

BuildRequires:	ant cmake gcc-c++ bison
# PERCONA: readelf for the RUNPATH check in %%install.
BuildRequires:	binutils
%if 0%{?suse_version} == 1500
# %%build and %%install use GCC 13 there
BuildRequires:	gcc13 gcc13-c++
%endif

BuildRequires:	armadillo-devel
BuildRequires:	cfitsio-devel
BuildRequires:	chrpath
BuildRequires:	doxygen
BuildRequires:	fontconfig-devel
BuildRequires:	freexl-devel
%if 0%{?g2clib_enabled}
BuildRequires:	g2clib-devel
BuildRequires:	g2clib-static
%endif
BuildRequires:	geos%{geosmajorversion}-devel >= %{geosfullversion}
BuildRequires:	ghostscript
BuildRequires:	jpackage-utils
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 9 || 0%{?suse_version} >= 1499
BuildRequires:	libarchive-devel >= 3.5.0
%endif
%ifnarch %{ppc64le}
%if 0%{?rhel} || 0%{?fedora}
BuildRequires:	libarrow-devel
%endif
BuildRequires:	libdeflate-devel
%endif
# For 'mvn_artifact' and 'mvn_install'
BuildRequires:	libgeotiff%{libgeotiffmajorversion}-devel
BuildRequires:	libjpeg-devel
BuildRequires:	libpng-devel >= 1.6.0
%if 0%{?fedora}
BuildRequires:	libkml-devel
%endif
# PERCONA: PGDG's -16 release floor cannot match our Release 1; the version
# alone pins our geos315-linked libspatialite50.
BuildRequires:	libspatialite%{libspatialitemajorversion}-devel >= %!{GIS_LIBSPATIALITE_VERSION}

BuildRequires:	libtiff-devel >= 4.1
BuildRequires:	libwebp-devel
BuildRequires:	libtool
BuildRequires:	giflib-devel
BuildRequires:	netcdf-devel >= 4.7
%if 0%{?rhel}
BuildRequires:	mariadb-devel
%endif
%if 0%{?fedora}
BuildRequires:	mariadb-connector-c-devel
%endif

# Enable muparser library for VRT expressions
%if 0%{?fedora} >= 42
BuildRequires:	muParser-devel
Requires:	muParser
%endif
%if 0%{?suse_version} == 1500
BuildRequires:	muparser-devel
Requires:	libmuparser2_3_3
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:	muparser-devel
# PERCONA: Tumbleweed ships libmuparser2_3_5; there the automatic soname
# dependency is enough.
%if 0%{?suse_version} == 1600
Requires:	libmuparser2_3_4
%endif
%endif

# PERCONA: libpq from the distro (EL: libpq-devel; SUSE: postgresql-devel,
# resolved on openSUSE:Factory and SUSE:SLFO:1.2), not PGDG's libpq5.
%if 0%{?suse_version}
BuildRequires:	postgresql-devel
%else
BuildRequires:	libpq-devel
%endif
BuildRequires:	pcre2-devel
BuildRequires:	perl(ExtUtils::MakeMaker)
# PERCONA: OBS cannot resolve the %%{_bindir}/pkg-config path form.
BuildRequires:	pkgconfig
%if 0%{?suse_version} >= 1500
BuildRequires:	libpoppler-devel >= 0.86
%else
BuildRequires:	poppler-devel >= 0.86
%endif
BuildRequires:	proj%{projmajorversion}-devel >= 9.4.1

BuildRequires:	sqlite-devel >= 3.31
BuildRequires:	swig
%if %{build_refman}
BuildRequires:	texlive-collection-fontsrecommended
%if 0%{?fedora}
BuildRequires:	texlive-collection-langcyrillic
BuildRequires:	texlive-collection-langportuguese
BuildRequires:	texlive-newunicodechar
%endif
BuildRequires:	texlive-epstopdf
BuildRequires:	tex(multirow.sty)
BuildRequires:	tex(sectsty.sty)
BuildRequires:	tex(tocloft.sty)
BuildRequires:	tex(xtab.sty)
%endif
BuildRequires:	unixODBC-devel

%if 0%{?suse_version} == 1500
BuildRequires:	hdf hdf-devel hdf-devel-static
BuildRequires:	hdf5 hdf5-devel hdf5-devel-static
BuildRequires:	libexpat-devel libjson-c-devel
BuildRequires:	libjasper-devel
BuildRequires:	libxerces-c-devel
BuildRequires:	python311-devel
BuildRequires:	libshp-devel libcurl-devel >= 7.68
BuildRequires:	java-11-openjdk-devel
%endif
# PERCONA: >= 1600 (PGDG: == 1600) so Tumbleweed gets the SLES 16 set.
%if 0%{?suse_version} >= 1600
BuildRequires:	hdf5 hdf5-devel
BuildRequires:	libexpat-devel libjson-c-devel
BuildRequires:	libjasper-devel
BuildRequires:	libxerces-c-devel
BuildRequires:	java-21-openjdk-devel
%endif
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 8
BuildRequires:	libdap-devel
BuildRequires:	expat-devel
BuildRequires:	hdf-devel hdf-static hdf5-devel >= 1.10
BuildRequires:	jasper-devel
%if 0%{?rhel} == 8
BuildRequires:	java-11-openjdk-devel
%else
%if 0%{?rhel} == 9
BuildRequires:	java-17-openjdk-devel
%else
%if 0%{?rhel} == 10
BuildRequires:	java-21-openjdk-devel
%else
BuildRequires:	java-devel >= 1:1.6.0
%endif
%endif
%endif
BuildRequires:	json-c-devel
BuildRequires:	libdap-devel libgta-devel
BuildRequires:	perl-devel
BuildRequires:	perl-generators
BuildRequires:	python3-devel >= 3.8
BuildRequires:	xerces-c-devel
%endif
BuildRequires:	xz-devel
BuildRequires:	zlib-devel
BuildRequires:	libtirpc-devel

BuildRequires:	qhull-devel
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 9
BuildRequires:	SFCGAL-devel >= 2.0.0
%else
%if 0%{?suse_version}
# PERCONA: our common:deps sfcgal is named sfcgal on SUSE (as openSUSE's own).
BuildRequires:	sfcgal-devel
%else
BuildRequires:	SFCGAL-devel
%endif
%endif
%if 0%{?suse_version} == 1500
%endif

BuildRequires:	shapelib-devel curl-devel >= 7.68
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 8 || 0%{?suse_version} >= 1600
BuildRequires:	openjpeg2-devel >= 2.3.1
%endif

# Run time dependencies
Requires:	gpsbabel
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 9
Requires:	libarchive >= 3.5.0
%endif
%if 0%{?suse_version} >= 1499
Requires: libarchive13 >= 3.5.0
%endif
Requires:	%{name}-libs%{?_isa} = %{version}-%{release}


%description
Geospatial Data Abstraction Library (GDAL/OGR) is a cross platform
C++ translator library for raster and vector geospatial data formats.
As a library, it presents a single abstract data model to the calling
application for all supported formats. It also comes with a variety of
useful commandline utilities for data translation and processing.

It provides the primary data access engine for many applications.
GDAL/OGR is the most widely used geospatial data access library.


%package devel
Summary:	Development files for the GDAL file format library
Requires:	%{name}-libs%{?_isa} = %{version}-%{release}

%description devel
This package contains development files for GDAL.


%package libs
Summary:	GDAL file format library
# See frmts/grib/degrib/README.TXT
Provides:	bundled(g2lib) = 1.6.0
Provides:	bundled(degrib) = 2.14
Requires:	geos%{geosmajorversion} >= %{geosfullversion}
Requires:	netcdf >= 4.7 gpsbabel
Requires:	libgeotiff%{libgeotiffmajorversion}
Requires:	libspatialite%{libspatialitemajorversion} >= %!{GIS_LIBSPATIALITE_VERSION}

%if 0%{?suse_version}
%if 0%{?suse_version} <= 1499
Requires:	libarmadillo10
%endif
%endif
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 9
Requires:	armadillo
%endif

%description libs
This package contains the GDAL file format library.

%if %gdaljava
%package java
Summary:	Java modules for the GDAL file format library
Requires:	jpackage-utils
Requires:	%{name}-libs%{?_isa} = %{version}-%{release}

%description java
The GDAL Java modules provide support to handle multiple GIS file formats.


%package javadoc
Summary:	Javadocs for %{name}
Requires:	jpackage-utils
BuildArch:	noarch

%description javadoc
This package contains the API documentation for %{name}.
%endif

%if %gdal_python_enabled
%package python3
%{?py_provide:%py_provide python3-gdal}
Summary:	Python modules for the GDAL file format library
BuildRequires:	python%{python3_pkgversion}-numpy
%if 0%{?suse_version}
# numpy/arrayobject.h
BuildRequires:	python%{python3_pkgversion}-numpy-devel
%endif
BuildRequires:	python%{python3_pkgversion}-devel python%{python3_pkgversion}-setuptools
Requires:	python%{python3_pkgversion}-numpy
Requires:	%{name}-libs%{?_isa} = %{version}-%{release}

%description python3
The GDAL Python 3 modules provide support to handle multiple GIS file formats.


%package python-tools
Summary:	Python tools for the GDAL file format library
Requires:	%{name}-python3

%description python-tools
The GDAL Python package provides number of tools for programming and
manipulating GDAL file format library
%endif

# We don't want to provide private Python extension libs
%global __provides_exclude_from ^(%{python2_sitearch}|%{python3_sitearch})/.*\.so$
%global __provides_exclude_from ^%{python3_sitearch}/.*\.so$

%prep
%setup -q -n %{sname}-%{version}-fedora

%patch -P 0 -p0

# Delete bundled libraries
rm -rf frmts/png/libpng
rm -rf frmts/gif/giflib
rm -rf frmts/jpeg/libjpeg
rm -rf frmts/jpeg/libjpeg12
rm -rf mrf/LERCV1

# Copy in PROVENANCE.TXT-fedora
cp -a %{SOURCE4} .

%build
# Use a newer GCC on SLES 15 to build this version of GDAL:
%if 0%{?suse_version} == 1500
export CC=/usr/bin/gcc-13
export CXX=/usr/bin/g++-13
%endif
%ifarch sparcv9 sparc64 s390 s390x
export CFLAGS="$RPM_OPT_FLAGS -fPIC"
%else
export CFLAGS="$RPM_OPT_FLAGS -fpic"
%endif
export CXXFLAGS="$CFLAGS -I%{projinstdir}/include -I%{libgeotiffinstdir}/include -I%{geosinstdir}/include -I%{libspatialiteinstdir}/include"
export CPPFLAGS="$CPPFLAGS -I%{projinstdir}/include -I%{libgeotiffinstdir}/include -I%{geosinstdir}/include -I%{libspatialiteinstdir}/include"
# SLES 15 has -Itirpc on /usr/include, so use the following only on Fedora and RHEL:
%if 0%{?fedora} >= 30 || 0%{?rhel} >= 9
export CXXFLAGS="$CFLAGS -I%{_includedir}/tirpc"
export CPPFLAGS="$CPPFLAGS -I%{_includedir}/tirpc"
%endif
LDFLAGS="$LDFLAGS -L%{projinstdir}/lib64 -L%{libgeotiffinstdir}/lib -L%{geosinstdir}/lib64 -L%{libspatialiteinstdir}/lib -L%{_libdir} -Wl,-rpath,%{gdalinstdir}/lib:%{projinstdir}/lib64:%{libgeotiffinstdir}/lib:%{geosinstdir}/lib64:%{libspatialiteinstdir}/lib"; export LDFLAGS

# PERCONA: RUNPATH instead of an ld.so.conf.d drop-in. %%cmake may pass
# CMAKE_SKIP_RPATH=ON, so turn it back off. CMAKE_INSTALL_RPATH is one
# colon-joined entry, not a CMake list: the Python bindings rebuild with
# "setup.py build_ext --rpath=<CMAKE_INSTALL_RPATH>" from a generated script
# (swig/python/CMakeLists.txt), where a ';' list would be split into separate
# arguments. PROJ and SpatiaLite are added to CMAKE_PREFIX_PATH so that
# find_package(PROJ CONFIG) finds proj98, never a distro PROJ.
%if 0%{?suse_version}
%if 0%{?suse_version} >= 1500
 %{__install} -d build
 pushd build
 cmake .. -DCMAKE_INSTALL_PREFIX:PATH=%{gdalinstdir} \
%endif
%else
 %cmake -DCMAKE_INSTALL_PREFIX:PATH=%{gdalinstdir} \
%endif
 -DCMAKE_INSTALL_INCLUDEDIR=include \
 -DCMAKE_INSTALL_LIBDIR=lib \
 -DCMAKE_SKIP_RPATH:BOOL=OFF \
 -DCMAKE_SKIP_INSTALL_RPATH:BOOL=OFF \
 -DCMAKE_BUILD_WITH_INSTALL_RPATH:BOOL=ON \
 -DCMAKE_INSTALL_RPATH:STRING="%{gdalinstdir}/lib:%{projinstdir}/lib64:%{libgeotiffinstdir}/lib:%{geosinstdir}/lib64:%{libspatialiteinstdir}/lib" \
 -DHAVE_SPATIALITE=ON \
 -DSPATIALITE_INCLUDE_DIR=%{libspatialiteinstdir}/include \
 -DSPATIALITE_LIBRARY=%{libspatialiteinstdir}/lib/libspatialite.so \
 -DCMAKE_PREFIX_PATH="%{geosinstdir};%{libgeotiffinstdir};%{projinstdir};%{libspatialiteinstdir}" \
 -DGDAL_USE_JPEG12_INTERNAL=OFF \
%if %gdal_python_enabled
  -DBUILD_PYTHON_BINDINGS:BOOL=ON \
  -DPython_ROOT=/usr \
  -DPython_LOOKUP_VERSION=%{pyver} \
%else
 -DBUILD_PYTHON_BINDINGS:BOOL=OFF \
%endif
 -DGDAL_USE_SHAPELIB=OFF \
%if %gdaljava
 -DBUILD_JAVA_BINDINGS=ON \
 -DGDAL_JAVA_INSTALL_DIR=%{_jnidir}/%{name} \
%else
 -DBUILD_JAVA_BINDINGS=OFF \
%endif
 -DSWIG_REGENERATE_PYTHON=OFF \
 -DBUILD_CSHARP_BINDINGS=OFF

%cmake_build

%install
# Use a newer GCC on SLES 15 to install this version of GDAL:
%if 0%{?suse_version} == 1500
export CC=/usr/bin/gcc-13
export CXX=/usr/bin/g++-13
%endif

%cmake_install

touch gdal_python_manpages.txt gdal_python_manpages_excludes.txt
# List of manpages for python scripts
for file in %{buildroot}%{gdalinstdir}/bin/*.py; do
  if [ -f %{buildroot}%{gdalinstdir}/share/man/man1/`basename ${file/.py/.1*}` ]; then
    echo "%{gdalinstdir}/share/man/man1/`basename ${file/.py/.1*}`" >> gdal_python_manpages.txt
    echo "%exclude %{gdalinstdir}/share/man/man1/`basename ${file/.py/.1*}`" >> gdal_python_manpages_excludes.txt
  fi
done

%if %gdal_python_enabled
%{__mkdir} -p %{buildroot}/%{python3_sitearch}/
%{__mv} %{buildroot}/%{gdalinstdir}/lib64/python%{pyver}/site-packages/GDAL-%{version}-py*.egg-info/ %{buildroot}/%{python3_sitearch}/GDAL-%{version}-py*.egg-info/
%{__mv} %{buildroot}/%{gdalinstdir}/lib64/python%{pyver}/site-packages/osgeo %{buildroot}/%{python3_sitearch}/osgeo/
%{__mv} %{buildroot}/%{gdalinstdir}/lib64/python%{pyver}/site-packages/osgeo_utils %{buildroot}/%{python3_sitearch}/osgeo_utils
%endif

# PERCONA: no /etc/ld.so.conf.d drop-in; every ELF under the prefix
# (including the JNI library in %%{gdalinstdir}/lib/jni), the Python
# extension modules and anything under %%{_jnidir} need RUNPATH to GDAL
# itself and to each GIS library it links. Fail if a scanned binding
# directory is missing, so the check cannot pass vacuously.
%if %gdal_python_enabled
test -d %{buildroot}%{python3_sitearch}/osgeo || { echo "PERCONA: %{python3_sitearch}/osgeo missing"; exit 1; }
ls %{buildroot}%{python3_sitearch}/osgeo/_*.so >/dev/null || { echo "PERCONA: no Python extension modules in %{python3_sitearch}/osgeo"; exit 1; }
%endif
%if %gdaljava
test -f %{buildroot}%{gdalinstdir}/lib/jni/libgdalalljni.so || { echo "PERCONA: %{gdalinstdir}/lib/jni/libgdalalljni.so missing"; exit 1; }
%endif
for f in $(find %{buildroot}%{gdalinstdir} %{buildroot}%{python3_sitearch}/osgeo %{buildroot}%{_jnidir} -type f 2>/dev/null); do
  head -c4 "$f" | grep -q 'ELF' || continue
  rp=$(readelf -d "$f" | grep -E '\((RUNPATH|RPATH)\)') || { echo "PERCONA: no RUNPATH in ${f#%{buildroot}}"; exit 1; }
  for d in %{gdalinstdir}/lib %{geosinstdir}/lib64 %{projinstdir}/lib64; do
    echo "$rp" | grep -q "$d" || { echo "PERCONA: RUNPATH of ${f#%{buildroot}} lacks $d"; exit 1; }
  done
done

%files -f gdal_python_manpages_excludes.txt
%dir %{gdalinstdir}
%dir %{gdalinstdir}/bin
%dir %{gdalinstdir}/share
%dir %{gdalinstdir}/share/bash-completion
%dir %{gdalinstdir}/share/bash-completion/completions
%dir %{gdalinstdir}/share/man
%dir %{gdalinstdir}/share/man/man1
%{gdalinstdir}/bin/gdal
%{gdalinstdir}/bin/gdal_contour
%{gdalinstdir}/bin/gdal_create
%{gdalinstdir}/bin/gdal_footprint
%{gdalinstdir}/bin/gdal_grid
%{gdalinstdir}/bin/gdal_rasterize
%{gdalinstdir}/bin/gdal_translate
%{gdalinstdir}/bin/gdal_viewshed
%{gdalinstdir}/bin/gdaladdo
%{gdalinstdir}/bin/gdalbuildvrt
%{gdalinstdir}/bin/gdaldem
%{gdalinstdir}/bin/gdalenhance
%{gdalinstdir}/bin/gdalinfo
%{gdalinstdir}/bin/gdallocationinfo
%{gdalinstdir}/bin/gdalmanage
%{gdalinstdir}/bin/gdalmdiminfo
%{gdalinstdir}/bin/gdalmdimtranslate
%{gdalinstdir}/bin/gdalsrsinfo
%{gdalinstdir}/bin/gdaltindex
%{gdalinstdir}/bin/gdaltransform
%{gdalinstdir}/bin/gdalwarp
%{gdalinstdir}/bin/gnmanalyse
%{gdalinstdir}/bin/gnmmanage
%{gdalinstdir}/bin/nearblack
%{gdalinstdir}/bin/sozip
%if %gdal_python_enabled
%{gdalinstdir}/bin/ogr_layer_algebra*
%endif
%{gdalinstdir}/bin/ogr2ogr
%{gdalinstdir}/bin/ogrinfo
%{gdalinstdir}/bin/ogrlineref
%{gdalinstdir}/bin/ogrtindex
%{gdalinstdir}/share/bash-completion/completions/*
%exclude %{gdalinstdir}/share/bash-completion/completions/*.py
%{gdalinstdir}/share/man/man1/*
%exclude %{gdalinstdir}/share/man/man1/gdal-config.1*
# Python manpages excluded in -f gdal_python_manpages_excludes.txt

%files libs
%dir %{gdalinstdir}
%dir %{gdalinstdir}/lib
%dir %{gdalinstdir}/share
%license LICENSE.TXT
%doc NEWS.md PROVENANCE.TXT COMMITTERS PROVENANCE.TXT-fedora
%{gdalinstdir}/lib/libgdal.so.%{gdalsomajorversion}
%{gdalinstdir}/lib/libgdal.so.%{gdalsomajorversion}.*
%{gdalinstdir}/share/%{sname}/
%{gdalinstdir}/lib/gdalplugins/

%files devel
%dir %{gdalinstdir}
%dir %{gdalinstdir}/bin
%dir %{gdalinstdir}/lib
%dir %{gdalinstdir}/lib/cmake
%dir %{gdalinstdir}/lib/cmake/%{sname}
%dir %{gdalinstdir}/lib/pkgconfig
%{gdalinstdir}/bin/%{sname}-config
%dir %{gdalinstdir}/include/
%{gdalinstdir}/include/*.h
%{gdalinstdir}/include/*.hpp
%{gdalinstdir}/lib/cmake/%{sname}/GDAL*.cmake
%{gdalinstdir}/lib/*.so
%{gdalinstdir}/lib/pkgconfig/%{sname}.pc

%if %gdal_python_enabled
%files python3
%doc swig/python/README.rst
%{python3_sitearch}/GDAL-%{version}-py*.egg-info/
%{python3_sitearch}/osgeo/
%{python3_sitearch}/osgeo_utils/

%files python-tools -f gdal_python_manpages.txt
%dir %{gdalinstdir}
%dir %{gdalinstdir}/bin
%dir %{gdalinstdir}/share
%dir %{gdalinstdir}/share/bash-completion
%dir %{gdalinstdir}/share/bash-completion/completions
%dir %{gdalinstdir}/share/man
%dir %{gdalinstdir}/share/man/man1
%{gdalinstdir}/bin/gdal_calc*
%{gdalinstdir}/bin/gdal_edit*
%{gdalinstdir}/bin/gdal_fillnodata*
%{gdalinstdir}/bin/gdal_merge*
%{gdalinstdir}/bin/gdal_pansharpen*
%{gdalinstdir}/bin/gdal_polygonize*
%{gdalinstdir}/bin/gdal_proximity*
%{gdalinstdir}/bin/gdal_retile*
%{gdalinstdir}/bin/gdal_sieve*
%{gdalinstdir}/bin/gdal2tiles*
%{gdalinstdir}/bin/gdal2xyz*
%{gdalinstdir}/bin/gdalattachpct*
%{gdalinstdir}/bin/gdalcompare*
%{gdalinstdir}/bin/gdalmove*
%{gdalinstdir}/bin/ogrmerge*
%{gdalinstdir}/bin/pct2rgb*
%{gdalinstdir}/bin/rgb2pct*
%{gdalinstdir}/share/bash-completion/completions/*.py
%endif

%if %gdaljava
%files java
%dir %{gdalinstdir}
%dir %{gdalinstdir}/lib
%dir %{gdalinstdir}/lib/jni
%dir %{_jnidir}/%{name}
%{_jnidir}/%{name}/gdal-%{version}-sources.jar
%{_jnidir}/%{name}/gdal-%{version}.jar
%{_jnidir}/%{name}/gdal-%{version}.pom
%{gdalinstdir}/lib/jni/libgdalalljni.so

%files javadoc
%dir %{_jnidir}/%{name}
%{_jnidir}/%{name}/gdal-%{version}-javadoc.jar
%endif

%changelog
* Fri Oct 16 2026 Percona Development <info@percona.com> - 3.13.3-1
- Ported from PGDG pgdg-rpms e38918e8; no ld.so.conf.d drop-in, RUNPATH instead

* Fri Oct 16 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-6PGDG
- Update download URL

* Mon Oct 12 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-5PGDG
- Rebuild against GEOS 3.15. Per
  https://github.com/pgdg-packaging/pgdg-rpms/issues/359

* Mon Oct 5 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-4PGDG
- Embed the PROJ, GeOS, libgeotiff and SpatiaLite library paths as
  rpaths, so that GDAL uses GeOS 3.14 also when other GeOS versions are
  installed: they were passed in SHLIB_LINK, which CMake ignores.
- Require the GeOS package that we build against.
- Build against and require libspatialite50 5.1.0-16 or later, which
  uses GeOS 3.14 also when other GeOS versions are installed.
- Add the numpy-devel BuildRequires on SUSE, which has the numpy headers
  that the Python bindings need.
- Add the gcc13 BuildRequires on SLES 15, where the package is built
  with GCC 13.

* Mon Aug 31 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-3PGDG
- Pin java-11/17/21-openjdk-devel BuildRequires on RHEL 8/9/10
  respectively, instead of the unversioned java-devel, which resolves
  to the outdated default JDK 8 on RHEL 8. Per
  https://github.com/pgdg-packaging/pgdg-rpms/issues/110

* Tue Aug 25 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-2PGDG
- Set python3_pkgversion/__ospython for Amazon Linux 2023 (python3.13),
  to keep the Python stack consistent across all packages in the repo.
  Note: gdal_python_enabled still doesn't cover amzn, so this has no
  effect until that's revisited separately.

* Tue Aug 18 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.3-1PGDG
- Update to 3.13.3 per changes described at:
  https://github.com/OSGeo/gdal/releases/tag/v3.13.3

* Wed Jul 22 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.2-1PGDG
- Update to 3.13.2 per changes described at:
  https://github.com/OSGeo/gdal/releases/tag/v3.13.2

* Sat Jun 6 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.1-1PGDG
- Update to 3.13.1 per changes described at:
  https://github.com/OSGeo/gdal/releases/tag/v3.13.1

* Wed May 13 2026 Devrim Gunduz <devrim@gunduz.org> - 3.13.0-1PGDG
- Initial 3.13.0 packaging per changes described at:
  https://github.com/OSGeo/gdal/releases/tag/v3.13.0
  Check the migration guide:
  https://gdal.org/en/latest/user/migration_guide.html#from-gdal-3-12-to-gdal-3-13
