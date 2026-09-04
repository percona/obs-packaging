%global debug_package %{nil}
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

Name:           %{python3_pkgprefix}-secretstorage
Version:        3.5.0
Release:        1%{?dist}
Summary:        Python bindings to FreeDesktop.org Secret Service API
License:        BSD-3-Clause
URL:            https://github.com/mitya57/secretstorage
Source0:        https://files.pythonhosted.org/packages/source/S/SecretStorage/secretstorage-3.5.0.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  python3.12-cryptography
BuildRequires:  %{python3_pkgprefix}-jeepney >= 0.6

Requires:       python3.12-cryptography
Requires:       %{python3_pkgprefix}-jeepney >= 0.6

%description
Python bindings to FreeDesktop.org Secret Service API.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n secretstorage-3.5.0

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import secretstorage"

%files
%{python3_sitelib}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 3.5.0-1
- Package SecretStorage 3.5.0 for Python 3.12 (pgAdmin 4 dependency stack)
