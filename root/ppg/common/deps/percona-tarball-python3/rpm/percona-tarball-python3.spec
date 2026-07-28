# PERCONA PACKAGE for ppg:common:deps (RockyLinux_8 and RockyLinux_9 only).
#
# /opt-prefixed CPython runtime consumed by the Percona PostgreSQL binary
# tarball (QA items 5 and 6 of the 2026-07 tarball QA round).
#
# Why this exists: the tarball bundles the RPM-built plpython3.so, which
# links libpython3.12.so.1.0; the distro libpython's compiled-in prefix
# is /usr, so the embedded interpreter looks for its stdlib at
# /usr/lib64/python3.12 — a path that does not exist on the tarball's
# target hosts. plpython3u only worked when the server was started
# through an env-exporting wrapper (PYTHONHOME) and QA proved any wrapper
# bypass crashes the backend. This package builds CPython from source
# with --prefix=/opt/percona-python3, so libpython3.12.so.1.0 finds its
# stdlib at /opt/percona-python3/lib/python3.12 and plpython3u works with
# ZERO environment variables — the official tarball's mechanism.
#
# Version: one 3.12.x for both bases (3.12.13 is the newest upstream
# 3.12, and the same version both distros ship as python3.12). The
# percona-postgresql17 staging spec steers plpython at python3.12 on both
# EL8 and EL9 (DT_NEEDED libpython3.12.so.1.0), the embedding ABI is
# stable within 3.12, and the staging python3.12-* site-packages copied
# into the tarball for patroni (psycopg2 etc.) are cp312.
#
# Built --enable-shared with an rpath to /opt/percona-python3/lib so
# bin/python3 finds its own libpython, and --with-ensurepip=install so
# pip3 ships. The stdlib is complete (ssl, sqlite3, zlib, bz2, lzma,
# readline, curses, uuid, ctypes); lib/python3.12/test is kept because
# the official tarball ships it. .pyc files are NOT stripped here — the
# tarball build strips bytecode at artifact level (QA item 6).
#
# The name is deliberately distinct from the distro python3.12 and
# everything installs under /opt/percona-python3: nothing shadows system
# packages. ppg:common:deps is publish=false project-wide.

%global py_prefix /opt/percona-python3
%global py_major 3.12

# PERCONA: self-contained /opt runtime — do not leak provides from the
# /opt tree, and libpython is our own file (do not require it). ELF
# requires on system libs (openssl, libffi, sqlite, ...) are kept.
%global __provides_exclude_from ^%{py_prefix}/.*$
# (stdlib scripts carry /usr/bin/env and even /usr/local/bin/python
# shebangs — those must not become install-time file dependencies)
%global __requires_exclude ^(libpython3\\.12|python\\(abi\\)|/usr/bin/python|/usr/local/bin/python|/usr/bin/env)
# PERCONA: keep /opt shebangs untouched and do not let the brp scripts
# bytecompile our tree with the system interpreter (wrong magic).
%undefine __brp_mangle_shebangs
%global _python_bytecompile_extra 0
%global _python_bytecompile_errors_terminate_build 0

Name:           percona-tarball-python3
Version:        3.12.13
Release:        2%{?dist}
Summary:        CPython runtime under /opt/percona-python3 for the Percona PostgreSQL binary tarball
License:        Python-2.0.1
URL:            https://www.python.org/
Source0:        Python-%{version}.tar.xz
# PERCONA: built against OpenSSL >= 3.3 headers (Rocky 9 ships 3.5),
# _ssl/_hashlib would need OPENSSL_3.3.0/OPENSSL_3.4.0 symbol versions
# and fail to load inside a postgres backend on OpenSSL 3.0 hosts
# (Ubuntu 22.04/24.04, Debian 12) where the host libcrypto wins soname
# dedup. Force CPython's own 3.0-compatible fallbacks; inert on EL8
# (OpenSSL 1.1.1 headers). The %%check below pins the promise.
Patch0:         python-3.12-openssl30-symbol-compat.patch

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  redhat-rpm-config
BuildRequires:  openssl-devel
BuildRequires:  libffi-devel
BuildRequires:  zlib-devel
BuildRequires:  bzip2-devel
BuildRequires:  xz-devel
BuildRequires:  sqlite-devel
BuildRequires:  readline-devel
BuildRequires:  ncurses-devel
BuildRequires:  expat-devel
BuildRequires:  libuuid-devel
BuildRequires:  tar
BuildRequires:  findutils

