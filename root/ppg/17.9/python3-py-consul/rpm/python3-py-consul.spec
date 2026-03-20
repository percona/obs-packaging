%global         debug_package %{nil}

%if 0%{?rhel} || 0%{?fedora}
%global python3_pkgprefix python3
%endif
%if 0%{?suse_version} == 1500
%global python3_pkgprefix python311
%endif
%if 0%{?suse_version} > 1600
%global python3_pkgprefix python313
%endif

%if 0%{?rhel} && 0%{?rhel} >= 9
%global __ospython %{_bindir}/python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython %{_bindir}/python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

%define         name python3-py-consul

Summary:        Python client for Consul
Name:           %{name}
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{name}-%{version}.tar.gz
License:        MIT
Group:          Development/Libraries
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix:         %{_prefix}
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/criteo/py-consul
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools
%if 0%{?suse_version}
BuildRequires:  %{python3_pkgprefix}-setuptools
%endif

Requires:       %{python3_pkgprefix}-requests

Provides:       py-consul = %{version}-%{release}

%description
Python client for Consul (http://www.consul.io/).
Includes support for Consul's Key/Value store, services, health checks,
sessions, events, ACLs, and more.

%prep
%setup -n %{name}-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitelib}/consul
%dir %{python3_sitelib}/consul/__pycache__
%dir %{python3_sitelib}/consul/api
%dir %{python3_sitelib}/consul/api/__pycache__
%dir %{python3_sitelib}/consul/api/acl
%dir %{python3_sitelib}/consul/api/acl/__pycache__
%dir %{python3_sitelib}/docs
%dir %{python3_sitelib}/docs/__pycache__
%dir %{python3_sitelib}/py_consul-%{version}-py%{py3ver}.egg-info

%changelog
* Thu Mar 19 2026 Percona Build/Release Team <eng-build@percona.com> - 1.7.1-1
- Initial build of py-consul 1.7.1
