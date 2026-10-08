%global pyft_minor %!{PYFT_MINOR}
%global py_prefix /opt/percona-python%{pyft_minor}t
%global py_bin %{py_prefix}/bin/python%{pyft_minor}t
%global py_sitelib %{py_prefix}/lib/python%{pyft_minor}t/site-packages
%global pgmajor %!{STORMWEAVER_PG_MAJOR}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif

# the extension lives in the interpreter's /opt tree: no provides from there,
# no python(abi) or private libpython requires
%global __provides_exclude_from ^%{py_prefix}/.*$
%global __requires_exclude ^(libpython3\\.[0-9]+t|python\\(abi\\)|/opt/percona-python.*)
%undefine __brp_mangle_shebangs
%global _python_bytecompile_extra 0
%global _python_bytecompile_errors_terminate_build 0
%global __brp_python_bytecompile %{nil}

Name:           stormweaver
Version:        1.0.0
Release:        1%{?dist}
Summary:        Concurrent database testing tool
License:        MIT
URL:            https://github.com/Percona-Lab/stormweaver
Source0:        %{name}-%{version}.tar.gz
Source1:        stormweaver.launcher
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
ExclusiveArch:  x86_64 aarch64

%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc-c++
BuildRequires:  gcc-toolset-%{gts_version}-annobin-plugin-gcc
%else
BuildRequires:  gcc-c++
%endif
BuildRequires:  cmake >= 3.22
BuildRequires:  percona-python%{pyft_minor}t
BuildRequires:  percona-python%{pyft_minor}t-pytest
BuildRequires:  percona-postgresql%{pgmajor}-devel
BuildRequires:  zlib-devel
%if 0%{?suse_version}
BuildRequires:  ninja
BuildRequires:  pkg-config
BuildRequires:  libopenssl-3-devel
BuildRequires:  libmariadb-devel
BuildRequires:  libcryptopp-devel
%else
BuildRequires:  ninja-build
BuildRequires:  pkgconfig
BuildRequires:  openssl-devel
BuildRequires:  mariadb-connector-c-devel
BuildRequires:  cryptopp-devel
%endif

Requires:       percona-python%{pyft_minor}t
Requires:       percona-postgresql%{pgmajor}-libs
Recommends:     percona-python%{pyft_minor}t-pytest

%description
StormWeaver is a concurrent database testing tool: a C++23 core (metadata,
actions, workers, SQL) driven from free-threaded Python scenarios. It starts
its own PostgreSQL or MySQL servers from an installation directory given with
-i, so no server package is required. Runs on %{py_prefix}; the
stormweaver.testing pytest plugin needs percona-python%{pyft_minor}t-pytest.

%prep
%setup -q

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
export CXXFLAGS="%{optflags}"
cmake -S . -B build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DPython_EXECUTABLE=%{py_bin} \
    -DPG_CONFIG=/usr/pgsql-%{pgmajor}/bin/pg_config \
    -DSTORMWEAVER_PYTHON_INSTALL_DIR=%{py_sitelib}
cmake --build build

%install
DESTDIR=%{buildroot} cmake --install build
install -D -m 0755 %{SOURCE1} %{buildroot}%{_bindir}/stormweaver
install -D -m 0644 config/stormweaver.toml %{buildroot}%{_sysconfdir}/stormweaver/stormweaver.toml
mkdir -p %{buildroot}%{_datadir}/stormweaver
cp -r scenarios %{buildroot}%{_datadir}/stormweaver/scenarios
find %{buildroot}%{_datadir}/stormweaver -name __pycache__ -prune -exec rm -rf {} +
# bytecode from our own interpreter, paths recorded without the buildroot
%{py_bin} -m compileall -q -s %{buildroot} %{buildroot}%{py_sitelib}/stormweaver

%check
build/core/tests/unit/test-stormweaver-unit
PYTHONPATH=%{buildroot}%{py_sitelib} %{py_bin} -m pytest tests/unit -q -p no:cacheprovider

%files
%license LICENSE
%doc README.md
%{_bindir}/stormweaver
%dir %{_sysconfdir}/stormweaver
%config(noreplace) %{_sysconfdir}/stormweaver/stormweaver.toml
%{_datadir}/stormweaver
%{py_sitelib}/stormweaver
%{py_sitelib}/stormweaver-*.dist-info

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{STORMWEAVER_VERSION}-1
- stormweaver %!{STORMWEAVER_VERSION} packaged for the tools:stormweaver project
