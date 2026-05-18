%global pgmajorversion %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 9
%global gts_version 14
%endif

%global  sname pgaudit%{pgmajorversion}_set_user
%define pginstdir /usr/pgsql-%{pgmajorversion}/

Name:		percona-%{sname}
Version:	4.2.0
Release:	1%{?dist}
Epoch:      1
Provides:	pgaudit%{pgmajorversion}_set_user = %{version}-%{release}
URL:        https://github.com/pgaudit/set_user.git
License:	PostgreSQL
Group:		Applications/Database
Source:		%{name}-%{version}.tar.gz
Summary:	pgaudit%{pgmajorversion}_set_user - PostgreSQL extension allowing privilege escalation with enhanced logging and control
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

BuildRequires:	percona-postgresql%{pgmajorversion}
BuildRequires:	percona-postgresql%{pgmajorversion}-devel
BuildRequires:	krb5-devel
BuildRequires:	openssl-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?suse_version} >= 1600
BuildRequires:	clang19 llvm19
%endif
%if 0%{?suse_version} == 1500
BuildRequires:	clang17 llvm17
%endif
%if 0%{?fedora} || 0%{?rhel}
BuildRequires:	clang llvm
%endif

Requires:	postgresql%{pgmajorversion}

%description
PostgreSQL is an advanced Object-Relational database management system.
The PostgreSQL Audit extension (pgaudit) provides detailed session and/or 
object audit logging via the standard PostgreSQL logging facility. 
The set_user part of that extension allows for extra logging with regard
 to granting of superuser privileges, and also enforces 
 a superuser-request policy over direct superuser logins.

%prep
%setup -q -n %{name}-%{version}

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
%{__make} USE_PGXS=1 DESTDIR=%{buildroot} install

%clean
rm -rf ${RPM_BUILD_ROOT}

%files
%defattr(-,root,root)
%dir %{pginstdir}/include
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%dir %{pginstdir}/lib/bitcode/src
%dir %{pginstdir}/lib/bitcode/src/set_user
%dir %{pginstdir}/lib/bitcode/src/set_user/src
%{pginstdir}/lib/set_user.so
%{pginstdir}/lib/bitcode/src/set_user.index.bc
%{pginstdir}/lib/bitcode/src/set_user/src/set_user.bc
%{pginstdir}/include/set_user.h
%{pginstdir}/share/extension/set_user-*.sql
%{pginstdir}/share/extension/set_user.control
%doc LICENSE
%doc README.md

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGAUDIT_SET_USER_VERSION}-1
- Update to upstream version %!{PGAUDIT_SET_USER_VERSION}
