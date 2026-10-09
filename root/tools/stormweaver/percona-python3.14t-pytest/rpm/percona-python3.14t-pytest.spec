# pytest and its pure-python deps installed from wheels into the
# percona-python<minor>t prefix. The macro block mirrors percona-python3.14t.
%global pyft_minor %!{PYFT_MINOR}
%global py_prefix /opt/percona-python%{pyft_minor}t
%global py_bin %{py_prefix}/bin/python%{pyft_minor}t
%global py_sitelib %{py_prefix}/lib/python%{pyft_minor}t/site-packages
%global __provides_exclude_from ^%{py_prefix}/.*$
%global __requires_exclude ^(libpython3\\.[0-9]+t|python\\(abi\\)|/opt/percona-python.*|/usr/bin/env)
%undefine __brp_mangle_shebangs
%global _python_bytecompile_extra 0
%global _python_bytecompile_errors_terminate_build 0
%global __brp_python_bytecompile %{nil}
%global debug_package %{nil}

Name:           percona-python%{pyft_minor}t-pytest
Version:        %!{PYTEST_VERSION}
Release:        %!{BUNDLE_RELEASE}%{?dist}
Summary:        pytest for percona-python%{pyft_minor}t
License:        MIT AND BSD-2-Clause
URL:            https://pytest.org/
BuildArch:      noarch
Source0:        pytest-%!{PYTEST_VERSION}.tar.gz
Source1:        pytest-%!{PYTEST_VERSION}-py3-none-any.whl
Source2:        pluggy-%!{PLUGGY_VERSION}-py3-none-any.whl
Source3:        iniconfig-%!{INICONFIG_VERSION}-py3-none-any.whl
Source4:        packaging-%!{PACKAGING_VERSION}-py3-none-any.whl
Source5:        pygments-%!{PYGMENTS_VERSION}-py3-none-any.whl
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>

BuildRequires:  percona-python%{pyft_minor}t
Requires:       percona-python%{pyft_minor}t

%description
pytest %{version} with pluggy, iniconfig, packaging and pygments installed
into %{py_prefix} from their pure-python wheels. Provides %{py_prefix}/bin/pytest.

%prep
# wheels are installed as-is, nothing to unpack

%build

%install
%{py_bin} -m pip install --no-deps --no-index --no-warn-script-location --root %{buildroot} \
    %{SOURCE1} %{SOURCE2} %{SOURCE3} %{SOURCE4} %{SOURCE5}
# recompile so the .pyc files record the install path, not the buildroot
%{py_bin} -m compileall -q -f -d %{py_sitelib} %{buildroot}%{py_sitelib}
# file list: pip owns the files, we own every directory it created below site-packages
( cd %{buildroot} && find opt -type f -o -type l | sed 's|^|/|' ;
  cd %{buildroot} && find .%{py_sitelib} -mindepth 1 -type d | sed 's|^\.|%dir |' ) > %{_builddir}/files.list

%check
PYTHONPATH=%{buildroot}%{py_sitelib} %{py_bin} -m pytest --version

%files -f %{_builddir}/files.list

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PYTEST_VERSION}-%!{BUNDLE_RELEASE}
- pytest %!{PYTEST_VERSION} for percona-python%!{PYFT_MINOR}t
