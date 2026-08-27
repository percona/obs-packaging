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

Name:           %{python3_pkgprefix}-paramiko
Version:        3.5.1
Release:        1%{?dist}
Summary:        SSH2 protocol library
License:        LGPL-2.1-or-later
URL:            https://paramiko.org
Source0:        https://files.pythonhosted.org/packages/source/p/paramiko/paramiko-3.5.1.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  %{python3_pkgprefix}-bcrypt >= 3.2
BuildRequires:  python3.12-cryptography
BuildRequires:  %{python3_pkgprefix}-pynacl >= 1.5

Requires:       %{python3_pkgprefix}-bcrypt >= 3.2
Requires:       python3.12-cryptography
Requires:       %{python3_pkgprefix}-pynacl >= 1.5

%description
SSH2 protocol library.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n paramiko-3.5.1

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" | sed 's/^/%dir /' >> INSTALLED_FILES

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import paramiko"

%files -f INSTALLED_FILES
%defattr(-,root,root)

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 3.5.1-1
- Package paramiko 3.5.1 for Python 3.12 (pgAdmin 4 dependency stack)
