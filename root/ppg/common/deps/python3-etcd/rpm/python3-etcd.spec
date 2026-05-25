%global         debug_package %{nil}

%if 0%{?rhel} || 0%{?fedora}
%global python3_pkgprefix python3
%endif
%if 0%{?rhel} && 0%{?rhel} >= 8
%global python3_pkgprefix python3.12
%endif
%if 0%{?suse_version} == 1500
%global python3_pkgprefix python311
%endif
%if 0%{?suse_version} >= 1600
%global python3_pkgprefix python313
%endif

%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython %{_bindir}/python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython %{_bindir}/python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

%define srcname python3-etcd
%define pkgname %{python3_pkgprefix}-etcd

Summary:        A python client for etcd
Name:           %{pkgname}
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        MIT
Group:          Development/Libraries
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix:         %{_prefix}
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/jplana/python-etcd
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools
%if 0%{?suse_version}
BuildRequires:  %{python3_pkgprefix}-setuptools
%endif

Requires:       %{python3_pkgprefix}-urllib3
%if !0%{?suse_version}
Requires:       %{python3_pkgprefix}-dns
%endif
%if 0%{?suse_version} >= 1500
Requires:       %{python3_pkgprefix}-dnspython
%endif

%description
A python client for etcd (https://github.com/coreos/etcd).
Includes support for the etcd v2 API with SSL client certificate
authentication, cluster failover, and read/write/delete operations.

%prep
%setup -n %{srcname}-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitelib}/etcd
%dir %{python3_sitelib}/etcd/__pycache__
%dir %{python3_sitelib}/etcd/tests
%dir %{python3_sitelib}/etcd/tests/__pycache__
%dir %{python3_sitelib}/etcd/tests/integration
%dir %{python3_sitelib}/etcd/tests/integration/__pycache__
%dir %{python3_sitelib}/etcd/tests/unit
%dir %{python3_sitelib}/etcd/tests/unit/__pycache__
%dir %{python3_sitelib}/python_etcd-%{version}-py%{py3ver}.egg-info

%if 0%{?rhel} && 0%{?rhel} >= 9
%package -n python3-etcd
Summary:        Compatibility alias for python3-etcd on RHEL >= 9
Requires:       python3.12-etcd = %{epoch}:%{version}-%{release}
BuildArch:      noarch
Epoch:          1

%description -n python3-etcd
Compatibility alias that pulls in python3.12-etcd on RHEL >= 9.

%files -n python3-etcd
%endif

%if 0%{?rhel} && 0%{?rhel} == 8
%package -n python3-etcd
Summary:        Compatibility alias for python3-etcd on RHEL 8
Requires:       python3.12-etcd = %{epoch}:%{version}-%{release}
BuildArch:      noarch
Epoch:          1

%description -n python3-etcd
Compatibility alias that pulls in python3.12-etcd on RHEL 8.

%files -n python3-etcd
%endif

%changelog
* Sun Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 0.4.5-2
- Use python3.12 package name on RHEL >= 9
* Thu Mar 19 2026 Percona Build/Release Team <eng-build@percona.com> - 0.4.5-1
- Initial build of python-etcd 0.4.5
