%global debug_package %{nil}
%global pgmajorversion %!{PG_MAJOR_VERSION}
%global pname pgvectorscale
%global sname	percona-pgvectorscale_%{pgmajorversion}

%define pginstdir /usr/pgsql-%{pgmajorversion}/

Summary:        Vector scaling extension for PostgreSQL
Name:           %{sname}
Version:        1.0.0
Release:        1%{?dist}
License:        PostgreSQL
URL:            https://github.com/timescale/pgvectorscale
Source0:        %{sname}-%{version}.tar.gz
Source1:    vendor.tar.gz
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

BuildRequires:  cargo
BuildRequires:  cargo-pgrx = 0.16.1
BuildRequires:  rustfmt
BuildRequires:  rust-toolset jq clang llvm-devel
BuildRequires:  percona-postgresql%{pgmajorversion}-devel

Requires:       percona-postgresql%{pgmajorversion}-server
Requires:       percona-pgvector_%{pgmajorversion}

%description
pgvectorscale enhances pgvector with scalable indexing and storage.

%prep
%autosetup -p1 -a1 -n %{sname}-%{version}

%build
cd pgvectorscale
export CARGO_NET_OFFLINE=true
export PGRX_PG_CONFIG_PATH=%{pginstdir}/bin/pg_config
export RUSTFLAGS="-C target-feature=+avx2,+fma"
cargo pgrx init --no-run --pg%{pgmajorversion}=%{pginstdir}/bin/pg_config
cargo build --release --no-default-features --features pg%{pgmajorversion}
cargo pgrx package --no-default-features --features pg%{pgmajorversion} --pg-config %{pginstdir}/bin/pg_config

%install
rm -rf %{buildroot}
install -d %{buildroot}
cp -r target/release/vectorscale-pg%{pgmajorversion}/* %{buildroot}/

%files
%{pginstdir}/lib/vectorscale*.so
%{pginstdir}/share/extension/vectorscale*
%license LICENSE

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGVECTORSCALE_VERSION}-1
- Update to upstream version %!{PGVECTORSCALE_VERSION}
