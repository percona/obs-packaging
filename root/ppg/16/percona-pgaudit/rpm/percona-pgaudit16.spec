%define pgmajorversion %!{PG_MAJOR_VERSION}

%if 0%{?rhel} && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pginstdir /usr/pgsql-%{pgmajorversion}/

Name:           percona-pgaudit%{pgmajorversion}
Version:        1.0.0
Release:        2%{?dist}
Summary:        PostgreSQL Audit Extension
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

License:        PostgreSQL
URL:            http://pgaudit.org
Epoch:          1
Source0:        percona-pgaudit-%{version}.tar.gz
Patch0:		all.patch

BuildRequires:  gcc
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
BuildRequires:  percona-postgresql%{pgmajorversion}-server
BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  openssl-devel
BuildRequires:  clang llvm
BuildRequires:  krb5-devel

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
export PATH=/opt/rh/gcc-toolset-%{gts_version}/root/usr/bin${PATH:+:${PATH}}
rpmlibdir=$(rpm --eval "%{_libdir}")
export LD_LIBRARY_PATH=/opt/rh/gcc-toolset-%{gts_version}/root${rpmlibdir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
export PKG_CONFIG_PATH=/opt/rh/gcc-toolset-%{gts_version}/root/usr/lib64/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}
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
%dir %{pginstdir}
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/pgaudit
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/pgaudit.so
%{pginstdir}/share/extension/pgaudit--%{pgmajorversion}.*.sql
%{pginstdir}/lib/bitcode/pgaudit*.bc
%{pginstdir}/lib/bitcode/pgaudit/pgaudit*.bc
%{pginstdir}/share/extension/pgaudit.control


%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGAUDIT_VERSION}-1
- Update to upstream version %!{PGAUDIT_VERSION}
