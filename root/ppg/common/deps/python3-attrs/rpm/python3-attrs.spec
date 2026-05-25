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

%global srcname python3-attrs

Summary:        Classes Without Boilerplate
Name:           %{python3_pkgprefix}-attrs
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        MIT
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://www.attrs.org/
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools

%description
attrs is an MIT-licensed Python package with class decorators that ease
the chores of implementing the most common attribute-related object protocols.

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
%dir %{python3_sitelib}/attr
%dir %{python3_sitelib}/attr/__pycache__
%dir %{python3_sitelib}/attrs
%dir %{python3_sitelib}/attrs/__pycache__

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 22.1.0-1
- Initial build of python3-attrs 22.1.0
