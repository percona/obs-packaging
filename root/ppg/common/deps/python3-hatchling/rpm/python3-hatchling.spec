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
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-hatchling
Version:        1.28.0
Release:        1%{?dist}
Summary:        Modern, extensible Python build backend
License:        MIT
URL:            https://hatch.pypa.io/latest/
Source0:        https://files.pythonhosted.org/packages/source/h/hatchling/hatchling-1.28.0.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  %{python3_pkgprefix}-packaging >= 24.2
BuildRequires:  %{python3_pkgprefix}-pathspec >= 0.10.1
BuildRequires:  python3.12-pluggy
BuildRequires:  %{python3_pkgprefix}-trove-classifiers

Requires:       %{python3_pkgprefix}-packaging >= 24.2
Requires:       %{python3_pkgprefix}-pathspec >= 0.10.1
Requires:       python3.12-pluggy
Requires:       %{python3_pkgprefix}-trove-classifiers

%description
Modern, extensible Python build backend.

Built for Python 3.12 from the PyPI sdist; a Python 3.12 build/runtime dependency shared by Percona PostgreSQL packages.

%prep
%autosetup -p1 -n hatchling-1.28.0

%build
export PYTHONPATH=$PWD/src
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -c "import hatchling"

%files
%{python3_sitelib}/*
%{_bindir}/hatchling

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 1.28.0-1
- Package hatchling 1.28.0 for Python 3.12 (shared Python 3.12 build stack)
