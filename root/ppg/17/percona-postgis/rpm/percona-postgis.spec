%undefine _debugsource_packages
%global postgismajorversion 3.5
%global postgisminorversion 5
%global postgissomajorversion 3
%define pgmajorversion %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 9
%global gts_version 14
%endif
%global postgiscurrmajorversion %(echo %{postgismajorversion}|tr -d '.')
%global sname	postgis

%define pginstdir /usr/pgsql-%{pgmajorversion}/

#%pgdg_set_gis_variables

# Override some variables. PostGIS 3.3 is best served with GeOS 3.11,
# GDAL 3.4 and PROJ 9.0:
%if 0%{?rhel} && 0%{?rhel} == 10
%global geosfullversion 3.13.1
%global geosmajorversion 313
%global geosinstdir /usr/geos%{geosmajorversion}
%global gdalfullversion 3.11.3
%global gdalmajorversion 311
%global gdalinstdir /usr/gdal%{gdalmajorversion}
%global projmajorversion 96
%global projfullversion 9.6.2
%global projinstdir /usr/proj%{projmajorversion}
%endif

%if 0%{?rhel} && 0%{?rhel} == 9
# Using EPEL/CRB packages (non-PGDG build environment)
%global geosfullversion 3.13.1
%global geosinstdir /usr
%global gdalfullversion 3.4.3
%global gdalinstdir /usr
%global projfullversion 9.6.0
%global projinstdir /usr
%global libgeotiffmajorversion %{nil}
%global libgeotiffinstdir /usr
%endif

%if 0%{?rhel} && 0%{?rhel} == 8
%global geosfullversion 3.11.2
%global geosmajorversion 311
%global geosinstdir /usr/geos%{geosmajorversion}
%global gdalfullversion 3.8.5
%global gdalmajorversion 38
%global gdalinstdir /usr/gdal%{gdalmajorversion}
%global projmajorversion 95
%global projfullversion 9.5.1
%global projinstdir /usr/proj%{projmajorversion}
%endif


%if 0%{?suse_version} >= 1600
# openSUSE Leap 16 / Tumbleweed: use standard unversioned package names (no PGDG versioned suffixes)
%global geosfullversion 3.11.0
%global geosinstdir /usr
%global geosmajorversion %{nil}
%global projfullversion 9.0.0
%global projinstdir /usr
%global projmajorversion %{nil}
%global libgeotiffinstdir /usr
%global libgeotiffmajorversion %{nil}
%global gdalfullversion 3.0.0
%global gdalinstdir /usr
%global gdalmajorversion %{nil}
%global libspatialiteinstdir /usr
%endif

# Override PROJ major version on RHEL 7.
# libspatialite 4.3 does not build against 8.0.0 as of March 2021.
# Also use GDAL 3.4
%if 0%{?rhel} && 0%{?rhel} == 7
%global gdalfullversion 3.3.3
%global gdalmajorversion 33
%global gdalinstdir /usr/gdal%{gdalmajorversion}
%global projmajorversion 72
%global projfullversion 7.2.1
%global projinstdir /usr/proj%{projmajorversion}
%endif

%if 0%{?rhel} == 7 || 0%{?suse_version} >= 1315
%global libspatialitemajorversion	43
%else
%global libspatialitemajorversion	50
%endif

%ifarch ppc64 ppc64le s390 s390x armv7hl
 %if 0%{?rhel} && 0%{?rhel} == 7
  %{!?llvm:%global llvm 0}
 %else
  %{!?llvm:%global llvm 1}
 %endif
%else
 %{!?llvm:%global llvm 1}
%endif

%{!?utils:%global	utils 1}
%{!?shp2pgsqlgui:%global	shp2pgsqlgui 1}
%if 0%{?suse_version} >= 1315
%{!?raster:%global     raster 0}
%else
%{!?raster:%global     raster 1}
%endif

