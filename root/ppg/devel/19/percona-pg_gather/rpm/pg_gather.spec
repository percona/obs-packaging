%global pgmajor %!{PG_MAJOR_VERSION}
%global debug_package %{nil}

%global sname   percona-pg_gather
%global pgmajorversion %{pgmajor}
%global pginstdir /usr/pgsql-%{pgmajorversion}

Summary:        sql-only script to gather performance and configuration data from PostgreSQL databases
Name:           percona-pg_gather
Version:        1
Release:        1%{?dist}
License:        GPLv3
Group:          Applications/Databases
Source0:        %{sname}-%{version}.tar.gz
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

Requires:       percona-postgresql%{pgmajorversion}

%description
pg_gather consists of one sql-only script (gather.sql) for gathering performance and configuration data from PostgreSQL databases.

%prep
%setup -q -n %{sname}-%{version}

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/%{_bindir} $RPM_BUILD_ROOT/%{pginstdir}
%{__install} -p -D -m 0755 gather.sql %{buildroot}%{pginstdir}/share/contrib/gather.sql

%files
%dir %{pginstdir}
%dir %{pginstdir}/share
%dir %{pginstdir}/share/contrib
%attr (755,root,root) %{pginstdir}/share/contrib/gather.sql

%clean
rm -rf $RPM_BUILD_ROOT

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_GATHER_VERSION}-1
- Update to upstream version %!{PG_GATHER_VERSION}
