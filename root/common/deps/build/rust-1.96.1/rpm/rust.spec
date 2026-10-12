%global debug_package %{nil}

Name:     rust-1.96.1
Version:  1.96.1
Release:  1%{?dist}
Summary:  Rust compiler and Cargo toolchain
License:  Apache-2.0 OR MIT
URL:      https://www.rust-lang.org
Source0:  rustc-%{version}-src.tar.xz

# Rust 1.96.1 stage0 bootstrap artifacts (Rust 1.95.0)
# x86_64 bootstrap toolchain
Source1:  rust-std-1.95.0-x86_64-unknown-linux-gnu.tar.xz
Source2:  rustc-1.95.0-x86_64-unknown-linux-gnu.tar.xz
Source3:  cargo-1.95.0-x86_64-unknown-linux-gnu.tar.xz

# aarch64 bootstrap toolchain
Source4:  rust-std-1.95.0-aarch64-unknown-linux-gnu.tar.xz
Source5:  rustc-1.95.0-aarch64-unknown-linux-gnu.tar.xz
Source6:  cargo-1.95.0-aarch64-unknown-linux-gnu.tar.xz

ExclusiveArch: x86_64 aarch64

BuildRequires:  gcc gcc-c++ make cmake ninja-build python3 curl-devel libxml2-devel
BuildRequires:  openssl-devel zlib-devel xz-devel ncurses-devel pkgconfig llvm-devel

# Bootstrap toolchain available in the OBS repository
BuildRequires:  rust >= 1.92
BuildRequires:  cargo >= 1.92

# Extensions select the matching tool with `BuildRequires: rust = 1.96.1`.
Provides:       rust = %{version}

%description
Rust 1.96.1 compiler toolchain built for OBS to satisfy the
Rust compiler and Cargo version requirements of cargo-pgrx 0.19.1.

%package -n cargo
Summary:        Rust package manager and build tool
Requires:       rust = %{version}-%{release}

%description -n cargo
Cargo package manager built alongside Rust 1.96.1.

%prep
%autosetup -n rustc-%{version}-src
# Prepopulate the bootstrap cache
mkdir -p build/cache/2026-04-16

%ifarch x86_64
cp %{SOURCE1} build/cache/2026-04-16/
cp %{SOURCE2} build/cache/2026-04-16/
cp %{SOURCE3} build/cache/2026-04-16/
%endif
%ifarch aarch64
cp %{SOURCE4} build/cache/2026-04-16/
cp %{SOURCE5} build/cache/2026-04-16/
cp %{SOURCE6} build/cache/2026-04-16/
%endif

%build
export CARGO_NET_OFFLINE=true
./configure \
    --prefix=%{_prefix} \
    --sysconfdir=%{_sysconfdir} \
    --disable-docs \
    --enable-vendor \
    --llvm-root=/usr \
    --enable-llvm-link-shared \
    --set build.build-stage=2 \
    --set build.install-stage=2 \
    --set build.jobs=%{_smp_build_ncpus}
python3 ./x.py build

%install
DESTDIR=%{buildroot} python3 ./x.py install
# Fix ambiguous Python shebang in the installed Rust source component
sed -i '1s|^#!/usr/bin/env python$|#!/usr/bin/env python3|' \
    %{buildroot}%{_prefix}/lib/rustlib/src/rust/library/core/src/unicode/printable.py
# Remove Rust installer metadata that contains temporary buildroot paths.
rm -f %{buildroot}%{_prefix}/lib/rustlib/manifest-*
rm -f %{buildroot}%{_prefix}/lib/rustlib/install.log
rm -f %{buildroot}%{_prefix}/lib/rustlib/uninstall.sh

%files
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_libdir}/librustc_driver-*.so
%{_prefix}/lib/rustlib/

%files -n cargo
%{_bindir}/cargo
%{_mandir}/man1/cargo*.1*

%changelog
* Tue Oct 13 2026 Percona Development Team <info@percona.com> - 1.96.1-1
- Package rust 1.96.1 for building cargo-pgrx 0.19.1 based PostgreSQL extensions
