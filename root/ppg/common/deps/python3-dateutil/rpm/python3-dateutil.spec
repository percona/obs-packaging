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

%global srcname python3-dateutil

Summary:        Extensions to the standard Python datetime module
Name:           %{python3_pkgprefix}-dateutil
Version:        1.0.0
Release:        1%{?dist}
Source0:        %{srcname}-%{version}.tar.gz
License:        Apache-2.0 AND BSD-3-Clause
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Url:            https://github.com/dateutil/dateutil
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools

Requires:       %{python3_pkgprefix}-six >= 1.5

%description
The dateutil module provides powerful extensions to the standard datetime module,
available in Python 2.7 and later.

%prep
%setup -n %{srcname}-%{version}
# Remove setup_requires from setup.cfg to avoid pip dependency at build time
python3 -c "
import re
try:
    txt = open('setup.cfg').read()
    txt = re.sub(r'\nsetup_requires\s*=[^\n]*(\n[ \t]+[^\n]*)*', '', txt)
    open('setup.cfg','w').write(txt)
except: pass
" || true
# Inject version into setup.cfg so setuptools doesn't need setuptools-scm to determine it
sed -i "/^\[metadata\]/a version = %{version}" setup.cfg

%build
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%{__ospython} setup.py build

%install
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# Own egg-info directories (not recorded by --record)
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" >> INSTALLED_FILES

%files -f INSTALLED_FILES
%defattr(-,root,root)
%dir %{python3_sitelib}/dateutil
%dir %{python3_sitelib}/dateutil/__pycache__
%dir %{python3_sitelib}/dateutil/tz
%dir %{python3_sitelib}/dateutil/tz/__pycache__
%dir %{python3_sitelib}/dateutil/parser
%dir %{python3_sitelib}/dateutil/parser/__pycache__

%changelog
* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 2.9.0.post0-1
- Initial build of python3-dateutil 2.9.0.post0
