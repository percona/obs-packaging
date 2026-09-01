%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython        %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython        %{_bindir}/python3
%global python3_pkgprefix python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -P -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-maturin
Version:        1.15.0
Release:        1%{?dist}
Summary:        Build tool for Rust-based Python packages (PEP 517 backend)
License:        MIT OR Apache-2.0
URL:            https://www.maturin.rs/
Source0:        https://files.pythonhosted.org/packages/source/m/maturin/maturin-1.15.0.tar.gz
Source1:        vendor.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

# The maturin binary is a plain cargo build; the PEP 517 python module in the
# sdist is a pure-python shim that shells out to that binary, so the sdist's
# own setuptools>=77/setuptools-rust bootstrap is bypassed entirely (RHEL 9
# ships setuptools 68).
BuildRequires:  cargo
BuildRequires:  rust
BuildRequires:  gcc
BuildRequires:  python%{python3_buildversion}-devel

Requires:       cargo
Requires:       rust

%description
maturin builds and publishes Rust-based Python packages (pyo3, cffi and
uniffi bindings). This package ships the maturin binary and the PEP 517
build-backend module for Python %{python3_buildversion}.

Built for Python 3.12; part of the pgAdmin 4 (percona-pgadmin4) dependency
stack build tooling — the build backend of cryptography >= 43.

%prep
%autosetup -p1 -n maturin-%{version} -a1

%build
export CARGO_NET_OFFLINE=true
# cargo_vendor put vendor/ and .cargo/config.toml next to the top-level Cargo.toml
export CARGO_HOME=$PWD/.cargo
cargo build --release --offline

%install
install -D -m 0755 target/release/maturin %{buildroot}%{_bindir}/maturin
# The PEP 517 backend shim (imported as "maturin" by pip); pure python,
# subprocess-calls the binary from PATH.
mkdir -p %{buildroot}%{python3_sitelib}/maturin
install -m 0644 maturin/*.py %{buildroot}%{python3_sitelib}/maturin/

%check
%{buildroot}%{_bindir}/maturin --version
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import maturin"

%files
%license license-mit license-apache
%{_bindir}/maturin
%{python3_sitelib}/maturin/

%changelog
* Tue Sep 01 2026 Percona Development Team <info@percona.com> - 1:1.15.0-1
- Package maturin 1.15.0 for Python 3.12 (build backend of cryptography 49,
  pgAdmin 4 dependency stack)