%if 0%{?fedora} >= 41 || 0%{?rhel} >= 7 || 0%{?suse_version} >= 1500
%ifnarch ppc64 ppc64le
# TODO
%{!?sfcgal:%global     sfcgal 1}
%else
%{!?sfcgal:%global     sfcgal 0}
%endif
%else
%{!?sfcgal:%global    sfcgal 0}
%endif

Summary:	Geographic Information Systems Extensions to PostgreSQL
Name:		percona-postgis%{postgiscurrmajorversion}_%{pgmajorversion}
Version:	1.0.0
Release:	1%{?dist}
License:	GPLv2+
Source0:	percona-postgis-%{version}.tar.gz
Source2:        postgis.pdf
Source4:	%{sname}%{postgissomajorversion}-filter-requires-perl-Pg.sh

URL:		https://www.postgis.net/

BuildRequires:	percona-postgresql%{pgmajorversion}-devel libxml2 libxslt autoconf automake libtool gmp-devel pcre2-devel gcc gcc-c++
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?rhel} && 0%{?rhel} == 9
BuildRequires:	geos-devel libgeotiff-devel
%else
BuildRequires:	geos%{geosmajorversion}-devel >= %{geosfullversion}
BuildRequires:	libgeotiff%{libgeotiffmajorversion}-devel
%if !0%{?suse_version}
BuildRequires:	pgdg-srpm-macros >= 1.0.53
%endif
%endif
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 8
Requires:       pcre2
%else
Requires:       libpcre2-8-0
%endif
%if 0%{?suse_version} >= 1500
Requires:	libgmp10
%else
Requires:	gmp
%endif
%if 0%{?suse_version}
%if 0%{?suse_version} >= 1500
BuildRequires:	libjson-c-devel proj%{projmajorversion}-devel >= %{projfullversion}
%endif
%else
%if 0%{?rhel} && 0%{?rhel} == 9
BuildRequires:	proj-devel flex json-c-devel
%else
BuildRequires:	proj%{projmajorversion}-devel >= %{projfullversion} flex json-c-devel
%endif
%endif
BuildRequires:	libxml2-devel
%if %{shp2pgsqlgui}
BuildRequires:	gtk2-devel > 2.8.0
%endif
%if %{sfcgal}
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 9
BuildRequires:	SFCGAL SFCGAL-devel >= 2.1.0
%endif
%if 0%{?rhel} == 8
BuildRequires:        SFCGAL SFCGAL-devel
%endif
%if 0%{?suse_version} >= 1500 && 0%{?suse_version} < 1600
BuildRequires:        SFCGAL SFCGAL-devel
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:        sfcgal sfcgal-devel
%endif
%endif

%if %{raster}
%if 0%{?rhel} && 0%{?rhel} == 9
BuildRequires:	gdal3.4-devel
Requires:	gdal3.4-libs
%else
BuildRequires:	gdal%{gdalmajorversion}-devel >= %{gdalfullversion}
Requires:	gdal%{gdalmajorversion}-libs >= %{gdalfullversion}
%endif
%endif

%if 0%{?suse_version} >= 1500
Requires:	libprotobuf-c1
BuildRequires:	libprotobuf-c-devel
%else
# Fedora/RHEL:
Requires:	protobuf-c >= 1.1.0
BuildRequires:	protobuf-c-devel >= 1.1.0
%endif

Requires:	percona-postgresql%{pgmajorversion}
Requires:	percona-postgresql%{pgmajorversion}-contrib
Requires:	hdf5
%if 0%{?rhel} && 0%{?rhel} == 9
Requires:	geos proj libgeotiff gdal3.4-libs
%else
Requires:	geos%{geosmajorversion} >= %{geosfullversion}
Requires:	proj%{projmajorversion} >= %{projfullversion}
Requires:	libgeotiff%{libgeotiffmajorversion}
%if %{raster}
Requires:	gdal%{gdalmajorversion}-libs >= %{gdalfullversion}
%endif
%endif

