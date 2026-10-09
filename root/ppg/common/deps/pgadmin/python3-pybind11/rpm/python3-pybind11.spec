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

Name:           %{python3_pkgprefix}-pybind11
Version:        2.13.6
Release:        1%{?dist}
Summary:        Seamless operability between C++11 and Python
License:        BSD-3-Clause
URL:            https://github.com/pybind/pybind11
Source0:        https://files.pythonhosted.org/packages/source/p/pybind11/pybind11-2.13.6.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel

%description
pybind11 is a lightweight header-only library that exposes C++ types in Python
and vice versa. Built for Python 3.12 from the PyPI sdist; a build-time
dependency of pillow 12 in the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n pybind11-%{version}

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
# imports and confirms the headers landed (pillow reads get_include())
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import pybind11, os; p=pybind11.get_include(); assert os.path.exists(os.path.join('%{buildroot}%{python3_sitelib}', 'pybind11', 'include', 'pybind11', 'pybind11.h')) or os.path.exists(p+'/pybind11/pybind11.h'); print(p)"

%files
# console script from setup.py entry_points
%{_bindir}/pybind11-config
%{python3_sitelib}/*

%changelog
* Fri Sep 04 2026 Percona Development Team <info@percona.com> - 2.13.6-1
- Package pybind11 2.13.6 for Python 3.12 (build dependency of pillow 12;
  the 2.x line is setuptools-backed, unlike 3.x which needs scikit-build-core)
