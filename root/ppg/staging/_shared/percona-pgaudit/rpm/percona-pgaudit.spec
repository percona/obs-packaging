%define pgmajorversion %!{PG_MAJOR_VERSION}

%{!?llvm:%global llvm 1}
%{!?runselftest:%global runselftest 0}

# Propagate %%llvm into the actual build: PGXS decides whether to invoke
# clang/llvm-config based on with_llvm from the installed postgresql*-devel's
# Makefile.global, not from this spec's %%llvm. Without passing with_llvm=no
# through to make, setting %%llvm 0 here only drops the llvm BuildRequires/
# subpackage/files, while the build still tries to run clang regardless.
%if %llvm
%global with_llvm_arg %{nil}
%else
%global with_llvm_arg with_llvm=no
%endif

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pginstdir /usr/pgsql-%{pgmajorversion}/

Name:           percona-pgaudit%{pgmajorversion}
Version:        1.0.0
Release:        %!{PKG_REVISION}%{?dist}
Summary:        PostgreSQL Audit Extension
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

%if 0%{?pgminorversion:1}
# pgminorversion is the PostgreSQL minor release that the build servers
# build against (global/Makefile.global): require at least that one, at
# build time and at runtime.
# The other postgresqlNN-* dependencies need no version here: the PostgreSQL
# subpackages require each other's exact version-release (all of them pin
# the client package, which pins -libs), so the server, contrib etc. follow
# -devel at build time and -libs at runtime.
BuildRequires:	percona-postgresql%{pgmajorversion}-devel >= %{pgminorversion}
Requires:	percona-postgresql%{pgmajorversion}-libs%{?_isa} >= %{pgminorversion}
%endif

License:        PostgreSQL
URL:            http://pgaudit.org
Epoch:          1
Source0:        percona-pgaudit-%{version}.tar.gz

BuildRequires:  gcc
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
BuildRequires:  percona-postgresql%{pgmajorversion}-devel percona-postgresql%{pgmajorversion}
BuildRequires:  krb5-devel

%if 0%{?suse_version} >= 1500
Requires:	libopenssl3
BuildRequires:	libopenssl-3-devel
%endif
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 8 || 0%{?amzn}
Requires:	openssl-libs >= 1.1.1k
BuildRequires:	openssl-devel
%endif
Requires:	percona-postgresql%{pgmajorversion}-server
%if %runselftest
BuildRequires:	percona-postgresql%{pgmajorversion}-server pgdg-srpm-macros >= 2.0.0
# The tests use pg_stat_statements and postgres_fdw from contrib
BuildRequires:	percona-postgresql%{pgmajorversion}-contrib
# prove and IPC::Run, for the TAP tests
BuildRequires:	perl(Test::Harness) perl(IPC::Run)
%endif

Provides:       pgaudit pgaudit%{pgmajorversion}
%description
The PostgreSQL Audit extension (pgaudit) provides detailed session
and/or object audit logging via the standard PostgreSQL logging
facility.

The goal of the PostgreSQL Audit extension (pgaudit) is to provide
PostgreSQL users with capability to produce audit logs often required to
comply with government, financial, or ISO certifications.

An audit is an official inspection of an individual's or organization's
accounts, typically by an independent body. The information gathered by
the PostgreSQL Audit extension (pgaudit) is properly called an audit
trail or audit log. The term audit log is used in this documentation.

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for pgaudit
Requires:	%{name}%{?_isa} = %{version}-%{release}
%if 0%{?suse_version} == 1500
BuildRequires:	llvm17-devel clang17-devel
Requires:	llvm17
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:	llvm-devel clang-devel
%endif
%if 0%{?amzn}
BuildRequires:	llvm-devel >= 15.0 clang-devel >= 15.0
Requires:	llvm >= 15.0
%endif
%if ( 0%{?fedora} || 0%{?rhel} >= 8 ) && !0%{?amzn}
BuildRequires:	llvm-devel >= 19.0 clang-devel >= 19.0
Requires:	llvm >= 19.0
%endif

%description llvmjit
This package provides JIT support for pgaudit
%endif

%prep
%setup -q -n percona-pgaudit-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
sed -i 's:PG_CONFIG = pg_config:PG_CONFIG = /usr/pgsql-%{pgmajorversion}/bin/pg_config:' Makefile
%{__make} USE_PGXS=1 %{?_smp_mflags} %{with_llvm_arg}


%install
%{__rm} -rf %{buildroot}
%{__make}  USE_PGXS=1 %{?_smp_mflags} DESTDIR=%{buildroot} install %{with_llvm_arg}
# Install README and howto file under PostgreSQL installation directory:
%{__install} -d %{buildroot}%{pginstdir}/doc/extension
%{__install} -m 644 README.md %{buildroot}%{pginstdir}/doc/extension/README-pgaudit.md
%{__rm} -f %{buildroot}%{pginstdir}/doc/extension/README.md

%check
%if %runselftest
# The tests need pgaudit in shared_preload_libraries
%pgdg_check_init
pgdg_check_start main "shared_preload_libraries = 'pgaudit'"
pgdg_installcheck %{with_llvm_arg}
%endif

%files
%defattr(-,root,root,-)
%doc %{pginstdir}/doc/extension/README-pgaudit.md
%dir %{pginstdir}
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/pgaudit
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/pgaudit.so
%{pginstdir}/share/extension/pgaudit--*.sql
%{pginstdir}/share/extension/pgaudit.control

%if %llvm
%files llvmjit
%{pginstdir}/lib/bitcode/pgaudit*.bc
%{pginstdir}/lib/bitcode/pgaudit/*.bc
%endif

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGAUDIT_VERSION}-1
- Update to upstream version %!{PGAUDIT_VERSION}