%if 0%{?suse_version} >= 1500 && 0%{?suse_version} < 1600
Requires:	libjson-c5
Requires:	libxerces-c-3_2
BuildRequires:        libxerces-c-devel
%endif
%if 0%{?suse_version} >= 1600
Requires:        libjson-c5
BuildRequires:        libxerces-c-devel
%endif
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 8
Requires:	json-c xerces-c
BuildRequires:  xerces-c-devel
%endif
Requires(post):	%{_sbindir}/update-alternatives

Provides:	%{sname} = %{version}-%{release}
Obsoletes:	%{sname}3_%{pgmajorversion} <= %{postgismajorversion}.0-1
Provides:	%{sname}3_%{pgmajorversion} => %{postgismajorversion}.0

%description
PostGIS adds support for geographic objects to the PostgreSQL object-relational
database. In effect, PostGIS "spatially enables" the PostgreSQL server,
allowing it to be used as a backend spatial database for geographic information
systems (GIS), much like ESRI's SDE or Oracle's Spatial extension. PostGIS
follows the OpenGIS "Simple Features Specification for SQL" and has been
certified as compliant with the "Types and Functions" profile.

%package client
Summary:	Client tools and their libraries of PostGIS
Requires:	%{name}%{?_isa} = %{version}-%{release}
Provides:	%{sname}-client = %{version}-%{release}
Obsoletes:	%{sname}2_%{pgmajorversion}-client <= %{postgismajorversion}.2-1
Provides:	%{sname}2_%{pgmajorversion}-client => %{postgismajorversion}.0

%description client
The %{name}-client package contains the client tools and their libraries
of PostGIS.

%if %{sfcgal}
%package devel
Summary:	Development headers and libraries for PostGIS
Requires:	%{name}%{?_isa} = %{version}-%{release}
Provides:	%{sname}-devel = %{version}-%{release}
Obsoletes:	%{sname}2_%{pgmajorversion}-devel <= %{postgismajorversion}.2-1
Provides:	%{sname}2_%{pgmajorversion}-devel => %{postgismajorversion}.0

%description devel
The %{name}-devel package contains the header files and libraries
needed to compile C or C++ applications which will directly interact
with PostGIS.
%endif

%package docs
Summary:	Extra documentation for PostGIS
Obsoletes:	%{sname}2_%{pgmajorversion}-docs <= %{postgismajorversion}.2-1
Provides:	%{sname}2_%{pgmajorversion}-docs => %{postgismajorversion}.0

%description docs
The %{name}-docs package includes PDF documentation of PostGIS.

%if %{shp2pgsqlgui}
%package	gui
Summary:	GUI for PostGIS
Requires:	%{name}%{?_isa} = %{version}-%{release}

%description	gui
The %{name}-gui package provides a gui for PostGIS.
%endif

%if %utils
%package utils
Summary:	The utils for PostGIS
Requires:	%{name} = %{version}-%{release} perl-DBD-Pg
Provides:	%{sname}-utils = %{version}-%{release}
Obsoletes:	%{sname}2_%{pgmajorversion}-utils <= %{postgismajorversion}.2-1
Provides:	%{sname}2_%{pgmajorversion}-utils => %{postgismajorversion}.0

%description utils
The %{name}-utils package provides the utilities for PostGIS.
%endif

%global __perl_requires %{SOURCE4}

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for postgis35
Requires:	%{name}%{?_isa} = %{version}-%{release}
%if 0%{?suse_version} == 1500
BuildRequires:  llvm17-devel clang17-devel
Requires:	llvm17
%endif
%if 0%{?suse_version} == 1600
BuildRequires:  llvm19-devel clang19-devel
Requires:	llvm19
%endif
%if 0%{?suse_version} > 1600
BuildRequires:	clang llvm
Requires:	llvm
%endif
%if 0%{?fedora} || 0%{?rhel} >= 8
BuildRequires:	clang llvm
Requires:	llvm >= 19.0
%endif

