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

%global srcname python3-boto3

Summary:        The AWS SDK for Python
Name:           %{python3_pkgprefix}-boto3
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        Apache-2.0
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/boto/boto3
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools

Requires:       %{python3_pkgprefix}-botocore

%description
Boto3 is the Amazon Web Services (AWS) Software Development Kit (SDK) for Python,
which allows Python developers to write software that makes use of services like
Amazon S3 and Amazon EC2.

%prep
%setup -n %{srcname}-%{version}

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# Own all installed directories (not recorded by --record)
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitelib}/boto3

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 1.38.19-1
- Initial build of python3-boto3 1.38.19
