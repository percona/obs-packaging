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

Name:           %{python3_pkgprefix}-greenlet
Version:        3.5.5
Release:        1%{?dist}
Summary:        Lightweight in-process concurrent programming
License:        MIT AND PSF-2.0
URL:            https://greenlet.readthedocs.io
Source0:        https://files.pythonhosted.org/packages/source/g/greenlet/greenlet-3.5.5.tar.gz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  gcc-c++

%description
Lightweight in-process concurrent programming.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n greenlet-3.5.5
# setuptools 68 (RHEL 9) cannot parse PEP 639 licence metadata: use the table form, drop license-files
sed -i -e 's/^license = "\(.*\)"$/license = {text = "\1"}/' -e '/^license-files = \[$/,/^\]$/d' -e '/^license-files = \[.*\]$/d' pyproject.toml

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitearch} %{__ospython} -P -c "import greenlet"

%files
%{python3_sitearch}/*
%{_includedir}/python%{py3ver}/greenlet/

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 3.5.5-1
- Package greenlet 3.5.5 for Python 3.12 (pgAdmin 4 dependency stack)
