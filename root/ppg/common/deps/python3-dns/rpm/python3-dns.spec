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

%global srcname python3-dns

Summary:        DNS toolkit for Python
Name:           %{python3_pkgprefix}-dns
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        ISC
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://www.dnspython.org/
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools

%description
dnspython is a DNS toolkit for Python. It supports almost all record types. It can
be used for queries, zone transfers, and dynamic updates. It supports TSIG
authenticated messages and EDNS0.

%prep
%setup -n %{srcname}-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# Own egg-info directories (not recorded by --record)
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitelib}/dns
%dir %{python3_sitelib}/dns/__pycache__

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 1.15.0-1
- Initial build of python3-dns 1.15.0