%description
CPython %{version} built from the upstream source with
--prefix=/opt/percona-python3 and --enable-shared, so
libpython3.12.so.1.0's compiled-in prefix points the embedded interpreter
(plpython3.so inside the postgres backend) at the bundled stdlib without
any environment variables. Ships a complete stdlib and pip. Consumed by
the Percona PostgreSQL binary tarball build; not intended for standalone
installation.

%prep
%setup -q -n Python-%{version}
%patch0 -p1

%build
./configure \
    --prefix=%{py_prefix} \
    --enable-shared \
    --without-static-libpython \
    --with-ensurepip=install \
    CFLAGS="%{optflags}" \
    LDFLAGS="-Wl,-rpath,%{py_prefix}/lib"
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}

%check
# PERCONA: pin the OpenSSL symbol-version promise at the source. The
# OpenSSL-linking extension modules must not need symbol versions newer
# than the tarball's runtime floor: no OPENSSL_3.[1-9]* on EL9 (OpenSSL
# 3.0 hosts: Ubuntu 22.04/24.04, Debian 12) and no RHEL-only
# OPENSSL_1_1_1[a-z] version nodes on EL8 (stock OpenSSL 1.1 hosts:
# Debian 11). Everything else in lib-dynload must not link OpenSSL at
# all. Loud rpmbuild failure otherwise.
fail=0
dynload=%{buildroot}%{py_prefix}/lib/python%{py_major}/lib-dynload
for so in "$dynload"/_ssl.cpython-*.so "$dynload"/_hashlib.cpython-*.so; do
    # Guard the unmatched-glob case: if a module silently failed to build,
    # $so is the literal pattern, readelf errors and the || true below
    # would swallow it into a false PASS.
    [ -e "$so" ] || { echo "FATAL: expected module missing: $so"; fail=1; continue; }
    echo "checking OpenSSL symbol versions: $so"
%if 0%{?rhel} == 8
    bad=$(readelf -W --dyn-syms "$so" | grep -E '@OPENSSL_1_1_1[a-z]' || true)
%else
    bad=$(readelf -W --dyn-syms "$so" | grep -E '@OPENSSL_3\.[1-9]' || true)
%endif
    if [ -n "$bad" ]; then
        echo "FATAL: $so needs post-baseline OpenSSL symbol versions:"
        echo "$bad"
        fail=1
    fi
done
for so in "$dynload"/*.so; do
    case "$(basename "$so")" in _ssl.cpython-*|_hashlib.cpython-*) continue ;; esac
    if readelf -d "$so" | grep -qE 'NEEDED.*lib(ssl|crypto)'; then
        echo "FATAL: unexpected OpenSSL linkage in $so"
        fail=1
    fi
done
[ "$fail" -eq 0 ]

%files
%license LICENSE
%{py_prefix}

%changelog
* Tue Jul 28 2026 Percona Build/Release Team <eng-build@percona.com> - 3.12.13-2
- Keep _ssl/_hashlib at OpenSSL 3.0 versioned symbols: force CPython's
  X509_STORE_get1_objects polyfill and the pre-3.4 EVP_MD_CTX_size
  expansion so plpython3u's import ssl/hashlib works on OpenSSL 3.0
  hosts where the postgres backend has the host libcrypto mapped.
  Add a %%check gate asserting the symbol-version floor per base.

* Tue Jul 28 2026 Percona Build/Release Team <eng-build@percona.com> - 3.12.13-1
- Initial /opt/percona-python3 runtime for the Percona PostgreSQL binary
  tarball: CPython 3.12.13 built from upstream source with the prefix
  compiled to /opt/percona-python3, so the RPM-built plpython3.so finds
  its stdlib with zero environment variables (tarball QA items 5 and 6).
