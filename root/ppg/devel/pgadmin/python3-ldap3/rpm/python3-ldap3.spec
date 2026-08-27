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

Name:           %{python3_pkgprefix}-ldap3
Version:        2.9.1
Release:        1%{?dist}
Summary:        A strictly RFC 4510 conforming LDAP V3 pure Python client library
License:        LGPL-3.0-only
URL:            https://github.com/cannatag/ldap3
Source0:        https://files.pythonhosted.org/packages/source/l/ldap3/ldap3-2.9.1.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  %{python3_pkgprefix}-pyasn1

Requires:       %{python3_pkgprefix}-pyasn1

%description
A strictly RFC 4510 conforming LDAP V3 pure Python client library.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n ldap3-2.9.1

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" | sed 's/^/%dir /' >> INSTALLED_FILES

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -c "import ldap3"

%files -f INSTALLED_FILES
%defattr(-,root,root)

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 2.9.1-1
- Package ldap3 2.9.1 for Python 3.12 (pgAdmin 4 dependency stack)
