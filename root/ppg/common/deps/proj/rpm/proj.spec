%if 0%{?fedora}
%bcond_without mingw
%else
%bcond_with mingw
%endif

%global data_version 1.21
Name:           proj
# Also check whether there is a new proj-data release when upgrading!
Version:        9.6.0
Release:        1%{?dist}
Summary:        Cartographic projection software (PROJ)

License:        MIT
URL:            https://proj.org
Source0:        proj-%{version}.tar.gz
Source1:        proj-data-%{data_version}.tar.gz

Patch0:         0001-Remove-RPATH.patch
Patch1:         proj_build.patch

BuildRequires:  cmake
BuildRequires:  curl-devel
BuildRequires:  gcc-c++
%if 0%{?fedora}
BuildRequires:  gmock-devel
BuildRequires:  gtest-devel >= 1.8.0
%endif
BuildRequires:  make
BuildRequires:  libtiff-devel
BuildRequires:  sqlite-devel

%if %{with mingw}
BuildRequires: mingw32-curl
BuildRequires: mingw32-filesystem >= 95
BuildRequires: mingw32-gcc-c++
BuildRequires: mingw32-libtiff
BuildRequires: mingw32-sqlite

BuildRequires: mingw64-curl
BuildRequires: mingw64-filesystem >= 95
BuildRequires: mingw64-gcc-c++
BuildRequires: mingw64-libtiff
BuildRequires: mingw64-sqlite
%endif

%if 0%{?fedora}
Obsoletes:      proj-datumgrid < 1.8-6.3.2.6
%endif

Requires:       proj-data = %{version}-%{release}

%description
Proj and invproj perform respective forward and inverse transformation of
cartographic data to or from cartesian data with a wide range of selectable
projection functions.


%package devel
Summary:        Development files for PROJ
Requires:       %{name}%{?_isa} = %{version}-%{release}
%if 0%{?fedora}
Obsoletes:      %{name}-static < 7.2.0
%endif

%description devel
This package contains libproj and the appropriate header files and man pages.


%package data
Summary:        Proj data files
BuildArch:      noarch

%description data
Proj arch independent data files.


%if 0%{?fedora}
%package data-europe
Summary:        Compat package for old proj-datumgrid-europe
BuildArch:      noarch
Obsoletes:      proj-datumgrid-europe < 1.6-3
Provides:       deprecated()
Requires:       proj-data-at
Requires:       proj-data-be
Requires:       proj-data-ch
Requires:       proj-data-cz
Requires:       proj-data-de
Requires:       proj-data-dk
Requires:       proj-data-es
Requires:       proj-data-eur
Requires:       proj-data-fi
Requires:       proj-data-fo
Requires:       proj-data-fr
Requires:       proj-data-hu
Requires:       proj-data-is
Requires:       proj-data-nl
Requires:       proj-data-pl
Requires:       proj-data-pt
Requires:       proj-data-se
Requires:       proj-data-si
Requires:       proj-data-sk
Requires:       proj-data-uk

%description data-europe
Compat package for old proj-datumgrid-europe.
Please do not depend on this package, it will get removed!

%files data-europe


%package data-north-america
Summary:        Compat package for old proj-datumgrid-north-america
BuildArch:      noarch
Obsoletes:      proj-datumgrid-north-america < 1.4-3
Provides:       deprecated()
Requires:       proj-data-ca
Requires:       proj-data-us

%description data-north-america
Compat package for old proj-datumgrid-north-america.
Please do not depend on this package, it will get removed!

%files data-north-america


%package data-oceania
Summary:        Compat package for old proj-datumgrid-oceania
BuildArch:      noarch
Obsoletes:      proj-datumgrid-oceania < 1.2-3
Provides:       deprecated()
Requires:       proj-data-au
Requires:       proj-data-nc
Requires:       proj-data-nz

%description data-oceania
Compat package for old proj-datumgrid-oceania.
Please do not depend on this package, it will get removed!

%files data-oceania


