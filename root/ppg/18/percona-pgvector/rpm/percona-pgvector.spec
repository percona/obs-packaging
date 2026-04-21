%global pgmajor 18

%define pgmajorversion %{pgmajor}
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
Version:	0.8.2
Release:	1%{?dist}
Summary:	Open-source vector similarity search for Postgres
License:	PostgreSQL
URL:		https://github.com/%{sname}/%{sname}/
Source0:	percona-pgvector-%{version}.tar.gz

BuildRequires:	percona-postgresql%{pgmajorversion}-devel
Requires:	postgresql%{pgmajorversion}-server

%description
Open-source vector similarity search for Postgres. Supports L2 distance,
inner product, and cosine distance

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for pgvector
Requires:	%{name}%{?_isa} = %{version}-%{release}
#%%if 0%%{?rhel} && 0%%{?rhel} == 7
#%%ifarch aarch64
#Requires:	llvm-toolset-7.0-llvm >= 7.0.1
#%%else
#Requires:	llvm5.0 >= 5.0
#%%endif
#%%endif
%if 0%{?suse_version} == 1500
BuildRequires:	llvm17-devel clang17-devel clang17 llvm17
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:	llvm19-devel clang19-devel clang19 llvm19
%endif
%if 0%{?fedora} || 0%{?rhel}
BuildRequires:	llvm-devel clang-devel clang llvm
%endif

%description llvmjit
This packages provides JIT support for pgvector
%endif

%prep
%setup -q -n percona-pgvector-%{version}

%build
sed -i 's:PG_CONFIG = pg_config:PG_CONFIG = /usr/pgsql-%{pgmajorversion}/bin/pg_config:' Makefile
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot}

#Remove header file, we don't need it right now:
%{__rm} %{buildroot}%{pginstdir}/include/server/extension/%{pname}/%{pname}.h

%files
%doc README.md
%license LICENSE
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/%{pname}.so
%{pginstdir}/share/extension//%{pname}.control
%{pginstdir}/share/extension/%{pname}*sql
%dir %{pginstdir}/include/server/extension/vector/
%{pginstdir}/include/server/extension/vector/*.h

%if %llvm
%files llvmjit
   %{pginstdir}/lib/bitcode/%{pname}*.bc
   %dir %{pginstdir}/lib/bitcode/%{pname}
   %dir %{pginstdir}/lib/bitcode/%{pname}/src
   %{pginstdir}/lib/bitcode/%{pname}/src/*.bc
%endif

%changelog
* Thu Jun 27 2024 Muhammad Aqeel <muhammad.aqeel@percona.com> - 0.7.2-1
- Initial build 0.7.2

