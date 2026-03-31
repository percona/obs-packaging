%global debug_package %{nil}

%if 0%{?rhel} && 0%{?rhel} >= 9
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

%global srcname python3-zstandard

Summary:        Zstandard bindings for Python
Name:           %{python3_pkgprefix}-zstandard
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        BSD-3-Clause
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/indygreg/python-zstandard
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  gcc

%description
This project provides Python bindings for interfacing with the Zstandard
compression library. A C extension and CFFI interface is provided.

%prep
%setup -n %{srcname}-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# Own egg-info and subdirectories (not recorded by --record)
find %{buildroot} -name "*.egg-info" -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES
find %{buildroot}%{python3_sitearch}/zstandard -mindepth 1 -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitearch}/zstandard

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 0.23.0-1
- Initial build of python3-zstandard 0.23.0
