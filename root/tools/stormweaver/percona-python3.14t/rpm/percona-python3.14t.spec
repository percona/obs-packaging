# Free-threaded CPython under /opt/percona-python<minor>t: the runtime for
# stormweaver. Modelled on ppg/common/deps/tarballs/percona-python3.
%global pyft_minor %!{PYFT_MINOR}
%global py_prefix /opt/percona-python%{pyft_minor}t
%global py_bin %{py_prefix}/bin/python%{pyft_minor}t

# self-contained /opt tree: leak no provides, do not require our own libpython
# or a python(abi), keep stdlib shebangs as they are
%global __provides_exclude_from ^%{py_prefix}/.*$
%global __requires_exclude ^(libpython3\\.[0-9]+t|python\\(abi\\)|/usr/bin/python|/usr/local/bin/python|/usr/bin/env)
%undefine __brp_mangle_shebangs
# the rpath into our own lib/ is the design, EL10 check-rpaths must not abort on it
%global __brp_check_rpaths %{nil}
%global _python_bytecompile_extra 0
%global _python_bytecompile_errors_terminate_build 0
%global __brp_python_bytecompile %{nil}

Name:           percona-python%{pyft_minor}t
Version:        %!{PYFT_VERSION}
Release:        1%{?dist}
Summary:        Free-threaded CPython %{pyft_minor} under %{py_prefix}
License:        Python-2.0.1
URL:            https://www.python.org/
Source0:        Python-%{version}.tar.xz
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  libffi-devel
BuildRequires:  zlib-devel
BuildRequires:  xz-devel
BuildRequires:  readline-devel
BuildRequires:  ncurses-devel
BuildRequires:  libuuid-devel
BuildRequires:  tar
BuildRequires:  findutils
%if 0%{?suse_version}
BuildRequires:  libopenssl-3-devel
BuildRequires:  libbz2-devel
BuildRequires:  sqlite3-devel
BuildRequires:  libexpat-devel
BuildRequires:  gdbm-devel
%else
BuildRequires:  redhat-rpm-config
BuildRequires:  openssl-devel
BuildRequires:  bzip2-devel
BuildRequires:  sqlite-devel
BuildRequires:  expat-devel
BuildRequires:  gdbm-devel
%endif

%description
CPython %{version} built from the python.org source with --disable-gil
(free-threaded) and --prefix=%{py_prefix}. Complete stdlib, pip and venv.
Runtime for stormweaver; usable for free-threaded venvs
(%{py_bin} -m venv DIR).

%prep
%setup -q -n Python-%{version}

%build
./configure \
    --prefix=%{py_prefix} \
    --disable-gil \
    --enable-shared \
    --without-static-libpython \
    --with-ensurepip=install \
    CFLAGS="%{optflags}" \
    LDFLAGS="-Wl,-rpath,%{py_prefix}/lib"
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}
# no test suite, no tk/idle, no test extension modules
rm -rf %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/test \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/idlelib \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/tkinter \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/turtledemo \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/turtle.py
rm -f %{buildroot}%{py_prefix}/bin/idle%{pyft_minor}t %{buildroot}%{py_prefix}/bin/idle3
rm -f %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/lib-dynload/_test*.so \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/lib-dynload/_ctypes_test*.so \
    %{buildroot}%{py_prefix}/lib/python%{pyft_minor}t/lib-dynload/_xxtestfuzz*.so
# unversioned aliases keep pip/venv tooling happy; python3 stays our free-threaded build
ln -sf python%{pyft_minor}t %{buildroot}%{py_prefix}/bin/python3
ln -sf python%{pyft_minor}t %{buildroot}%{py_prefix}/bin/python

%check
# the buildroot tree is not at its final prefix yet: point the loader and
# the interpreter at it explicitly
export LD_LIBRARY_PATH=%{buildroot}%{py_prefix}/lib
export PYTHONHOME=%{buildroot}%{py_prefix}
%{buildroot}%{py_bin} -c '
import sys, ssl, hashlib, sqlite3, zlib, ctypes, bz2, lzma, readline, uuid, _uuid, curses, dbm.gnu, dbm.ndbm
assert not sys._is_gil_enabled(), "GIL enabled, --disable-gil did not take"
assert sys.version_info[:2] == tuple(int(x) for x in "%{pyft_minor}".split(".")), sys.version
print("free-threaded", sys.version)
'
%{buildroot}%{py_bin} -m pip --version

%files
%license LICENSE
%{py_prefix}

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PYFT_VERSION}-1
- Free-threaded CPython %!{PYFT_VERSION} under /opt/percona-python%!{PYFT_MINOR}t
