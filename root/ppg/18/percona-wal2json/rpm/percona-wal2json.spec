%global pgmajor %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8
%global gts_version 14
%endif

%define pginstdir /usr/pgsql-%{pgmajorversion}

%global sname wal2json
%global pgmajorversion %{pgmajor}
%global _default_patch_fuzz 2

Summary:	JSON output plugin for changeset extraction
Name:		percona-%{sname}%{pgmajorversion}
Version:	1.0
Release:	1%{?dist}
Epoch:		1
License:	BSD
Source0:	percona-%{sname}-%{version}.tar.gz
Patch0:		%{sname}-pg%{pgmajorversion}-makefile-pgxs.patch
URL:		https://github.com/eulerto/wal2json
BuildRequires:	percona-postgresql%{pgmajorversion}-devel
BuildRequires:	krb5-devel
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
Provides:	%{sname}%{pgmajorversion}
Requires:	percona-postgresql%{pgmajorversion}-server
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

%description
wal2json is an output plugin for logical decoding. It means that the
plugin have access to tuples produced by INSERT and UPDATE. Also,
UPDATE/DELETE old row versions can be accessed depending on the
configured replica identity. Changes can be consumed using the streaming
protocol (logical replication slots) or by a special SQL API.

The wal2json output plugin produces a JSON object per transaction. All
of the new/old tuples are available in the JSON object. Also, there are
options to include properties such as transaction timestamp,
schema-qualified, data types, and transaction ids.

%prep
%setup -q -n percona-%{sname}-%{version}
%patch  -P 0 -p0

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
%{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
%make_install DESTDIR=%{buildroot}
%{__install} -d %{buildroot}/%{pginstdir}/doc/extension/
%{__mv} README.md  %{buildroot}/%{pginstdir}/doc/extension/README-%{sname}.md

%postun -p /sbin/ldconfig
%post -p /sbin/ldconfig

%files
%doc %{pginstdir}/doc/extension/README-%{sname}.md
%{pginstdir}/lib/%{sname}.so
%{pginstdir}/lib/bitcode/%{sname}*.bc
%dir %{pginstdir}/lib/bitcode/%{sname}
%{pginstdir}/lib/bitcode/%{sname}/*.bc

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{WAL2JSON_VERSION}-1
- Update to upstream version %!{WAL2JSON_VERSION}

