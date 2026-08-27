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

Name:           %{python3_pkgprefix}-dns
Version:        2.8.0
Release:        1%{?dist}
Summary:        DNS toolkit
License:        ISC
URL:            https://pypi.org/project/dnspython/
Source0:        https://files.pythonhosted.org/packages/source/d/dnspython/dnspython-2.8.0.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
%if 0%{?rhel} == 8 || 0%{?rhel} == 9
BuildRequires:  %{python3_pkgprefix}-hatchling
%else
BuildRequires:  python3-hatchling
%endif

%description
DNS toolkit.

Built for Python 3.12 from the PyPI sdist; a Python 3.12 build/runtime dependency shared by Percona PostgreSQL packages.

%prep
%autosetup -p1 -n dnspython-2.8.0

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import dns"

%files
%{python3_sitelib}/*

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 2.8.0-1
- Package dnspython 2.8.0 for Python 3.12 (bump to 2.8.0 (email-validator needs >= 2.0); built with hatchling)

* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 1.15.0-1
- Initial build of python3-dns 1.15.0
