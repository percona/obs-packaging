%global pgmajorversion %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pginstdir /usr/pgsql-%{pgmajorversion}/

Name:           percona-pgaudit%{pgmajorversion}
Version:        1.0
Release:        1%{?dist}
Summary:        PostgreSQL Audit Extension
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

License:        PostgreSQL
URL:            http://pgaudit.org
Epoch:          1
Source0:        percona-pgaudit-%{version}.tar.gz

BuildRequires:  gcc
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
BuildRequires:  percona-postgresql%{pgmajorversion}-server
BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  openssl-devel
BuildRequires:  krb5-devel
BuildRequires:  clang llvm

Requires:       postgresql%{pgmajorversion}
Requires:       postgresql%{pgmajorversion}-libs
Requires:       postgresql%{pgmajorversion}-server

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


%prep
%setup -q -n percona-pgaudit-%{version}
#%%patch0

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
sed -i 's:PG_CONFIG = pg_config:PG_CONFIG = /usr/pgsql-%{pgmajorversion}/bin/pg_config:' Makefile
%{__make} USE_PGXS=1 %{?_smp_mflags}


%install
%{__make}  USE_PGXS=1 %{?_smp_mflags} DESTDIR=%{buildroot} install
# Install README and howto file under PostgreSQL installation directory:
%{__install} -d %{buildroot}%{pginstdir}/doc/extension
%{__install} -m 644 README.md %{buildroot}%{pginstdir}/doc/extension/README-pgaudit.md
%{__rm} -f %{buildroot}%{pginstdir}/doc/extension/README.md



%files
%defattr(-,root,root,-)
%doc %{pginstdir}/doc/extension/README-pgaudit.md
%{pginstdir}/lib/pgaudit.so
%{pginstdir}/share/extension/pgaudit--%{pgmajorversion}.*.sql
%{pginstdir}/lib/bitcode/pgaudit*.bc
%dir %{pginstdir}/lib/bitcode/pgaudit
%{pginstdir}/lib/bitcode/pgaudit/pgaudit*.bc
%{pginstdir}/share/extension/pgaudit.control


%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGAUDIT_VERSION}-1
- Update to upstream version %!{PGAUDIT_VERSION}
