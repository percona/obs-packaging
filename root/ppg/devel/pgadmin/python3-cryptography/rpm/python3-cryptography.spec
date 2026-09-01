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
%global python3_sitearch %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-cryptography
Version:        49.0.0
Release:        1%{?dist}
Summary:        Cryptographic recipes and primitives for Python
License:        Apache-2.0 OR BSD-3-Clause
URL:            https://cryptography.io/
Source0:        https://files.pythonhosted.org/packages/source/c/cryptography/cryptography-49.0.0.tar.gz
Source1:        vendor.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
# Epoch 1 so this outranks the RHEL 9 python3.12-cryptography 41 (pgAdmin 9.17
# targets cryptography 49: CFB8 only exists in hazmat.decrepit there, and 41
# has no decrepit at all)
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
# cryptography-cffi's build.rs compiles the _openssl cffi module through a
# python -c snippet that imports setuptools/distutils
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# PEP 517 backend (shells out to the maturin binary; pgAdmin stack package)
BuildRequires:  %{python3_pkgprefix}-maturin
BuildRequires:  %{python3_pkgprefix}-cffi >= 1:2.0
# _cffi_src/build_openssl.py runs cffi.FFI() during the cargo build
BuildRequires:  %{python3_pkgprefix}-pycparser
BuildRequires:  cargo
BuildRequires:  rust
BuildRequires:  gcc
BuildRequires:  openssl-devel
BuildRequires:  pkgconf

Requires:       %{python3_pkgprefix}-cffi >= 1:2.0

%description
cryptography includes both high level recipes and low level interfaces to
common cryptographic algorithms such as symmetric ciphers, message digests,
and key derivation functions.

Built for Python 3.12 from the PyPI sdist against the system OpenSSL; part
of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n cryptography-%{version} -a1

%build
export CARGO_NET_OFFLINE=true
# cargo_vendor put vendor/ and .cargo/config.toml next to src/rust/Cargo.toml
# (the [tool.maturin] manifest-path); maturin runs cargo with that manifest.
export CARGO_HOME=$PWD/src/rust/.cargo
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -P -c "
import cryptography
from cryptography.hazmat.decrepit.ciphers.modes import CFB8
from cryptography.fernet import Fernet
f = Fernet(Fernet.generate_key())
assert f.decrypt(f.encrypt(b'smoke')) == b'smoke'
print(cryptography.__version__)
"

%files
%{python3_sitearch}/*

%changelog
* Tue Sep 01 2026 Percona Development Team <info@percona.com> - 1:49.0.0-1
- Package cryptography 49.0.0 for Python 3.12 (pgAdmin 9.17 targets 49:
  CFB8 moved to hazmat.decrepit; replaces the reused RHEL cryptography 41)
