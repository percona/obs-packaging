%global pgmajor %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 9
%global gts_version 14
%endif

%define pgmajorversion %{pgmajor}
%define pginstdir /usr/pgsql-%{pgmajorversion}/
%global sname percona-pg_cron_%{pgmajorversion}

%ifarch ppc64 ppc64le s390 s390x armv7hl
 %if 0%{?rhel} && 0%{?rhel} == 7
  %{!?llvm:%global llvm 0}
 %else
  %{!?llvm:%global llvm 1}
 %endif
%else
 %{!?llvm:%global llvm 1}
%endif

Summary:	Run periodic jobs in PostgreSQL
Name:		%{sname}
Version:        1.6.7
Release:        1%{?dist}
License:	AGPLv3
Source0:	%{sname}-%{version}.tar.gz
URL:		https://github.com/citusdata/pg_cron
BuildRequires:	percona-postgresql%{pgmajorversion}-devel libxml2-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
Requires:	postgresql%{pgmajorversion}-server
Requires(post):	%{_sbindir}/update-alternatives
Requires(postun):	%{_sbindir}/update-alternatives

%if 0%{?suse_version} >= 1315 && 0%{?suse_version} <= 1499
Requires:	libopenssl1_0_0
%else
%if 0%{?suse_version} >= 1500
Requires:	libopenssl1_1
%else
Requires:	openssl-libs >= 1.0.2k
%endif
%endif

%if 0%{?suse_version} >= 1315 && 0%{?suse_version} <= 1499
BuildRequires:	libopenssl-devel
%else
BuildRequires:	openssl-devel
%endif

%if 0%{?suse_version}
%if 0%{?suse_version} >= 1315
BuildRequires:	openldap2-devel
%endif
%else
BuildRequires:	openldap-devel
%endif

%description
pg_cron is a simple cron-based job scheduler for PostgreSQL
(9.5 or higher) that runs inside the database as an extension.
It uses the same syntax as regular cron, but it allows you to
schedule PostgreSQL commands directly from the database.

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for pg_cron
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
#%%if 0%%{?fedora} || 0%%{?rhel} >= 8
#Requires:	llvm => 13.0
#%%endif

%description llvmjit
This packages provides JIT support for pg_cron
%endif

%prep
%setup -q -n %{sname}-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
PATH=%{pginstdir}/bin/:$PATH %{__make} %{?_smp_mflags}

%install
PATH=%{pginstdir}/bin/:$PATH %make_install
# Install documentation with a better name:
%{__mkdir} -p %{buildroot}%{pginstdir}/doc/extension
%{__cp} README.md %{buildroot}%{pginstdir}/doc/extension/README-pg_cron.md

%files
%defattr(-,root,root,-)
%doc CHANGELOG.md
%license LICENSE
%dir %{pginstdir}/doc
%dir %{pginstdir}/doc/extension
%dir %{pginstdir}/lib
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%doc %{pginstdir}/doc/extension/README-pg_cron.md
%{pginstdir}/lib/pg_cron.so
%{pginstdir}/share/extension/pg_cron-*.sql
%{pginstdir}/share/extension/pg_cron.control

%if %llvm
%files llvmjit
   %dir %{pginstdir}/lib
   %{pginstdir}/lib/bitcode/pg_cron*.bc
   %dir %{pginstdir}/lib/bitcode/pg_cron
   %dir %{pginstdir}/lib/bitcode/pg_cron/src
   %{pginstdir}/lib/bitcode/pg_cron/src/*.bc
%endif

%changelog
* Tue Jan 16 2024 Muhammad Aqeel <muhammad.aqeel@percona.com> - 1.6.7-1
- Initial build of 1.6.7

