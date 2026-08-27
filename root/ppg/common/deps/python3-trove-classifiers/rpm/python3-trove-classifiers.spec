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

Name:           %{python3_pkgprefix}-trove-classifiers
Version:        2025.9.11.17
Release:        1%{?dist}
Summary:        Canonical source for classifiers on PyPI (pypi.org)
License:        Apache-2.0
URL:            https://github.com/pypa/trove-classifiers
Source0:        https://files.pythonhosted.org/packages/source/t/trove-classifiers/trove_classifiers-2025.9.11.17.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel

%description
Canonical source for classifiers on PyPI (pypi.org).

Built for Python 3.12 from the PyPI sdist; a Python 3.12 build/runtime dependency shared by Percona PostgreSQL packages.

%prep
%autosetup -p1 -n trove_classifiers-2025.9.11.17
# Build without calver (not packaged): pin the version literally.
sed -i 's/"calver"//; s/, *\]/]/' pyproject.toml
sed -i 's/use_calver="[^"]*",/version="%{version}",/; /setup_requires=\["calver"\],/d' setup.py

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import trove_classifiers"

%files
%{python3_sitelib}/*
%{_bindir}/trove-classifiers

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 2025.9.11.17-1
- Package trove-classifiers 2025.9.11.17 for Python 3.12 (shared Python 3.12 build stack)