%package data-world
Summary:        Compat package for old proj-datumgrid-world
BuildArch:      noarch
Obsoletes:      proj-datumgrid-world < 1.0-5
Provides:       deprecated()
Requires:       proj-data-br
Requires:       proj-data-jp

%description data-world
Compat package for old proj-datumgrid-world.
Please do not depend on this package, it will get removed!

%files data-world
%endif


# TODO: why the \ cruft in this section?
%define data_subpkg(c:n:e:s:) \
%define countrycode %{-c:%{-c*}}%{!-c:%{error:Country code not defined}} \
%define countryname %{-n:%{-n*}}%{!-n:%{error:Country name not defined}} \
%define extrafile %{-e:%{_datadir}/%{name}/%{-e*}} \
%define wildcard %{!-s:%{_datadir}/%{name}/%{countrycode}_*} \
\
%package data-%{countrycode}\
Summary:      %{countryname} datum grids for Proj\
BuildArch:    noarch\
# See README.DATA \
License:      CC-BY-4.0 OR CC-BY-SA-4.0 OR MIT OR BSD-2-Clause OR CC0-1.0\
Requires:     proj-data = %{version}-%{release} \
Supplements:  proj\
\
%description data-%{countrycode}\
%{countryname} datum grids for Proj.\
\
%files data-%{countrycode}\
%{wildcard}\
%{extrafile}


%data_subpkg -c ar -n Argentina
%data_subpkg -c at -n Austria
%data_subpkg -c au -n Australia
%data_subpkg -c be -n Belgium
%data_subpkg -c br -n Brasil
%data_subpkg -c ca -n Canada
%data_subpkg -c ch -n Switzerland -e CH
%data_subpkg -c cz -n Czech
%data_subpkg -c de -n Germany
%data_subpkg -c dk -n Denmark -e DK
%data_subpkg -c es -n Spain
%data_subpkg -c eur -n %{quote:Nordic + Baltic} -e NKG
%data_subpkg -c fi -n Finland
%data_subpkg -c fo -n %{quote:Faroe Island} -e FO -s 1
%data_subpkg -c fr -n France
%data_subpkg -c hu -n Hungary
%data_subpkg -c is -n Island -e ISL
%data_subpkg -c jp -n Japan
%data_subpkg -c lv -n Latvia
%data_subpkg -c mx -n Mexico
%data_subpkg -c no -n Norway
%data_subpkg -c nc -n %{quote:New Caledonia}
%data_subpkg -c nl -n Netherlands
%data_subpkg -c nz -n %{quote:New Zealand}
%data_subpkg -c pl -n Poland
%data_subpkg -c pt -n Portugal
%data_subpkg -c se -n Sweden
%data_subpkg -c sk -n Slovakia
%data_subpkg -c si -n Slovenia
%data_subpkg -c uk -n %{quote:United Kingdom}
%data_subpkg -c us -n %{quote:United States}
%data_subpkg -c za -n %{quote:South Africa}


%if %{with mingw}
%package -n mingw32-%{name}
Summary:       Cartographic projection software (PROJ.4)
Obsoletes:     mingw32-%{name}-static < 6.3.2-3
BuildArch:     noarch

%description -n mingw32-%{name}
Proj and invproj perform respective forward and inverse transformation of
cartographic data to or from cartesian data with a wide range of selectable
projection functions. Proj docs: http://www.remotesensing.org/dl/new_docs/


%package -n mingw64-%{name}
Summary:       Cartographic projection software (PROJ.4)
Obsoletes:     mingw64-%{name}-static < 6.3.2-3
BuildArch:     noarch


%description -n mingw64-%{name}
Proj and invproj perform respective forward and inverse transformation of
cartographic data to or from cartesian data with a wide range of selectable
projection functions. Proj docs: http://www.remotesensing.org/dl/new_docs/


%{?mingw_debug_package}
%endif


%prep
%autosetup -p1


%build
# Native build
%if 0%{?fedora}
%cmake -DUSE_EXTERNAL_GTEST=ON
%else
%cmake -DBUILD_TESTING=OFF
%endif
%cmake_build