%description llvmjit
This packages provides JIT support for postgis35
%endif


%prep
%setup -q -n percona-postgis-%{version}
%{__cp} -p %{SOURCE2} .
%{__mv} postgis.pdf %{sname}-%{version}.pdf

%build
LDFLAGS="-Wl,-rpath,%{geosinstdir}/lib64 ${LDFLAGS}" ; export LDFLAGS
LDFLAGS="-Wl,-rpath,%{projinstdir}/lib64 ${LDFLAGS}" ; export LDFLAGS
LDFLAGS="-Wl,-rpath,%{libspatialiteinstdir}/lib ${LDFLAGS}" ; export LDFLAGS
SHLIB_LINK="$SHLIB_LINK -Wl,-rpath,%{geosinstdir}/lib64" ; export SHLIB_LINK
SFCGAL_LDFLAGS="$SFCGAL_LDFLAGS -L/usr/lib64"; export SFCGAL_LDFLAGS
LDFLAGS="$LDFLAGS -L%{geosinstdir}/lib64 -lgeos_c -L%{projinstdir}/lib64 -L%{gdalinstdir}/lib -L%{libgeotiffinstdir}/lib -ltiff -L/usr/lib64"; export LDFLAGS
CFLAGS="$CFLAGS -I%{gdalinstdir}/include"; export CFLAGS
export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:%{projinstdir}/lib64/pkgconfig
export PATH=/usr/bin:$PATH
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
export ACLOCAL=aclocal
export AUTOMAKE=automake
export AUTOCONF=autoconf
sh -x autogen.sh
autoconf

%configure --with-pgconfig=%{pginstdir}/bin/pg_config \
        --bindir=%{pginstdir}/bin/ \
	      --datadir=%{pginstdir}/share/ \
	      --mandir=%{_mandir}/%{name} \
        --enable-lto \
        --with-projdir=%{projinstdir} \
%if !%raster
        --without-raster \
%endif
%if %{sfcgal}
	--with-sfcgal=%{_bindir}/sfcgal-config \
%endif
%if %{shp2pgsqlgui}
	--with-gui \
%endif
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 8  || 0%{?suse_version} >= 1500
	--with-protobuf \
%else
	--without-protobuf \
%endif
	--enable-rpath --libdir=%{pginstdir}/lib \
	--with-geosconfig=%{geosinstdir}/bin/geos-config \
	--with-gdalconfig=%{gdalinstdir}/bin/gdal-config

SHLIB_LINK="$SHLIB_LINK" %{__make} LPATH=`%{pginstdir}/bin/pg_config --pkglibdir` shlib="%{sname}-%{postgissomajorversion}.so"

%{__make} %{?_smp_mflags} -C extensions

%if %utils
 SHLIB_LINK="$SHLIB_LINK" %{__make} %{?_smp_mflags} -C utils
%endif

%install
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
%{__rm} -rf %{buildroot}
SHLIB_LINK="$SHLIB_LINK" %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot}

