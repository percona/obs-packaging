%global pgmajor %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pgmajorversion %{pgmajor}
%define pginstdir /usr/pgsql-%{pgmajorversion}
%global sname address_standardizer

%{!?llvm:%global llvm 1}

Summary:	Parse a street address into its components
Name:		percona-address-standardizer%{pgmajorversion}
Version:	1.0.0
Release:	1%{?dist}
License:	MIT
Source0:	%{name}-%{version}.tar.gz
URL:		https://github.com/postgis/address_standardizer
BuildRequires:	percona-postgresql%{pgmajorversion}-devel pcre2-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
Requires:	postgresql%{pgmajorversion}-server

%description
The address_standardizer PostgreSQL extension parses a street address
into its components (house number, street name, suffix, ...). It is a
single-line address parser derived from the PAGC address standardizer,
formerly distributed as part of PostGIS and now maintained as a
standalone extension. The companion address_standardizer_data_us
extension provides the US dataset used by the parser.

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for address_standardizer
Requires:	%{name}%{?_isa} = %{version}-%{release}

BuildRequires:	llvm-devel clang-devel clang llvm

%description llvmjit
This package provides JIT support for address_standardizer
%endif

%prep
%setup -q

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
PATH=%{pginstdir}/bin:$PATH %{__make} install DESTDIR=%{buildroot}

%files
%defattr(-,root,root,-)
%doc README.md NEWS.md
%license COPYING
%dir %{pginstdir}/lib
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/%{sname}.so
%{pginstdir}/share/extension/%{sname}*.control
%{pginstdir}/share/extension/%{sname}*.sql

%if %llvm
%files llvmjit
   %dir %{pginstdir}/lib
   %{pginstdir}/lib/bitcode/%{sname}*.bc
   %dir %{pginstdir}/lib/bitcode/%{sname}
   %dir %{pginstdir}/lib/bitcode/%{sname}/src
   %{pginstdir}/lib/bitcode/%{sname}/src/*.bc
%endif

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{ADDRESS_STANDARDIZER_VERSION}-1
- Initial packaging of the standalone address_standardizer extension