%if %{with mingw}
# MinGW build
%mingw_cmake -DBUILD_TESTING=OFF
%mingw_make_build
%endif


%install
%cmake_install
%if %{with mingw}
%mingw_make_install
%endif

# Install data
# obs_scm tarballs place files under a <filename>-<version>/ prefix, so
# --strip-components=1 is needed to land them directly in the data directory.
mkdir -p %{buildroot}%{_datadir}/%{name}
tar -xf %{SOURCE1} --strip-components=1 --directory %{buildroot}%{_datadir}/%{name}

%if %{with mingw}
rm -rf %{buildroot}%{mingw32_docdir}
rm -rf %{buildroot}%{mingw32_mandir}
rm -rf %{buildroot}%{mingw64_docdir}
rm -rf %{buildroot}%{mingw64_mandir}

rm -rf %{buildroot}%{mingw32_datadir}/bash-completion
rm -rf %{buildroot}%{mingw64_datadir}/bash-completion

%mingw_debug_install_post
%endif


%if 0%{?fedora}
%check
# nkg test requires internet connection
%ctest -E nkg
%endif


%files
%{_bindir}/cct
%{_bindir}/cs2cs
%{_bindir}/geod
%{_bindir}/gie
%{_bindir}/invgeod
%{_bindir}/invproj
%{_bindir}/proj
%{_bindir}/projinfo
%{_bindir}/projsync
%{_libdir}/libproj.so.25*
%{_datadir}/bash-completion/completions/projinfo

%files devel
%{_includedir}/*.h
%{_includedir}/proj/
%{_libdir}/libproj.so
%{_libdir}/cmake/proj/
%{_libdir}/cmake/proj4/
%{_libdir}/pkgconfig/%{name}.pc

%files data
%doc README.md
%dir %{_docdir}/%{name}/
%doc %{_docdir}/%{name}/AUTHORS.md
%doc %{_docdir}/%{name}/NEWS.md
%license %{_docdir}/%{name}/COPYING
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/CH
%{_datadir}/%{name}/GL27
%{_datadir}/%{name}/ITRF2000
%{_datadir}/%{name}/ITRF2008
%{_datadir}/%{name}/ITRF2014
%{_datadir}/%{name}/ITRF2020
%{_datadir}/%{name}/nad.lst
%{_datadir}/%{name}/nad27
%{_datadir}/%{name}/nad83
%{_datadir}/%{name}/other.extra
%{_datadir}/%{name}/proj.db
%{_datadir}/%{name}/proj.ini
%{_datadir}/%{name}/world
%{_datadir}/%{name}/README.DATA
%{_datadir}/%{name}/copyright_and_licenses.csv
%{_datadir}/%{name}/deformation_model.schema.json
%{_datadir}/%{name}/projjson.schema.json
%{_datadir}/%{name}/triangulation.schema.json
%{_mandir}/man1/*.1*

%if %{with mingw}
%files -n mingw32-%{name}
%license COPYING
%{mingw32_bindir}/libproj_9.dll
%{mingw32_bindir}/*.exe
%{mingw32_libdir}/libproj.dll.a
%{mingw32_libdir}/cmake/proj/
%{mingw32_libdir}/cmake/proj4/
%{mingw32_libdir}/pkgconfig/proj.pc
%{mingw32_includedir}/*.h
%{mingw32_includedir}/proj/
%{mingw32_datadir}/%{name}/

%files -n mingw64-%{name}
%license COPYING
%{mingw64_bindir}/libproj_9.dll
%{mingw64_bindir}/*.exe
%{mingw64_libdir}/libproj.dll.a
%{mingw64_libdir}/cmake/proj/
%{mingw64_libdir}/cmake/proj4/
%{mingw64_libdir}/pkgconfig/proj.pc
%{mingw64_includedir}/*.h
%{mingw64_includedir}/proj/
%{mingw64_datadir}/%{name}/
%endif


%changelog
* Thu May 21 2026 Percona Development <info@percona.com> - 9.6.0-1
- Initial packaging of proj for Percona OBS