%if %utils
%{__install} -d %{buildroot}%{_datadir}/%{name}
%{__install} -m 644 utils/*.pl %{buildroot}%{_datadir}/%{name}
%endif

# Create alternatives entries for common binaries
%post client
%{_sbindir}/update-alternatives --install %{_bindir}/pgsql2shp postgis-pgsql2shp %{pginstdir}/bin/pgsql2shp %{pgmajorversion}0
%{_sbindir}/update-alternatives --install %{_bindir}/shp2pgsql postgis-shp2pgsql %{pginstdir}/bin/shp2pgsql %{pgmajorversion}0

# Drop alternatives entries for common binaries and man files
%postun client
if [ "$1" -eq 0 ]
  then
	# Only remove these links if the package is completely removed from the system (vs.just being upgraded)
	%{_sbindir}/update-alternatives --remove postgis-pgsql2shp	%{_bindir}/bin/pgsql2shp
	%{_sbindir}/update-alternatives --remove postgis-shp2pgsql	%{_bindir}/bin/shp2pgsql
fi

%clean
%{__rm} -rf %{buildroot}

%files
%defattr(-,root,root)
%doc COPYING CREDITS NEWS TODO README.%{sname} doc/html loader/README.* doc/%{sname}.xml doc/ZMSgeoms.txt
%license LICENSE.TXT
%dir %{pginstdir}lib
%dir %{pginstdir}share
%dir %{pginstdir}share/contrib
%dir %{pginstdir}share/contrib/%{sname}-%{postgismajorversion}
%dir %{pginstdir}share/extension
%dir %{_mandir}/%{name}/man1
%{pginstdir}/bin/postgis
%{pginstdir}/bin/postgis_restore
%{pginstdir}/doc/extension/README.address_standardizer
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/postgis.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/postgis_comments.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/postgis_upgrade*.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/uninstall_postgis.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/legacy*.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/*topology*.sql
%{pginstdir}/lib/%{sname}-%{postgissomajorversion}.so
%{pginstdir}/share/extension/%{sname}-*.sql
%if %{sfcgal}
%{pginstdir}/lib/%{sname}_sfcgal-%{postgissomajorversion}.so
%{pginstdir}/share/extension/%{sname}_sfcgal*.sql
%{pginstdir}/share/extension/%{sname}_sfcgal.control
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/sfcgal.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/sfcgal_upgrade.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/uninstall_sfcgal.sql
%endif
%{pginstdir}/share/extension/%{sname}.control
%{pginstdir}/lib/%{sname}_topology-%{postgissomajorversion}.so
%{pginstdir}/lib/address_standardizer-3.so
%{pginstdir}/share/extension/address_standardizer*.sql
%{pginstdir}/share/extension/address_standardizer*.control
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/sfcgal_comments.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/raster_comments.sql
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/spatial*.sql
%{pginstdir}/share/extension/%{sname}_tiger_geocoder*.sql
%{pginstdir}/share/extension/%{sname}_tiger_geocoder.control
%{pginstdir}/share/extension/%{sname}_topology-*.sql
%{pginstdir}/share/extension/%{sname}_topology.control
%{pginstdir}/share/contrib/%{sname}-%{postgismajorversion}/uninstall_legacy.sql
%if %{raster}
%{pginstdir}/share/contrib/postgis-%{postgismajorversion}/rtpostgis.sql
%{pginstdir}/share/contrib/postgis-%{postgismajorversion}/rtpostgis_legacy.sql
%{pginstdir}/share/contrib/postgis-%{postgismajorversion}/rtpostgis_upgrade.sql
%{pginstdir}/share/contrib/postgis-%{postgismajorversion}/uninstall_rtpostgis.sql
%{pginstdir}/share/extension/postgis_raster*.sql
%{pginstdir}/lib/postgis_raster-%{postgissomajorversion}.so
%{pginstdir}/share/extension/%{sname}_raster.control
%endif
%{_mandir}/%{name}/man1/postgis.1*
%{_mandir}/%{name}/man1/postgis_restore.1*

%files client
%defattr(644,root,root)
%dir %{_mandir}/%{name}
%attr(755,root,root) %{pginstdir}/bin/pgsql2shp
%if %{raster}
%attr(755,root,root) %{pginstdir}/bin/raster2pgsql
%endif
%attr(755,root,root) %{pginstdir}/bin/shp2pgsql
%attr(755,root,root) %{pginstdir}/bin/pgtopo_export
%attr(755,root,root) %{pginstdir}/bin/pgtopo_import
%{_mandir}/%{name}/man1/pgsql2shp*
%{_mandir}/%{name}/man1/pgtopo_*
%{_mandir}/%{name}/man1/shp2pgsql*

%if %{sfcgal}
%files devel
%defattr(644,root,root)
%dir %{pginstdir}lib
%dir %{pginstdir}lib/bitcode
%dir %{pginstdir}lib/bitcode/postgis_sfcgal-3
%{pginstdir}/lib/bitcode/postgis_sfcgal-3/postgis_sfcgal_legacy.bc
%endif

%files docs
%defattr(-,root,root)
%doc %{sname}-%{version}.pdf

%if %shp2pgsqlgui
%files gui
%defattr(-,root,root)
%dir %{pginstdir}share
%dir %{pginstdir}share/applications
%dir %{pginstdir}share/icons
%dir %{pginstdir}share/icons/hicolor
%dir %{pginstdir}share/icons/hicolor/8x8
%dir %{pginstdir}share/icons/hicolor/8x8/apps
%dir %{pginstdir}share/icons/hicolor/16x16
%dir %{pginstdir}share/icons/hicolor/16x16/apps
%dir %{pginstdir}share/icons/hicolor/22x22
%dir %{pginstdir}share/icons/hicolor/22x22/apps
%dir %{pginstdir}share/icons/hicolor/24x24
%dir %{pginstdir}share/icons/hicolor/24x24/apps
%dir %{pginstdir}share/icons/hicolor/32x32
%dir %{pginstdir}share/icons/hicolor/32x32/apps
%dir %{pginstdir}share/icons/hicolor/36x36
%dir %{pginstdir}share/icons/hicolor/36x36/apps
%dir %{pginstdir}share/icons/hicolor/40x40
%dir %{pginstdir}share/icons/hicolor/40x40/apps
%dir %{pginstdir}share/icons/hicolor/42x42
%dir %{pginstdir}share/icons/hicolor/42x42/apps
%dir %{pginstdir}share/icons/hicolor/48x48
%dir %{pginstdir}share/icons/hicolor/48x48/apps
%dir %{pginstdir}share/icons/hicolor/64x64
%dir %{pginstdir}share/icons/hicolor/64x64/apps
%{pginstdir}/bin/shp2pgsql-gui
%{pginstdir}/share/applications/shp2pgsql-gui.desktop
%{pginstdir}/share/icons/hicolor/*/apps/shp2pgsql-gui.png
%endif

