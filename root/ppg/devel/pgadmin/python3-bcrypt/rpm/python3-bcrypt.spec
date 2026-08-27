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
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitearch %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-bcrypt
Version:        5.0.0
Release:        1%{?dist}
Summary:        Modern password hashing for your software and your servers
License:        Apache-2.0
URL:            https://pypi.org/project/bcrypt/
Source0:        https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-5.0.0.tar.gz
Source1:        vendor.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  %{python3_pkgprefix}-setuptools-rust
BuildRequires:  cargo
BuildRequires:  rust
BuildRequires:  gcc

%description
Modern password hashing for your software and your servers.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n bcrypt-5.0.0 -a1

%build
export CARGO_NET_OFFLINE=true
export CARGO_HOME=$PWD/.cargo
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -c "import bcrypt"

%files
%{python3_sitearch}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 5.0.0-1
- Package bcrypt 5.0.0 for Python 3.12 (pgAdmin 4 dependency stack)
