%define pg_version %!{PG_MAJOR_VERSION}
%define pg_name percona-postgresql%{pg_version}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif
%define pgmajorversion %{pg_version}
%define pginstdir /usr/pgsql-%{pgmajorversion}/
%global pname pg_tde
%global sname percona-pg_tde%{pgmajorversion}

%global pgrel %{pg_version}

%ifarch ppc64 ppc64le s390 s390x armv7hl
 %if 0%{?rhel} && 0%{?rhel} == 7
  %{!?llvm:%global llvm 0}
 %else
  %{!?llvm:%global llvm 1}
 %endif
%else
 %{!?llvm:%global llvm 1}
%endif

%if "%{pg_name}" == ""
ExclusiveArch:  do_not_build
%endif

Name:           %{sname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        PostgreSQL extension for transparent data encryption.
License:        PostgreSQL
URL:            https://github.com/percona/pg_tde
Source0:        %{sname}-%{version}.tar.gz

BuildRequires:  %{pg_name}-devel chrpath openssl-devel libcurl-devel zlib-devel libzstd-devel libxml2-devel libxslt-devel libselinux-devel pam-devel krb5-devel readline-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?suse_version} >= 1500
BuildRequires:  libjson-c-devel liblz4-devel
%else
BuildRequires:  json-c-devel lz4-devel
%endif
BuildRequires:  clang llvm
%if 0%{?suse_version} >= 1500
Requires:       libjson-c5 curl libopenssl3
%else
Requires:       json-c curl openssl
%endif

Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, Inc

%description
pg_tde is a PostgreSQL extension enabling transparent data encryption.
It seamlessly encrypts and decrypts data in PostgreSQL databases, ensuring security and compliance.

%if %llvm
%package llvmjit
Summary:        Just-in-time compilation support for pg_tde
Requires:       %{name}%{?_isa} = %{version}-%{release}
BuildRequires:  llvm-devel clang-devel

%description llvmjit
This packages provides JIT support for pg_tde
%endif

%package devel
Summary:        Development files for %{name}
Requires:       %{name} = %{version}-%{release}

%description devel
Development and testing support files for pg_tde, including Perl test modules.

%prep
%setup -q -n %{sname}-%{version}

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make}

%install
%{__rm} -rf %{buildroot}
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot}
find %{buildroot}%{pginstdir} -type f \( -name '*.so' -o -name 'pg_tde_*' \) -exec chrpath --delete {} \; 2>/dev/null || true
mkdir -p %{buildroot}/%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test
install -m 644 ci_scripts/perl/PostgreSQL/Test/TdeCluster.pm %{buildroot}/%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test/

%files
%doc README.md
%license COPYRIGHT
%dir %{pginstdir}
%dir %{pginstdir}/bin
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/pg_tde
%dir %{pginstdir}/lib/bitcode/pg_tde/src
%dir %{pginstdir}/lib/bitcode/pg_tde/src/access
%dir %{pginstdir}/lib/bitcode/pg_tde/src/catalog
%dir %{pginstdir}/lib/bitcode/pg_tde/src/common
%dir %{pginstdir}/lib/bitcode/pg_tde/src/encryption
%dir %{pginstdir}/lib/bitcode/pg_tde/src/keyring
%dir %{pginstdir}/lib/bitcode/pg_tde/src/libkmip
%dir %{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip
%dir %{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip/src
%dir %{pginstdir}/lib/bitcode/pg_tde/src/smgr
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
%{pginstdir}/lib/bitcode/pg_tde.index.bc
%{pginstdir}/lib/bitcode/pg_tde/src/access/pg_tde_tdemap.bc
%{pginstdir}/lib/bitcode/pg_tde/src/access/pg_tde_xlog.bc
%{pginstdir}/lib/bitcode/pg_tde/src/access/pg_tde_xlog_keys.bc
%{pginstdir}/lib/bitcode/pg_tde/src/access/pg_tde_xlog_smgr.bc
%{pginstdir}/lib/bitcode/pg_tde/src/catalog/tde_keyring.bc
%{pginstdir}/lib/bitcode/pg_tde/src/catalog/tde_keyring_parse_opts.bc
%{pginstdir}/lib/bitcode/pg_tde/src/catalog/tde_principal_key.bc
%{pginstdir}/lib/bitcode/pg_tde/src/common/pg_tde_utils.bc
%{pginstdir}/lib/bitcode/pg_tde/src/encryption/enc_aes.bc
%{pginstdir}/lib/bitcode/pg_tde/src/encryption/enc_tde.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_api.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_curl.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_file.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_kmip.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_kmip_impl.bc
%{pginstdir}/lib/bitcode/pg_tde/src/keyring/keyring_vault.bc
%{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip/src/kmip.bc
%{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip/src/kmip_bio.bc
%{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip/src/kmip_locate.bc
%{pginstdir}/lib/bitcode/pg_tde/src/libkmip/libkmip/src/kmip_memset.bc
%{pginstdir}/lib/bitcode/pg_tde/src/pg_tde.bc
%{pginstdir}/lib/bitcode/pg_tde/src/pg_tde_event_capture.bc
%{pginstdir}/lib/bitcode/pg_tde/src/pg_tde_guc.bc
%{pginstdir}/lib/bitcode/pg_tde/src/smgr/pg_tde_smgr.bc

%files devel
%dir %{pginstdir}/lib/pgxs/src/test/perl
%dir %{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL
%dir %{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test
%{pginstdir}/lib/pgxs/src/test/perl/PostgreSQL/Test/TdeCluster.pm

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_TDE_VERSION}-1
- Update to upstream version %!{PG_TDE_VERSION}
