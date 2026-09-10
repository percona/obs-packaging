%global sname percona-credcheck
%global pgmajorversion %!{PG_MAJOR_VERSION}

%{!?llvm:%global llvm 1}

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
%global pginstdir /usr/pgsql-%{pgmajorversion}

Summary:        PostgreSQL username/password checks
Name:           %{sname}%{pgmajorversion}
Version:        %!{CREDCHECK_VERSION}
Release:        1%{?dist}
License:        PostgreSQL
URL:            https://github.com/HexaCluster/credcheck
Source0:        %{sname}-%{version}.tar.gz
Epoch:          1
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, Inc

BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  krb5-devel
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?suse_version} >= 1500
Requires:       libopenssl3
BuildRequires:  libopenssl-3-devel
%endif
%if 0%{?fedora} >= 41 || 0%{?rhel} >= 8 || 0%{?amzn}
Requires:       openssl-libs >= 1.1.1k
BuildRequires:  openssl-devel
%endif

Requires:       percona-postgresql%{pgmajorversion}

%description
The credcheck PostgreSQL extension provides few general credential checks,
which will be evaluated during the user creation, during the password change
and user renaming. By using this extension, we can define a set of rules to
allow a specific set of credentials, and a set of rules to reject a certain
type of credentials. This extension is developed based on the PostgreSQL's
check_password_hook hook.

%if %llvm
%package llvmjit
Summary:        Just-in-time compilation support for credcheck
Requires:       %{name}%{?_isa} = %{version}-%{release}
BuildRequires:  clang llvm

%description llvmjit
This package provides JIT support for credcheck
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
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot} %{with_llvm_arg}


%clean
%{__rm} -rf %{buildroot}


%files
%defattr(755,root,root,755)
%doc README.md
%license LICENSE
%dir %{pginstdir}
%dir %{pginstdir}/lib
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/lib/credcheck.so
%{pginstdir}/share/extension/credcheck.control
%{pginstdir}/share/extension/credcheck*.sql

%if %llvm
%files llvmjit
%dir %{pginstdir}/lib/bitcode
%dir %{pginstdir}/lib/bitcode/credcheck
%{pginstdir}/lib/bitcode/credcheck*.bc
%{pginstdir}/lib/bitcode/credcheck/*.bc
%endif


%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{CREDCHECK_VERSION}-1
- Update to %!{CREDCHECK_VERSION} per changes described at
  https://github.com/HexaCluster/credcheck/releases/tag/v%!{CREDCHECK_VERSION}
