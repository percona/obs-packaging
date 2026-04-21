%global pgmajor 18
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

%if 0%{?rhel} && 0%{?rhel} <= 9
BuildRequires:  gcc-toolset-14
%endif

BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  libcurl-devel
BuildRequires:  openssl-devel
BuildRequires:  krb5-devel
BuildRequires:  gcc-c++

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
%if 0%{?rhel} && 0%{?rhel} <= 9
source /opt/rh/gcc-toolset-14/enable
%endif
export PG_CONFIG=%{pginstdir}/bin/pg_config
make USE_PGXS=1 %{?_smp_mflags} with_llvm=no COMPILER='g++ $(CXXFLAGS)'

%install
%if 0%{?rhel} && 0%{?rhel} <= 9
source /opt/rh/gcc-toolset-14/enable
#%else
#source /opt/rh/gcc-toolset-15/enable
%endif
export PG_CONFIG=%{pginstdir}/bin/pg_config
make USE_PGXS=1 install DESTDIR=%{buildroot} with_llvm=no COMPILER='g++ $(CXXFLAGS)'

%files
%license LICENSE.txt
%doc README.md
%{pginstdir}/lib/%{pname}.so

%changelog
* Wed Feb 11 2026 Manika Singhal <manika.singhal@percona.com> - 1.0-1
- Initial build 1.0
