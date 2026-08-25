# PERCONA: tarball-only helper package.
#
# The binary tarball must run on hosts that do not ship libreadline at all
# (minimal Debian/Ubuntu images).  The staging server package builds psql
# against the host's libreadline, which forced the tarball to carry an
# LD_PRELOAD/symlink wrapper around psql.bin.  This package rebuilds ONLY the
# psql client from the very same PostgreSQL source, configured with
# --with-libedit-preferred, so it links BSD libedit instead; the tarball
# bundles libedit next to it and drops the wrapper.
#
# It lives in ppg:staging:%!{PG_MAJOR_VERSION}:tarballs (not in staging
# itself): it is PG-version-bound, is never published to a distro repository
# and must be compiled against exactly the EL base of the tarball that
# bundles it.  Hence the RockyLinux_8/RockyLinux_9 build repos in this
# project's project.yaml.

%undefine _package_note_file

%global pgmajorversion %!{PG_MAJOR_VERSION}
%global pgbaseinstdir  /usr/pgsql-%{pgmajorversion}
# Non-conflicting install location: the psql from the server package owns
# %%{pgbaseinstdir}/bin/psql, and both RPMs are installed in the same
# simpleimage chroot.  build-tarball.sh copies this one over it.
%global psqldir        %{_libexecdir}/percona-psql

Summary:        PostgreSQL interactive terminal linked against libedit
Name:           percona-psql
# Placeholder: rewritten by the OBS set_version source service (see obs/_service).
Version:        1.0.0
Release:        1%{?dist}
License:        PostgreSQL
Group:          Productivity/Databases/Tools
Url:            https://www.postgresql.org/
Vendor:         Percona, LLC

Source0:        percona-psql-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  bison
BuildRequires:  flex
# The full perl meta-package, like the server spec: the in-tree code
# generators (genbki.pl and friends) need modules that perl-interpreter alone
# does not carry on EL9 (lib.pm, Data::Dumper, ...).
BuildRequires:  perl
# EL8: PowerTools (RockyLinux:8/devel path).  EL9: CRB, part of
# RockyLinux:9/standard.  Deliberately NO readline-devel: configure must not
# be able to find readline, so the libedit link is unambiguous.
BuildRequires:  libedit-devel
BuildRequires:  zlib-devel
BuildRequires:  openssl-devel
# readelf, for the %%check link gate.
BuildRequires:  binutils

%description
The PostgreSQL interactive terminal (psql), built from the same source as
percona-postgresql%{pgmajorversion} but linked against BSD libedit instead of
GNU readline.  Used exclusively by the Percona Software for PostgreSQL binary
tarball, which bundles libedit and therefore needs no readline on the host.

%prep
%setup -q -n percona-psql-%{version}

%build
CFLAGS="${CFLAGS:-%optflags}"
# Same -ffast-math strip as the server build.
CFLAGS=`echo $CFLAGS|xargs -n 1|grep -v ffast-math|xargs -n 100`
export CFLAGS
LDFLAGS="-Wl,--as-needed"; export LDFLAGS

# Minimal configuration: psql only needs libpq, src/port and src/common, so
# every optional server-side dependency is off.  --enable-rpath (the default,
# stated explicitly) puts %%{pgbaseinstdir}/lib in psql's RUNPATH, matching
# the server build — build-tarball.sh rewrites it to $ORIGIN/../lib like it
# does for every other tarball binary.
# ICU is on by default since PostgreSQL 16, hence --without-icu.
./configure \
        --enable-rpath \
        --prefix=%{pgbaseinstdir} \
        --includedir=%{pgbaseinstdir}/include \
        --libdir=%{pgbaseinstdir}/lib \
        --datadir=%{pgbaseinstdir}/share \
        --with-libedit-preferred \
        --with-openssl \
        --without-icu

# psql includes generated headers (kwlist/fmgroids/...), so build those first.
MAKELEVEL=0 %{__make} -C src/backend submake-generated-headers

# Build psql's prerequisite trees one at a time. src/bin/psql's "all" target
# fans out into submake-libpq, submake-libpgport and submake-libpgfeutils,
# which under -j start several concurrent makes in src/port and src/common
# and race on the same static archives ("ar: unable to copy file
# 'libpgport.a'").  The full server build never hits this because src/port and
# src/common are already up to date by the time src/bin is reached.
for d in src/port src/common src/interfaces/libpq src/fe_utils; do
        %{__make} %{?_smp_mflags} -C $d
done
%{__make} %{?_smp_mflags} -C src/bin/psql

%install
install -D -m 0755 src/bin/psql/psql %{buildroot}%{psqldir}/psql

%check
# The whole point of this package: libedit in, readline out. Checked on the
# binary that actually ships (the buildroot copy, post-strip).
PSQL=%{buildroot}%{psqldir}/psql
readelf -d $PSQL | grep NEEDED
readelf -d $PSQL | grep -q 'NEEDED.*libedit\.so\.0'
readelf -d $PSQL | grep -q 'NEEDED.*libpq\.so\.5'
if readelf -d $PSQL | grep -q 'libreadline'; then
        echo "ERROR: psql is linked against libreadline"
        exit 1
fi

%files
%dir %{psqldir}
%{psqldir}/psql

%changelog
* Tue Aug 25 2026 Ricardo Dias <ricardo.dias@percona.com> - 1.0.0-1
- Initial package: psql linked against libedit for the binary tarball.
