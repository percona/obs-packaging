%global sname	postgresql_anonymizer
%global extname	anon
%global pgmajorversion %!{PG_MAJOR_VERSION}
%global debug_package %{nil}

%define pginstdir /usr/pgsql-%{pgmajorversion}/

Summary:	Anonymization & Data Masking for PostgreSQL
Name:		percona-%{sname}_%{pgmajorversion}
Version:	1.0.0
Release:	1%{?dist}
License:	PostgreSQL
Source0:	percona-%{sname}_%{pgmajorversion}-%{version}.tar.gz
Source1:    vendor.tar.gz
Packager:	Percona Development Team <https://jira.percona.com>
Vendor:		Percona, LLC
URL:		https://gitlab.com/dalibo/postgresql_anonymizer

BuildRequires:  cargo
BuildRequires:  cargo-pgrx = 0.18.0
BuildRequires:  rustfmt
BuildRequires:	percona-postgresql%{pgmajorversion}-devel
BuildRequires:	gcc clang-devel openssl-devel pkg-config
Requires:	percona-postgresql%{pgmajorversion}-server

%description
PostgreSQL Anonymizer is an extension to mask or replace personally
identifiable information (PII) or commercially sensitive data from a
PostgreSQL database. The project relies on a declarative approach of
anonymization. This means you can declare the masking rules using the
PostgreSQL Data Definition Language (DDL).

%prep
%autosetup -p1 -a1 -n percona-%{sname}_%{pgmajorversion}-%{version}

%build
export CARGO_NET_OFFLINE=true
export PGRX_PG_CONFIG_PATH=%{pginstdir}/bin/pg_config
export RUSTFLAGS="${RUSTFLAGS:-} -C link-arg=-Wl,--no-gc-sections"

cargo pgrx package --pg-config %{pginstdir}/bin/pg_config --no-default-features --features pg%{pgmajorversion}

PGRX_TARGET=target/release/%{extname}-pg%{pgmajorversion}
mkdir -p ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}/
install data/*.csv ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}/
install data/en_US/fake/*.csv ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}/

%install
%{__rm} -rf %{buildroot}
PGRX_TARGET=target/release/%{extname}-pg%{pgmajorversion}

%{__mkdir} -p %{buildroot}%{pginstdir}/lib
%{__mkdir} -p %{buildroot}%{pginstdir}/share/extension

install -m 755 ${PGRX_TARGET}%{pginstdir}/lib/%{extname}.so %{buildroot}%{pginstdir}/lib/
cp -a ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}.control %{buildroot}%{pginstdir}/share/extension/
cp -a ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}--*.sql %{buildroot}%{pginstdir}/share/extension/
cp -a ${PGRX_TARGET}%{pginstdir}/share/extension/%{extname}/ %{buildroot}%{pginstdir}/share/extension/%{extname}/

%files
%defattr(-,root,root,-)
%doc README.md
%{pginstdir}/lib/%{extname}.so
%{pginstdir}/share/extension/%{extname}.control
%{pginstdir}/share/extension/%{extname}--*.sql
%{pginstdir}/share/extension/%{extname}/

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_ANONYMIZER_VERSION}-1
- Update to upstream version %!{PG_ANONYMIZER_VERSION}
