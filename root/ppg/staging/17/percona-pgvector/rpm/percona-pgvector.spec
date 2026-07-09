%define pgmajorversion %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pginstdir /usr/pgsql-%{pgmajorversion}/
%global pname vector
%global sname percona-pgvector_%{pgmajorversion}

%ifarch ppc64 ppc64le s390 s390x armv7hl
 %if 0%{?rhel} && 0%{?rhel} == 7
  %{!?llvm:%global llvm 0}
 %else
  %{!?llvm:%global llvm 1}
 %endif
%else
 %{!?llvm:%global llvm 1}
%endif

Name:		%{sname}
Version:	1.0.0
Release:	1%{?dist}
Summary:	Open-source vector similarity search for Postgres
License:	PostgreSQL
URL:		https://github.com/%{sname}/%{sname}/
Source0:	%{name}-%{version}.tar.gz

BuildRequires:	percona-postgresql%{pgmajorversion}-devel
BuildRequires:	clang llvm

%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
Requires:	postgresql%{pgmajorversion}-server

%description
Open-source vector similarity search for Postgres. Supports L2 distance,
inner product, and cosine distance

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for pgvector
Requires:	%{name}%{?_isa} = %{version}-%{release}

BuildRequires:	llvm-devel clang-devel


%description llvmjit
This packages provides JIT support for pgvector
%endif

%prep
%setup -q -n %{sname}-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot}

#Remove header file, we don't need it right now:
%{__rm} %{buildroot}%{pginstdir}/include/server/extension/%{pname}/%{pname}.h

%files
%doc README.md
%license LICENSE
%dir /usr/pgsql-%{pgmajorversion}
%dir /usr/pgsql-%{pgmajorversion}/lib
%dir /usr/pgsql-%{pgmajorversion}/share
%dir /usr/pgsql-%{pgmajorversion}/share/extension
%{pginstdir}/lib/%{pname}.so
%{pginstdir}/share/extension//%{pname}.control
%{pginstdir}/share/extension/%{pname}*sql
%dir %{pginstdir}/include/server/extension/vector/
%{pginstdir}/include/server/extension/vector/*.h

%if %llvm
%files llvmjit
   %dir /usr/pgsql-%{pgmajorversion}/lib
   %dir /usr/pgsql-%{pgmajorversion}/lib/bitcode
   %dir /usr/pgsql-%{pgmajorversion}/lib/bitcode/%{pname}
   %dir /usr/pgsql-%{pgmajorversion}/lib/bitcode/%{pname}/src
   %{pginstdir}/lib/bitcode/%{pname}*.bc
   %{pginstdir}/lib/bitcode/%{pname}/src/*.bc
%endif

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGVECTOR_VERSION}-1
- Update to upstream version %!{PGVECTOR_VERSION}
