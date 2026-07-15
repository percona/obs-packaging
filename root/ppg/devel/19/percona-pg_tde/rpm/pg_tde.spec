%global pgmajor %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%define pgmajorversion %{pgmajor}
%define pginstdir /usr/pgsql-%{pgmajorversion}/
%global pname pg_tde
%global sname percona-pg_tde%{pgmajorversion}

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
Version:    1.0.0
Release:    1%{?dist}
Summary:	PostgreSQL extension for transparent data encryption.
License:	PostgreSQL
URL:		https://github.com/%{sname}/%{sname}/
Source0:	%{name}-%{version}.tar.gz

BuildRequires:  meson
BuildRequires:	percona-postgresql%{pgmajorversion}-devel chrpath openssl-devel libcurl-devel zlib-devel libxml2-devel libxslt-devel libselinux-devel pam-devel krb5-devel readline-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?fedora} || 0%{?rhel}
BuildRequires:	json-c-devel lz4-devel libzstd-devel numactl-devel
%endif
%if 0%{?suse_version}
BuildRequires:	libjson-c-devel liblz4-devel libzstd-devel >= 1.4.0 libnuma-devel
%endif
Requires:	postgresql%{pgmajorversion}-server curl openssl

%description
pg_tde is a PostgreSQL extension enabling transparent data encryption.
It seamlessly encrypts and decrypts data in PostgreSQL databases, ensuring security and compliance.

%if %llvm
%package llvmjit
Summary:	Just-in-time compilation support for pg_tde
Requires:	%{name}%{?_isa} = %{version}-%{release}
BuildRequires:	llvm-devel clang-devel clang llvm

%description llvmjit
This packages provides JIT support for pg_tde
%endif

%prep
%setup -q -n %{sname}-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif

%meson -Dpg_config=%{pginstdir}/bin/pg_config
%meson_build

%install
%{__rm} -rf %{buildroot}
%meson_install
find %{buildroot}%{pginstdir} -type f \( -name '*.so' -o -name 'pg_tde_*' \) -exec chrpath --delete {} \; 2>/dev/null || true
mkdir -p %{buildroot}/%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test
install -m 644 ci_scripts/perl/PostgreSQL/Test/TdeCluster.pm %{buildroot}/%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test/

%package devel
Summary: Development files for %{name}
Requires: %{name} = %{version}-%{release}

%description devel
Development and testing support files for pg_tde, including Perl test modules.

%files
%doc README.md
%license COPYRIGHT
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/bin/pg_tde_change_key_provider
%{pginstdir}/bin/pg_tde_archive_decrypt
%{pginstdir}/bin/pg_tde_restore_encrypt
%{pginstdir}/lib/%{pname}.so
%{pginstdir}/share/extension//%{pname}.control
%{pginstdir}/share/extension/%{pname}*sql
%{pginstdir}/bin/pg_tde_basebackup
%{pginstdir}/bin/pg_tde_checksums
%{pginstdir}/bin/pg_tde_resetwal
%{pginstdir}/bin/pg_tde_rewind
%{pginstdir}/bin/pg_tde_waldump
%{pginstdir}/bin/pg_tde_upgrade

%files devel
%dir %{pginstdir}/lib/pgxs/src/test/perl
%dir %{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL
%dir %{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test
%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test/TdeCluster.pm



%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_TDE_VERSION}-1
- Update to upstream version %!{PG_TDE_VERSION}
