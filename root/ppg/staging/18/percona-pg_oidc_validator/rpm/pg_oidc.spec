%global pgmajor %!{PG_MAJOR_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

%global debug_package %{nil}
%global __strip /bin/true
%define _enable_debug_packages 0
%define _unpackaged_files_terminate_build 0

%define pgmajorversion %{pgmajor}
%define pginstdir /usr/pgsql-%{pgmajorversion}/
%global pname pg_oidc_validator
%global sname percona-pg_oidc_validator%{pgmajorversion}

Name:           %{sname}
Version:        1.0
Release:        1%{?dist}
Summary:        PostgreSQL OAuth/OIDC token validator extension

License:        Apache-2.0
URL:            https://github.com/Percona-Lab/pg_oidc_validator
Source0:        %{name}-%{version}.tar.gz

%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif

BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  libcurl-devel
BuildRequires:  openssl-devel
BuildRequires:  krb5-devel
BuildRequires:  gcc-c++
%if 0%{?rhel} >= 10
BuildRequires:  libstdc++-static
%endif

Requires:       percona-postgresql%{pgmajorversion}
Requires:       libcurl
Requires:       openssl-libs

%description
pg_oidc_validator is a PostgreSQL extension that implements OIDC (OpenID Connect)
token validation. It validates JWT tokens from OIDC providers, enabling OAuth-based
authentication for PostgreSQL connections.

%prep
%setup -q

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
export PG_CONFIG=%{pginstdir}/bin/pg_config
make USE_PGXS=1 %{?_smp_mflags} with_llvm=no COMPILER='g++ $(CXXFLAGS)'

%install
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
export PG_CONFIG=%{pginstdir}/bin/pg_config
make USE_PGXS=1 install DESTDIR=%{buildroot} with_llvm=no COMPILER='g++ $(CXXFLAGS)'

%files
%license LICENSE.txt
%doc README.md
%{pginstdir}/lib/%{pname}.so

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_OIDC_VALIDATOR_VERSION}-1
- Update to upstream version %!{PG_OIDC_VALIDATOR_VERSION}
