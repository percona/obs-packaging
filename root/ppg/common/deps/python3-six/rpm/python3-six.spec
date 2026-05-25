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

%global srcname python3-six

Summary:        Python 2 and 3 compatibility library
Name:           %{python3_pkgprefix}-six
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        MIT
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/benjaminp/six
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools

%description
Six is a Python 2 and 3 compatibility library. It provides utility functions for
smoothing over the differences between the Python versions with the goal of writing
Python code that is compatible on both Python versions.

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

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 1.17.0-1
- Initial build of python3-six 1.17.0
