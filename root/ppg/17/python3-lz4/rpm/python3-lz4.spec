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

%global srcname python3-lz4

Summary:        LZ4 bindings for Python
Name:           %{python3_pkgprefix}-lz4
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        BSD-3-Clause
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/python-lz4/python-lz4
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  gcc
%if 0%{?suse_version}
BuildRequires:  liblz4-devel
%else
BuildRequires:  lz4-devel
%endif

%description
This package provides Python bindings for the lz4 compression library.

%prep
%setup -n %{srcname}-%{version}
# Remove pkgconfig and setuptools_scm from setup_requires to avoid pip at build time;
# lz4-devel pkg-config files are available via BuildRequires
python3 -c "
import re
try:
    txt = open('setup.py').read()
    txt = re.sub(r'setup_requires\s*=\s*\[[^\]]*\]', 'setup_requires=[]', txt)
    open('setup.py','w').write(txt)
except: pass
" || true

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# Own egg-info and subdirectories (not recorded by --record)
find %{buildroot} -name "*.egg-info" -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES
find %{buildroot}%{python3_sitearch}/lz4 -mindepth 1 -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitearch}/lz4

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 4.3.3-1
- Initial build of python3-lz4 4.3.3
