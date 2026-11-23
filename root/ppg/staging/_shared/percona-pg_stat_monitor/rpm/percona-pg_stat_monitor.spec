%global sname percona-pg_stat_monitor
%global pgmajorversion %!{PG_MAJOR_VERSION}
%define pgminorversion %!{PG_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif
%global pginstdir /usr/pgsql-%{pgmajorversion}

%{!?llvm:%global llvm 1}
%{!?runselftest:%global runselftest 0}
# The TAP tests need Text::Trim, which is not available on RHEL (nor in EPEL),
# so the tests cannot run there:
%if 0%{?rhel}
%global runselftest 0
%endif

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

Summary:        Statistics collector for PostgreSQL
Name:           %{sname}%{pgmajorversion}
Version:        1.0.0
Release:        %!{PKG_REVISION}%{?dist}
License:        PostgreSQL
Source0:        %{sname}-%{version}.tar.gz
URL:            https://github.com/percona/pg_stat_monitor
Epoch:          1
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, Inc

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

BuildRequires:  clang llvm
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif

BuildRequires:  krb5-devel
BuildRequires:  openssl-devel

Requires:       percona-postgresql%{pgmajorversion}-server
Provides:       percona-pg-stat-monitor%{pgmajorversion}
Conflicts:      percona-pg-stat-monitor%{pgmajorversion}
Obsoletes:      percona-pg-stat-monitor%{pgmajorversion}

%if %runselftest
BuildRequires:        percona-postgresql%{pgmajorversion}-server pgdg-srpm-macros >= 2.0.0
# The TAP tests use pg_stat_statements and pgbench
BuildRequires:        percona-postgresql%{pgmajorversion}-contrib
# prove and the Perl modules that the TAP tests use
BuildRequires:        perl(Test::Harness) perl(IPC::Run) perl(Text::Trim)
BuildRequires:        perl(Test::More) perl(lib) perl(File::Basename) perl(File::Compare)
%endif

%description
The pg_stat_monitor is a Query Performance Monitoring tool for PostgreSQL.
It attempts to provide a more holistic picture by providing much-needed query
performance insights in a single view.

pg_stat_monitor provides improved insights that allow database users to
understand query origins, execution, planning statistics and details, query
information, and metadata. This significantly improves observability, enabling
users to debug and tune query performance. pg_stat_monitor is developed on the
basis of pg_stat_statements as its more advanced replacement.

While pg_stat_statements provides ever-increasing metrics, pg_stat_monitor
aggregates the collected data, saving user efforts for doing it themselves.
pg_stat_monitor stores statistics in configurable time-based units – buckets.
This allows focusing on statistics generated for shorter time periods and
makes query timing information such as max/min/mean time more accurate.

%if %llvm
%package llvmjit
Summary:        Just-in-time compilation support for pg_stat_monitor
Requires:        %{name}%{?_isa} = %{version}-%{release}
%if 0%{?suse_version} == 1500
BuildRequires:        llvm17-devel clang17-devel
Requires:        llvm17
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:        llvm-devel clang-devel
Requires:        llvm
%endif
%if 0%{?amzn}
BuildRequires:        llvm-devel >= 15.0 clang-devel >= 15.0
Requires:        llvm >= 15.0
%endif
%if ( 0%{?fedora} || 0%{?rhel} >= 8 ) && !0%{?amzn}
BuildRequires:        llvm-devel >= 19.0 clang-devel >= 19.0
Requires:        llvm >= 19.0
%endif
%description llvmjit
This packages provides JIT support for pg_stat_monitor
%endif

%prep
%setup -q -n %{sname}-%{version}


%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} %{with_llvm_arg}


%install
%{__rm} -rf %{buildroot}
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} %{with_llvm_arg} install DESTDIR=%{buildroot}
%{__install} -d %{buildroot}%{pginstdir}/share/extension
%{__install} -m 755 README.md %{buildroot}%{pginstdir}/share/extension/README-pg_stat_monitor


%clean
%{__rm} -rf %{buildroot}


%post -p /sbin/ldconfig


%postun -p /sbin/ldconfig

%check
%if %runselftest
# The tests need pg_stat_monitor in shared_preload_libraries
%pgdg_check_init
# This test depends on timing: it expects three pg_sleep(3) calls to fall
# into three different 3-second buckets, and fails randomly.
%{__rm} -f t/029_bucket_done.pl
pgdg_check_start main "shared_preload_libraries = 'pg_stat_monitor'" \
        "max_prepared_transactions = 5"
pgdg_installcheck %{with_llvm_arg}
%endif

%files
%defattr(755,root,root,755)
%doc %{pginstdir}/share/extension/README-pg_stat_monitor
%dir %{pginstdir}
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/pg_stat_monitor
%dir %{pginstdir}/lib/bitcode/pg_stat_monitor/src
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/pg_stat_monitor.so
%{pginstdir}/share/extension/pg_stat_monitor--*.sql
%{pginstdir}/share/extension/pg_stat_monitor.control
		
%if %llvm
%files llvmjit
%{pginstdir}/lib/bitcode/pg_stat_monitor*.bc
%{pginstdir}/lib/bitcode/pg_stat_monitor/src/*.bc
%endif


%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_STAT_MONITOR_VERSION}-1
- Update to upstream version %!{PG_STAT_MONITOR_VERSION}