%if %llvm
%files llvmjit
%dir %{pginstdir}lib
%dir %{pginstdir}lib/bitcode
%dir %{pginstdir}lib/bitcode/address_standardizer-3
%dir %{pginstdir}lib/bitcode/postgis-%{postgissomajorversion}
%dir %{pginstdir}lib/bitcode/postgis_topology-%{postgissomajorversion}
   %{pginstdir}/lib/bitcode/address_standardizer*.bc
   %{pginstdir}/lib/bitcode/address_standardizer-3/*.bc
   %{pginstdir}/lib/bitcode/postgis-%{postgissomajorversion}*.bc
   %{pginstdir}/lib/bitcode/postgis_topology-%{postgissomajorversion}/*.bc
   %{pginstdir}/lib/bitcode/postgis_topology-%{postgissomajorversion}*.bc
   %{pginstdir}/lib/bitcode/postgis-%{postgissomajorversion}/*.bc
   %if %raster
    %{pginstdir}/lib/bitcode/postgis_raster-%{postgissomajorversion}*.bc
    %{pginstdir}/lib/bitcode/postgis_raster-%{postgissomajorversion}/*.bc
   %endif
   %if %{sfcgal}
   %dir %{pginstdir}lib/bitcode/postgis_sfcgal-%{postgissomajorversion}
   %{pginstdir}/lib/bitcode/postgis_sfcgal-%{postgissomajorversion}.index.bc
   %{pginstdir}/lib/bitcode/postgis_sfcgal-%{postgissomajorversion}/lwgeom_sfcgal.bc
   %endif
%endif

%if %utils
%files utils
%defattr(-,root,root)
%doc utils/README
%dir %{_datadir}/%{name}
%attr(755,root,root) %{_datadir}/%{name}/*.pl
%endif

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{POSTGIS_VERSION}-1
- Update to upstream version %!{POSTGIS_VERSION}
