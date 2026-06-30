%global debug_package %{nil}

Name:     cargo-pgrx-0.18.0
Version:  0.18.0
Release:  1%{?dist}
Summary:  cargo-pgrx 0.18.0 build tool for pgrx-based PostgreSQL extensions
License:  MIT
URL:      https://github.com/pgcentralfoundation/pgrx
Source0:  cargo-pgrx-%{version}.tar.gz
Source1:  vendor.tar.gz

ExclusiveArch: x86_64 aarch64

BuildRequires:  cargo
BuildRequires:  gcc
BuildRequires:  openssl-devel
BuildRequires:  zlib-devel
BuildRequires:  pkgconfig

# Extensions select the matching tool with `BuildRequires: cargo-pgrx = 0.18.0`.
Provides:       cargo-pgrx = %{version}

%description
cargo-pgrx is the build orchestrator for pgrx-based PostgreSQL extensions.
This package pins cargo-pgrx to %{version} so it matches extensions built
against the pgrx %{version} runtime. The PostgreSQL version is selected by the
consuming extension at `cargo pgrx package` time via pg_config, so this single
build serves every PostgreSQL major.

%prep
# -a1 unpacks vendor.tar.gz into the source tree: it bundles .cargo/config.toml
# (crates.io -> vendor/ source replacement) plus Cargo.lock, wiring the offline
# build automatically.
%autosetup -n cargo-pgrx-%{version} -a1

%build
export CARGO_NET_OFFLINE=true
cargo build --release --offline

%install
install -D -m 0755 target/release/cargo-pgrx %{buildroot}%{_bindir}/cargo-pgrx

%files
%{_bindir}/cargo-pgrx

%changelog
* Tue Jun 30 2026 Percona Development Team <info@percona.com> - 0.18.0-1
- Package cargo-pgrx 0.18.0 for building pgrx 0.18.0 based PostgreSQL extensions
