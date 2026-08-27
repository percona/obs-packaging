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

Name:           %{python3_pkgprefix}-cython
Version:        3.1.3
Release:        1%{?dist}
Summary:        The Cython compiler for writing C extensions in the Python language
License:        Apache-2.0
URL:            https://cython.org/
Source0:        https://files.pythonhosted.org/packages/source/C/Cython/cython-3.1.3.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  gcc

%description
The Cython compiler for writing C extensions in the Python language.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n cython-3.1.3

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES
find %{buildroot}%{python3_sitearch} -mindepth 1 -type d | sed "s|%{buildroot}||" | sed 's/^/%dir /' >> INSTALLED_FILES

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -c "import Cython"

%files -f INSTALLED_FILES
%defattr(-,root,root)
%{_bindir}/cygdb
%{_bindir}/cython
%{_bindir}/cythonize

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 3.1.3-1
- Package Cython 3.1.3 for Python 3.12 (pgAdmin 4 dependency stack)
