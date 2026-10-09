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
%{expand: %%global py3ver %(echo `%{__ospython} -P -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-ua-parser
Version:        0.18.0
Release:        1%{?dist}
Summary:        Python port of Browserscope's user agent parser
License:        Apache-2.0
URL:            https://github.com/ua-parser/uap-python
Source0:        https://files.pythonhosted.org/packages/source/u/ua-parser/ua-parser-0.18.0.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# setup.py's build_py compiles regexes.yaml with PyYAML
BuildRequires:  python3.12-pyyaml

%description
Python port of Browserscope's user agent parser.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n ua-parser-0.18.0
# PyYAML comes from the build root; stop setuptools from fetching it
sed -i '/^\s*setup_requires=\["pyyaml"\],$/d' setup.py

%build
%{__ospython} setup.py build

%install
%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES
find %{buildroot}%{python3_sitelib} -mindepth 1 -type d | sed "s|%{buildroot}||" | sed 's/^/%dir /' >> INSTALLED_FILES

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import ua_parser"

%files -f INSTALLED_FILES
%defattr(-,root,root)

%changelog
* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 0.18.0-1
- Package ua-parser 0.18.0 for Python 3.12 (pgAdmin 4 dependency stack)
