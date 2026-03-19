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

%define         name python3-etcd

Summary:        A python client for etcd
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
Url:            https://github.com/jplana/python-etcd
Epoch:          1

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
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
%setup -n %{name}-%{version}

%build
python3 setup.py build

%install
python3 setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

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
%dir %{python3_sitelib}/python_etcd-%{version}-py%{python3_version}.egg-info

%changelog
* Thu Mar 19 2026 Percona Build/Release Team <eng-build@percona.com> - 0.4.5-1
- Initial build of python-etcd 0.4.5
