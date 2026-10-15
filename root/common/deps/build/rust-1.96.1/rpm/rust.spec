%global debug_package %{nil}

%global common_libdir %{_prefix}/lib
%global rustlibdir %{common_libdir}/rustlib

Name:     rust
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
    --libdir=%{common_libdir} \
    --sysconfdir=%{_sysconfdir} \
    --disable-docs \
    --disable-rpath \
    --enable-vendor \
    --llvm-root=/usr \
    --enable-llvm-link-shared \
    --python=%{__python3} \
    --set build.build-stage=2 \
    --set build.install-stage=2 \
    --set build.jobs=%{_smp_build_ncpus}
python3 ./x.py build

%install
DESTDIR=%{buildroot} python3 ./x.py install

# Move compiler shared libraries into the RPM library directory
%if "%{_libdir}" != "%{common_libdir}"
mkdir -p %{buildroot}%{_libdir}
find %{buildroot}%{common_libdir} -maxdepth 1 -type f -name '*.so' \
    -exec mv -v -t %{buildroot}%{_libdir} '{}' '+'
%endif

# Remove Python scripts from the Rust source component
find %{buildroot}%{rustlibdir}/src -type f -name '*.py' -exec rm -v '{}' '+'

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}%{rustlibdir} -maxdepth 1 -type f -exec rm -v '{}' '+'

# The shared libraries should be executable for debuginfo extraction.
find %{buildroot}%{_libdir} -maxdepth 1 -type f -name '*.so' \
    -exec chmod -v +x '{}' '+'
find %{buildroot}%{rustlibdir} -type f -name '*.so' \
    -exec chmod -v +x '{}' '+'

# Remove optional developer tools not required by cargo-pgrx
rm -f %{buildroot}%{_bindir}/rust-analyzer
rm -f %{buildroot}%{_libexecdir}/rust-analyzer-proc-macro-srv

# Remove debugger wrappers
rm -f %{buildroot}%{_bindir}/rust-gdb
rm -f %{buildroot}%{_bindir}/rust-gdbgui
rm -f %{buildroot}%{_bindir}/rust-lldb

# Remove shell completions
rm -f %{buildroot}%{_sysconfdir}/bash_completion.d/cargo
rm -f %{buildroot}%{_datadir}/zsh/site-functions/_cargo

# Remove optional target specification schema
rm -f %{buildroot}%{_sysconfdir}/target-spec-json-schema.json

# Remove optional tool documentation
rm -rf %{buildroot}%{_docdir}/clippy
rm -rf %{buildroot}%{_docdir}/rust-analyzer
rm -rf %{buildroot}%{_docdir}/rustfmt
rm -rf %{buildroot}%{_docdir}/cargo
rm -rf %{buildroot}%{_docdir}/rustc

# Remove optional man pages
rm -f %{buildroot}%{_mandir}/man1/cargo*.1*
rm -f %{buildroot}%{_mandir}/man1/rustc.1*
rm -f %{buildroot}%{_mandir}/man1/rustdoc.1*

echo "===== Checking for conflicting ELF build ID ====="
find %{buildroot} -type f -exec sh -c '
    for f do
        id=$(readelf -n "$f" 2>/dev/null |
             sed -n "s/.*Build ID: //p" |
             head -n 1)
        if [ "$id" = "ea34e3e454440ccc3de9d54b004c8cd50ab05118" ]; then
            echo "MATCH: $f"
        fi
    done
' sh {} +
echo "===== Finished build-ID check ====="

%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%{_bindir}/rustc
%{_bindir}/rustdoc
{_bindir}/cargo-clippy
{_bindir}/clippy-driver
{_bindir}/rustfmt
{_bindir}/cargo-fmt
%{_libdir}/librustc_driver-*.so
%{rustlibdir}/
%exclude %{_sysconfdir}/target-spec-json-schema.json

%files -n cargo
%license src/tools/cargo/LICENSE-APACHE
%license src/tools/cargo/LICENSE-MIT
%license src/tools/cargo/LICENSE-THIRD-PARTY
%{_bindir}/cargo

%changelog
* Tue Oct 13 2026 Percona Development Team <info@percona.com> - 1.96.1-1
- Package rust 1.96.1 for building cargo-pgrx 0.19.1 based PostgreSQL extensions
