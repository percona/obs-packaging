%global sname          percona-pg_stat_monitor
%define pgmajorversion 17
%global pginstdir      /usr/pgsql-%{pgmajorversion}/

Summary:        Statistics collector for PostgreSQL
Name:           %{sname}%{pgmajorversion}
Version:        1.0.0
Release:        1%{?dist}
License:        PostgreSQL
Source0:        %{sname}-%{version}.tar.gz
URL:            https://github.com/percona/pg_stat_monitor
BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  clang llvm
Requires:       percona-postgresql%{pgmajorversion}
Provides:       percona-pg-stat-monitor%{pgmajorversion}
Conflicts:      percona-pg-stat-monitor%{pgmajorversion}
Obsoletes:      percona-pg-stat-monitor%{pgmajorversion}
Epoch:          1
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, Inc

%description
The pg_stat_monitor is a Query Performance Monitoring tool for PostgreSQL.
It attempts to provide a more holistic picture by providing much-needed query
performance insights in a single view.

pg_stat_monitor provides improved insights that allow database users to
understand query origins, execution, planning statistics and details, query
information, and metadata. This significantly improves observability, enabling
users to debug and tune query performance. pg_stat_monitor is developed on the
basis of pg_stat_statements as its more advanced replacement.


%prep
%setup -q -n %{sname}-%{version}


%build
sed -i 's:PG_CONFIG ?= pg_config:PG_CONFIG = %{pginstdir}bin/pg_config:' Makefile
%{__make} USE_PGXS=1 %{?_smp_mflags}


%install
%{__rm} -rf %{buildroot}
%{__make} USE_PGXS=1 %{?_smp_mflags} install DESTDIR=%{buildroot}
%{__install} -d %{buildroot}%{pginstdir}/share/extension
%{__install} -m 755 README.md %{buildroot}%{pginstdir}/share/extension/README-pg_stat_monitor


%clean
%{__rm} -rf %{buildroot}


%post -p /sbin/ldconfig


%postun -p /sbin/ldconfig


%files
%defattr(-,root,root,-)
%doc %{pginstdir}/share/extension/README-pg_stat_monitor
%dir %{pginstdir}
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/pg_stat_monitor
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/pg_stat_monitor.so
%{pginstdir}/share/extension/pg_stat_monitor--*.sql
%{pginstdir}/share/extension/pg_stat_monitor.control
%{pginstdir}/lib/bitcode/pg_stat_monitor*.bc
%{pginstdir}/lib/bitcode/pg_stat_monitor/*.bc


%changelog
* Tue Mar 24 2026 Percona Development Team <info@percona.com> - 2.3.2-1
- Initial packaging
