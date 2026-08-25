#!/bin/bash
# Builds the Percona PostgreSQL binary tarball from RPM-installed content.
# Runs chrooted as root inside an OBS simpleimage buildroot; writes the
# final artifact (with its official self-derived name) directly into
# /usr/src/packages/OTHER, where OBS collects build results. The recipe's
# own /.simpleimage.tar.gz handling is skipped (#!NoTarBall, and no such
# file is created).
set -e

PG_MAJOR=$(basename "$(ls -d /usr/pgsql-*)" | sed 's/^pgsql-//')
[ -n "$PG_MAJOR" ] || { echo "FATAL: no /usr/pgsql-* tree found" >&2; exit 1; }

# Python used by THIS SCRIPT ONLY (the section-14a ELF string patcher and
# its section-15 gate) — NOT the python shipped in the tarball. python3.12
# is no longer a direct BuildRequires, but it still reaches the chroot
# transitively (patroni's python3.12-* site-packages deps require the
# interpreter); /usr/bin/python3 is the fallback. The bundled
# /opt/percona-python3 interpreter is deliberately not used here: it is
# itself part of the patched payload.
# (|| true inside the substitution: under set -e, both lookups failing
# would abort the assignment itself and the FATAL below — with its useful
# message — would never run.)
PY_BIN=$(command -v python3.12 || command -v python3 || true)
[ -n "$PY_BIN" ] || { echo "FATAL: no chroot python3 for the ELF patch helper" >&2; exit 1; }

PG_PREFIX=/opt/percona-postgresql${PG_MAJOR}
PYTHON_PREFIX=/opt/percona-python3
PERL_PREFIX=/opt/percona-perl
TCL_PREFIX=/opt/percona-tcl
HAPROXY_PREFIX=/opt/percona-haproxy
# Lean /opt GDAL+PROJ runtimes (percona-gdal / percona-proj RPMs). Installed
# by their RPMs like the language runtimes, and shipped as two DATA-ONLY
# top-level components (section 13a): what the artifact needs from them is
# the resource directory whose path is compiled into the libraries. The
# libraries themselves are bundled into $PG_PREFIX/lib by section 13.
GDAL_PREFIX=/opt/percona-gdal
PROJ_PREFIX=/opt/percona-proj

###############################################################
# 0. Language runtimes installed by the percona-* RPMs
###############################################################
# The percona-{perl,tcl,python3} BuildRequires install COMPLETE
# from-source runtime trees at /opt/percona-{perl,tcl,python3} with every
# path compiled to the /opt prefix. That is what makes plperl/pltcl/
# plpython3 work with ZERO environment variables (QA items 3-5): the PL
# .so RUNPATHs set in section 14 point at these trees, and the trees'
# compiled-in defaults (@INC, TCL_LIBRARY, sys.prefix) already say /opt.
# Assert the trees are present and derive the version strings FROM the
# installed trees — the distro interpreters that used to answer these
# questions are no longer in the chroot by design.
PY_VER=$(basename "$(ls -d $PYTHON_PREFIX/lib/python3.*)" | sed 's/^python//')
PERL_VER=$(basename "$(ls -d $PERL_PREFIX/lib/5.*)")
TCL_VER=$(basename "$(ls -d $TCL_PREFIX/lib/tcl8.*)" | sed 's/^tcl//')
PERL_CORE_DIR=$PERL_PREFIX/lib/${PERL_VER}/CORE
# bin/pip3 is asserted because section 7 later symlinks bin/pip -> pip3:
# if ensurepip ever stops running in the runtime RPM, catch it here rather
# than ship a dangling symlink.
for f in "$PYTHON_PREFIX/bin/python3" \
         "$PYTHON_PREFIX/bin/pip3" \
         "$PYTHON_PREFIX/lib/libpython${PY_VER}.so.1.0" \
         "$PERL_PREFIX/bin/perl" \
         "$PERL_CORE_DIR/libperl.so" \
         "$TCL_PREFIX/bin/tclsh${TCL_VER}" \
         "$TCL_PREFIX/lib/libtcl${TCL_VER}.so" \
         "$TCL_PREFIX/lib/tcl${TCL_VER}/init.tcl"; do
    [ -e "$f" ] || { echo "FATAL: runtime file $f missing — percona-* RPM not installed?" >&2; exit 1; }
done
# patroni's site-packages come from the distro python3.12-* packages
# (section 8) and are only compatible if their X.Y equals the bundled
# interpreter's.
[ -d "/usr/lib/python${PY_VER}/site-packages" ] || {
    echo "FATAL: /usr/lib/python${PY_VER}/site-packages missing — bundled python ${PY_VER} vs distro python3.12-* stack mismatch" >&2
    exit 1
}

###############################################################
# 0a. GDAL/PROJ runtimes + psql client from the helper RPMs
###############################################################
# percona-gdal/percona-proj (ppg:common:deps) replace EPEL's gdal-libs/proj
# for the PostGIS libraries the tarball bundles. EPEL's cost us ~70 surplus
# shared objects (armadillo/BLAS -> a FlexiBLAS ELF constructor that
# abort()s on Rocky hosts, hdf/netcdf/OPeNDAP/poppler/xerces/ODBC/mariadb,
# and libtirpc/libexpat/libpcre2-posix) and compiled their resource paths
# to /usr/share/{gdal,proj}, which does not exist on a tarball host.
# Ours are lean and have those paths compiled to /opt/percona-*/share.
GDAL_LIB=$(ls "$GDAL_PREFIX"/lib/libgdal.so.[0-9]* 2>/dev/null | head -1)
PROJ_LIB=$(ls "$PROJ_PREFIX"/lib/libproj.so.[0-9]* 2>/dev/null | head -1)
[ -n "$GDAL_LIB" ] || { echo "FATAL: no $GDAL_PREFIX/lib/libgdal.so.* — percona-gdal not installed?" >&2; exit 1; }
[ -n "$PROJ_LIB" ] || { echo "FATAL: no $PROJ_PREFIX/lib/libproj.so.* — percona-proj not installed?" >&2; exit 1; }
for f in "$GDAL_PREFIX/share/gdal/gdalicon.png" "$PROJ_PREFIX/share/proj/proj.db"; do
    [ -f "$f" ] || { echo "FATAL: resource file $f missing — percona-gdal/percona-proj data dir not at the compiled path" >&2; exit 1; }
done
# The prjconf `Prefer: percona-gdal` / `Prefer: percona-proj` lines are what
# make PostGIS's libgdal.so.NN()(64bit)/libproj.so.NN()(64bit) Requires
# resolve to ours. If some other package Requires the EPEL packages BY NAME,
# Prefer cannot help and both libgdal flavours would sit in the chroot — with
# copy_deps free to bundle the fat one. Fail the build so we find out.
for epel in gdal gdal-libs proj proj-libs; do
    if rpm -q "$epel" >/dev/null 2>&1; then
        echo "FATAL: EPEL $epel is installed in the chroot ($(rpm -q "$epel")) — it must be replaced by percona-gdal/percona-proj (prjconf Prefer:)" >&2
        exit 1
    fi
done
# percona-psql (this project's RockyLinux_8/RockyLinux_9 build repos): psql
# linked against BSD libedit instead of the host's libreadline. Section 2b
# copies it over the server RPM's psql, which is what let the readline
# LD_PRELOAD/symlink wrapper be deleted.
PSQL_LIBEDIT=/usr/libexec/percona-psql/psql
[ -f "$PSQL_LIBEDIT" ] || { echo "FATAL: $PSQL_LIBEDIT missing — percona-psql not installed?" >&2; exit 1; }

###############################################################
# Universal host baseline — the ONLY libraries taken from the
# target system; everything else must be bundled
###############################################################
# CONTRACT: every token below names a library that is present on EVERY
# supported minimal host, so a tarball binary may resolve it from the host
# instead of carrying a copy. Verified 2026-07-29 against debian:12,
# ubuntu:24.04 and rockylinux:9-minimal (the three probe images):
#
#   * glibc family + the dynamic loader (libc/libm/libpthread/libdl/librt/
#     libresolv/libnss_*/ld-linux) and libgcc_s/libstdc++ — the toolchain
#     runtime of any Linux userland.
#   * libz/libbz2/liblz4/liblzma/libzstd — pulled in by dpkg/rpm, systemd
#     and coreutils on every one of the three images.
#   * libsystemd/libselinux/libpam*/libaudit/libcap*/libgcrypt/libgpg-error
#     — the pam/systemd stack every image ships (and which the tarball only
#     ever touches through the distro's own binaries).
#   * libtinfo — bash links it, so it exists wherever a shell does; needed
#     by libedit (bin/psql) and by python's readline extension.
#   * libssl/libcrypto — deliberately host-provided: that is exactly what
#     the ssl1.1/ssl3 variant labels promise, and the section-15 OpenSSL
#     host-ABI audit turns the promise into a tested guarantee.
#
# NOT on this list, i.e. BUNDLED (each one an acceptance-testing finding):
#   * libidn2/libunistring/libnghttp2 — sonames drift across distro
#     generations (libunistring.so.2 on EL8/EL9 vs .so.5 on current
#     Debian/Ubuntu) and minimal hosts do not ship them at all.
#   * libtirpc/libnsl/libeconf/libpcre2-8/libpcre2-posix/libexpat/
#     libreadline — all were excluded until the 2026-07 QA round, all are
#     ABSENT from at least one probe image (libpcre2-posix on default
#     Debian/Ubuntu, libtirpc/libnsl on debian:12-slim, libreadline on
#     every minimal image), and libreadline additionally has the EL8 .so.7
#     vs modern .so.8 soname split that forced the old psql wrapper. Once
#     unexcluded they flow through copy_deps/the NEEDED audit
#     automatically; the section-15 baseline gate asserts they never
#     silently come back.
#
# NOTE: the string literal below is a whitespace-separated token list —
# every word in it becomes a live glob prefix in is_system_lib, so never
# put comments inside the quotes.
SYSTEM_LIBS_EXCLUDE="
libc.so
libm.so
libpthread.so
libdl.so
librt.so
libresolv.so
libnss_
ld-linux
libgcc_s.so
libstdc++.so
libz.so
libbz2.so
liblz4.so
liblzma.so
libzstd.so
libsystemd.so
libselinux.so
libpam.so
libpam_misc.so
libaudit.so
libcap.so
libcap-ng.so
libgcrypt.so
libgpg-error.so
libssl.so
libcrypto.so
libtinfo.so
"

# Sonames that were on the exclude list before the 2026-07 QA round and must
# now always be BUNDLED (see the contract above). The section-15 baseline
# gate uses this list twice: no token may be matched by is_system_lib, and
# no bundled ELF may NEED one of them without the artifact carrying it.
# Deliberately NOT a second copy of the baseline: one literal list, one
# removed-tokens list, no third place to keep in sync.
FORMERLY_EXCLUDED_LIBS="
libtirpc.so
libnsl.so
libeconf.so
libpcre2-8.so
libpcre2-posix.so
libexpat.so
libreadline.so
"

is_system_lib() {
    local libname=$(basename "$1")
    local pattern
    for pattern in $SYSTEM_LIBS_EXCLUDE; do
        case "$libname" in
            ${pattern}*) return 0 ;;
        esac
    done
    return 1
}

###############################################################
# Helper: copy .so deps of an ELF file into destlib,
# preserving symlink chains and filtering system libs
###############################################################
copy_deps() {
    local binary="$1"
    local destlib="$2"
    ldd "$binary" 2>/dev/null | awk '/=>/ && $3 ~ /^\// {print $3}' | sort -u | while read lib; do
        [ -f "$lib" ] || continue
        is_system_lib "$lib" && continue
        # Resolve to real file and copy the whole symlink family
        local real=$(readlink -f "$lib")
        local dir=$(dirname "$real")
        local base=$(basename "$lib" | sed 's/\.so.*//')
        # The resolved real file may not match the ${base}.so* glob below
        # (e.g. libldap.so.2 -> libldap_r.so.2.0.200, libopenblaso.so.0 ->
        # libopenblaso-r0.3.29.so); copy it explicitly so the recreated
        # symlinks never dangle.
        cp -pn "$real" "$destlib/" 2>/dev/null || true
        # Copy real file + all related symlinks
        for f in "$dir"/${base}.so*; do
            [ -e "$f" ] || [ -L "$f" ] || continue
            if [ -L "$f" ]; then
                local target=$(readlink "$f")
                ln -sf "$target" "$destlib/$(basename "$f")" 2>/dev/null || true
            else
                cp -pn "$f" "$destlib/" 2>/dev/null || true
            fi
        done
    done
}

# Run copy_deps over all ELF files in a prefix (3 passes for dep depth).
# Any extra arguments are additional directory trees walked recursively for
# ELF .so files (e.g. python lib-dynload/ + site-packages C extensions),
# so their NEEDED libs are bundled too.
bundle_deps() {
    local prefix="$1"
    shift
    local libdir="$prefix/lib"
    mkdir -p "$libdir"
    for pass in 1 2 3; do
        {
            # sbin/ exists only for haproxy. find still walks the paths
            # that DO exist but exits non-zero on the missing one — the
            # || true keeps set -e from killing this subshell before the
            # extra-dirs find below has run.
            find "$prefix/bin" "$prefix/sbin" "$libdir" -maxdepth 1 -type f 2>/dev/null || true
            if [ $# -gt 0 ]; then find "$@" -type f -name '*.so*' 2>/dev/null; fi
        } | while read f; do
            file "$f" 2>/dev/null | grep -q ELF && copy_deps "$f" "$libdir" || true
        done
    done
}

# patchelf all ELF files in bin/, sbin/ and lib/ to given RPATH
patch_rpath() {
    local prefix="$1"
    local rpath="${2:-\$ORIGIN/../lib}"
    find "$prefix/bin" "$prefix/sbin" "$prefix/lib" -maxdepth 1 -type f 2>/dev/null | while read f; do
        file "$f" 2>/dev/null | grep -q ELF && \
            patchelf --set-rpath "$rpath" "$f" 2>/dev/null || true
    done
}

###############################################################
# 1. Create isolated prefix directories
###############################################################
# Only the SCRIPT-STAGED components are created here. The three language
# runtimes (percona-python3, percona-perl, percona-tcl) are installed into
# /opt by their percona-* RPMs (asserted in section 0) — creating
# them here would mask a missing runtime package.
for tool in percona-postgresql${PG_MAJOR} percona-pgbouncer percona-pgpool-II \
            percona-pgbackrest percona-pgbadger percona-patroni \
            percona-etcd percona-haproxy; do
    mkdir -p /opt/${tool}/{bin,lib}
done

###############################################################
# 2. PostgreSQL: /usr/pgsql-NN -> /opt/percona-postgresqlNN
###############################################################
cp -rp /usr/pgsql-${PG_MAJOR}/bin/. $PG_PREFIX/bin/
cp -rp /usr/pgsql-${PG_MAJOR}/lib/. $PG_PREFIX/lib/
cp -rp /usr/pgsql-${PG_MAJOR}/share $PG_PREFIX/
[ -d /usr/pgsql-${PG_MAJOR}/include ] && cp -rp /usr/pgsql-${PG_MAJOR}/include $PG_PREFIX/ || true
# doc/
mkdir -p $PG_PREFIX/doc
for d in /usr/share/doc/percona-postgresql${PG_MAJOR}*; do
    [ -d "$d" ] && cp -rp "$d" $PG_PREFIX/doc/ || true
done

###############################################################
# 2a. postgresql.conf.sample: revert RPM logging customizations
#     to upstream defaults and enable a /tmp unix socket
###############################################################
# The percona-postgresql RPM applies postgresql-conf.patch, which activates
# Red-Hat log-management defaults (logging_collector=on, log_directory='log',
# day-of-week rotation, ...) that assume the RPM's systemd-managed layout.
# The official from-source tarball ships the STOCK upstream sample, so revert
# those directives here (comment them back / restore upstream values).
#
# The /tmp unix socket is NOT handled here: initdb unconditionally rewrites
# the unix_socket_directories line in the generated postgresql.conf to its
# COMPILED-IN default, so a sample edit would have no effect. Section 14a
# instead patches that compiled default (/run/postgresql -> /tmp) inside
# every bundled ELF, matching the official from-source tarball's stock
# DEFAULT_PGSOCKET_DIR=/tmp.
CONF=$PG_PREFIX/share/postgresql.conf.sample
sed -i \
    -e "s|^log_destination = 'stderr'|#log_destination = 'stderr'|" \
    -e "s|^logging_collector = on|#logging_collector = off|" \
    -e "s|^log_directory = 'log'|#log_directory = 'log'|" \
    -e "s|^log_filename = 'postgresql-%a.log'|#log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'|" \
    -e "s|^log_rotation_age = 1d|#log_rotation_age = 1d|" \
    -e "s|^log_rotation_size = 0|#log_rotation_size = 10MB|" \
    -e "s|^log_truncate_on_rotation = on|#log_truncate_on_rotation = off|" \
    -e "s|^log_line_prefix = '%m \[%p\] '|#log_line_prefix = '%m [%p] '|" \
    "$CONF"
# Fail the build loudly if the RPM's sample changed shape so the reverts above
# no longer matched — otherwise we would silently re-ship the RH log-management
# defaults. All eight logging directives must end up commented.
if grep -qE "^(log_destination|logging_collector|log_directory|log_filename|log_rotation_age|log_rotation_size|log_truncate_on_rotation|log_line_prefix)[[:space:]]*=" "$CONF"; then
    echo "FATAL: an RH logging directive is still active in postgresql.conf.sample" >&2
    exit 1
fi

###############################################################
# 2b. PostgreSQL cleanup + libedit psql + gather.sql
###############################################################
# Remove RPM service helpers that don't belong in the tarball
rm -f $PG_PREFIX/bin/postgresql-${PG_MAJOR}-* 2>/dev/null || true

# gather.sql from percona-pg_gather (installed to pgsql share/contrib)
for f in /usr/pgsql-${PG_MAJOR}/share/contrib/gather.sql \
          /usr/share/percona-pg_gather/gather.sql /usr/bin/gather.sql \
          /usr/share/pgsql/gather.sql; do
    [ -f "$f" ] && cp "$f" $PG_PREFIX/bin/ && break || true
done

# psql: the libedit-linked client from percona-psql replaces the server
# RPM's readline-linked one. The RPM build links psql against the
# buildroot's GNU readline, which minimal target hosts do not ship at all —
# and the EL8 build needs the long-gone libreadline.so.7 soname. The old
# tarball worked around that with a psql.bin + shell-wrapper pair that
# LD_PRELOADed the host readline and, failing that, symlinked
# libreadline.so.7 at a host .so.8 inside the extraction dir. That whole
# machinery is GONE: percona-psql is the same PostgreSQL source configured
# --with-libedit-preferred, so bin/psql NEEDs libedit.so.0 (bundled by
# section 13's copy_deps, libedit itself needs only host-baseline
# libtinfo) and no readline is involved on any host. bin/psql is the REAL
# binary now, like every other tarball binary; section 13's patch_rpath
# rewrites its RUNPATH to $ORIGIN/../lib and section 15 asserts the link
# surface (libedit in, libreadline out).
install -m 0755 "$PSQL_LIBEDIT" $PG_PREFIX/bin/psql

# NOTE: postgres is shipped as the REAL binary — no env wrapper. The
# PERL5LIB/TCL_LIBRARY/PYTHONHOME exports the old wrapper carried are now
# compiled into the /opt runtime trees themselves (percona-* RPMs,
# see section 0), and QA proved any wrapper bypass (pg_ctl-less starts,
# bare `postgres -D`) broke all three PLs. Section 14 gives the PL .so
# files RUNPATHs that point at those trees.

###############################################################
# 3. pgBouncer
###############################################################
cp /usr/bin/pgbouncer /opt/percona-pgbouncer/bin/
[ -d /etc/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/etc && \
    cp -rp /etc/pgbouncer/. /opt/percona-pgbouncer/etc/ || true
# share/doc (RPM doc dir is unprefixed /usr/share/doc/pgbouncer; reference
# tarball layout is share/doc/pgbouncer/)
[ -d /usr/share/doc/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/share/doc && \
    cp -rp /usr/share/doc/pgbouncer /opt/percona-pgbouncer/share/doc/ || true
[ -d /usr/share/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/share && \
    cp -rp /usr/share/pgbouncer /opt/percona-pgbouncer/share/ || true

###############################################################
# 4. pgPool-II
###############################################################
find /usr/bin -maxdepth 1 \( -name 'pgpool' -o -name 'pcp_*' -o -name 'pg_md5' \
    -o -name 'pgslap' -o -name 'pgpool_*' \
    -o -name 'pg_enc' -o -name 'pgproto' \
    -o -name 'watchdog_setup' -o -name 'wd_cli' \) -exec cp {} /opt/percona-pgpool-II/bin/ \;
[ -d /etc/pgpool-II ] && \
    mkdir -p /opt/percona-pgpool-II/etc && \
    cp -rp /etc/pgpool-II/. /opt/percona-pgpool-II/etc/ || true
# share/ and include/
[ -d /usr/share/pgpool-II ] && cp -rp /usr/share/pgpool-II /opt/percona-pgpool-II/share/ || true
# Headers from the -devel package are installed flat into /usr/include
# (pcp.h, libpcp_ext.h, pool_*.h); reference layout nests them under
# include/pgpool2/. Use the RPM manifest to pick exactly those headers.
rpm -ql percona-pgpool-II-pg${PG_MAJOR}-devel 2>/dev/null | \
    grep '^/usr/include/.*\.h$' | while read -r h; do
    mkdir -p /opt/percona-pgpool-II/include/pgpool2
    cp -p "$h" /opt/percona-pgpool-II/include/pgpool2/
done

###############################################################
# 5. pgBackRest
###############################################################
cp /usr/bin/pgbackrest /opt/percona-pgbackrest/bin/
[ -d /etc/pgbackrest ] && \
    mkdir -p /opt/percona-pgbackrest/etc && \
    cp -rp /etc/pgbackrest/. /opt/percona-pgbackrest/etc/ || true
[ -f /etc/pgbackrest.conf ] && \
    mkdir -p /opt/percona-pgbackrest/etc && \
    cp /etc/pgbackrest.conf /opt/percona-pgbackrest/etc/ || true
# License (RPMs install %license files under /usr/share/licenses)
for d in /usr/share/licenses/percona-pgbackrest* /usr/share/doc/percona-pgbackrest*; do
    [ -f "$d/LICENSE" ] && cp "$d/LICENSE" /opt/percona-pgbackrest/pgbackrest_license && break || true
done

###############################################################
# 6. pgBadger -- flat layout (matches reference)
###############################################################
cp /usr/bin/pgbadger /opt/percona-pgbadger/pgbadger
# Point pgbadger at the bundled perl: the RPM script says /usr/bin/perl,
# which need not exist on a tarball target host. (The official tarball
# leaves this at `#!/usr/bin/env perl` — relying on a host perl being on
# PATH; the bundled interpreter is strictly more self-contained.)
sed -i "1s|^#!.*perl.*|#!/opt/percona-perl/bin/perl|" /opt/percona-pgbadger/pgbadger
rmdir /opt/percona-pgbadger/bin /opt/percona-pgbadger/lib 2>/dev/null || true
# Man page
find /usr/share/man -name 'pgbadger.1*' -exec sh -c 'f="{}"; case "$f" in *.gz) gunzip -c "$f" > /opt/percona-pgbadger/pgbadger.1p ;; *) cp "$f" /opt/percona-pgbadger/pgbadger.1p ;; esac' \; 2>/dev/null || true
# License and README (LICENSE lives under /usr/share/licenses, README under
# /usr/share/doc)
for d in /usr/share/doc/percona-pgbadger* /usr/share/licenses/percona-pgbadger*; do
    [ -d "$d" ] || continue
    [ -f "$d/LICENSE" ] && cp "$d/LICENSE" /opt/percona-pgbadger/LICENSE || true
    for readme in "$d"/README*; do
        [ -f "$readme" ] && cp "$readme" /opt/percona-pgbadger/README.md && break || true
    done
done

###############################################################
# 7. Python -> /opt/percona-python3 (tree installed by RPM)
###############################################################
# The percona-python3 RPM already installed the complete runtime
# (bin/python3.12 + python3, full stdlib incl. lib-dynload, libpython,
# include/, pkgconfig/, share/man, and a real pip via ensurepip — all
# shebangs and compiled paths already say /opt/percona-python3). The old
# flatten-from-system staging is gone. What remains here is the handful of
# utility scripts that come from OTHER packages in the chroot and ship in
# the official tarball's percona-python3/bin.
for script in syncobj_admin jp.py; do
    [ -f "/usr/bin/$script" ] && cp "/usr/bin/$script" $PYTHON_PREFIX/bin/ || true
done
# ydiff is a Python module with no /usr/bin script; create a wrapper
# (ydiff.py itself is copied into site-packages by section 8)
if [ -f /usr/lib/python${PY_VER}/site-packages/ydiff.py ]; then
    cat > $PYTHON_PREFIX/bin/ydiff << 'WEOF'
#!/opt/percona-python3/bin/python3
from ydiff import main
import sys
sys.exit(main())
WEOF
    chmod +x $PYTHON_PREFIX/bin/ydiff
fi
for script in $PYTHON_PREFIX/bin/syncobj_admin $PYTHON_PREFIX/bin/jp.py; do
    [ -f "$script" ] && \
        sed -i "1s|^#!.*python.*|#!/opt/percona-python3/bin/python3|" "$script" || true
done
# ensurepip creates pip3/pip3.12 but no plain `pip`; the official tarball
# ships one.
[ -e "$PYTHON_PREFIX/bin/pip" ] || ln -sf pip3 "$PYTHON_PREFIX/bin/pip"

###############################################################
# 8. Patroni -- copy from RPM-installed location into bundled Python
###############################################################
SITE_DEST=$PYTHON_PREFIX/lib/python${PY_VER}/site-packages
mkdir -p "$SITE_DEST"

# The distro python3.12-* packages install these under
# /usr/lib{,64}/python3.12/site-packages; the bundled interpreter is the
# same X.Y (asserted in section 0), so pure-python packages and cp312 C
# extensions are both usable. Package metadata ships as *.dist-info or
# *.egg-info depending on how each RPM was built — copy whichever form
# exists (this list is now load-bearing: the bundled python tree comes
# from our RPM, there is no wholesale distro site-packages copy anymore).
for pkg in patroni patroni-*.dist-info patroni-*.egg-info \
           click click-*.dist-info click-*.egg-info \
           dateutil python_dateutil-*.dist-info python_dateutil-*.egg-info \
           psutil psutil-*.dist-info psutil-*.egg-info \
           urllib3 urllib3-*.dist-info urllib3-*.egg-info \
           six.py six-*.dist-info six-*.egg-info \
           certifi certifi-*.dist-info certifi-*.egg-info \
           dns dnspython-*.dist-info dnspython-*.egg-info \
           pysyncobj pysyncobj-*.dist-info pysyncobj-*.egg-info \
           kazoo kazoo-*.dist-info kazoo-*.egg-info \
           etcd python_etcd-*.dist-info python_etcd-*.egg-info \
           boto3 boto3-*.dist-info boto3-*.egg-info \
           botocore botocore-*.dist-info botocore-*.egg-info \
           jmespath jmespath-*.dist-info jmespath-*.egg-info \
           s3transfer s3transfer-*.dist-info s3transfer-*.egg-info \
           psycopg2 psycopg2-*.dist-info psycopg2-*.egg-info \
           consul py_consul-*.dist-info py_consul-*.egg-info \
           prettytable prettytable-*.dist-info prettytable-*.egg-info \
           packaging packaging-*.dist-info packaging-*.egg-info \
           typing_extensions typing_extensions-*.dist-info typing_extensions-*.egg-info \
           requests requests-*.dist-info requests-*.egg-info \
           charset_normalizer charset_normalizer-*.dist-info charset_normalizer-*.egg-info \
           idna idna-*.dist-info idna-*.egg-info \
           yaml PyYAML-*.dist-info PyYAML-*.egg-info _yaml \
           wcwidth wcwidth-*.dist-info wcwidth-*.egg-info \
           cryptography cryptography-*.dist-info cryptography-*.egg-info \
           cffi cffi-*.dist-info cffi-*.egg-info _cffi_backend* \
           pycparser pycparser-*.dist-info pycparser-*.egg-info \
           ydiff.py ydiff-*.dist-info ydiff-*.egg-info; do
    for sitedir in /usr/lib/python${PY_VER}/site-packages /usr/lib64/python${PY_VER}/site-packages; do
        [ -d "$sitedir" ] || continue
        for match in "$sitedir"/$pkg; do
            [ -e "$match" ] && cp -rp "$match" "$SITE_DEST/" 2>/dev/null || true
        done
    done
done

# Copy patroni binaries, rewriting shebang to bundled Python
mkdir -p /opt/percona-patroni/bin
for pbin in patroni patronictl patroni_barman patroni_raft_controller patroni_aws patroni_wale_restore; do
    [ -f "/usr/bin/$pbin" ] || continue
    cp "/usr/bin/$pbin" "/opt/percona-patroni/bin/$pbin"
    sed -i "1s|^#!.*|#!/opt/percona-python3/bin/python3|" "/opt/percona-patroni/bin/$pbin"
done

# share/doc and license
mkdir -p /opt/percona-patroni/share/doc
for d in /usr/share/doc/percona-patroni*; do
    [ -d "$d" ] && cp -rp "$d"/. /opt/percona-patroni/share/doc/ || true
done
for d in /usr/share/licenses/percona-patroni* /usr/share/doc/percona-patroni*; do
    [ -f "$d/LICENSE" ] && cp "$d/LICENSE" /opt/percona-patroni/patroni_license && break || true
done
# Remove empty lib/ from patroni (Python app, no native libs)
rmdir /opt/percona-patroni/lib 2>/dev/null || true

###############################################################
# 9. etcd (Go static binary -- no deps to bundle)
###############################################################
for ebin in etcd etcdctl etcdutl; do
    [ -f "/usr/bin/$ebin" ] && cp "/usr/bin/$ebin" /opt/percona-etcd/bin/ || true
done
# Remove empty lib/ (etcd is statically linked)
rmdir /opt/percona-etcd/lib 2>/dev/null || true

###############################################################
# 10. Perl -> /opt/percona-perl (tree installed by RPM)
###############################################################
# The percona-perl RPM already installed the complete runtime
# (bin/perl + every core utility script with /opt shebangs, the full core
# module set at lib/<ver> with CORE/libperl, man pages) with the distro-
# matched version and ABI (5.26.3 on EL8, 5.32.1 on EL9 — the version
# plperl.so's libperl DT_NEEDED demands). The old flatten-from-system
# staging is gone.
#
# The old Net::SSLeay/IO::Socket::SSL prune is OBSOLETE: those are CPAN
# modules the distro shipped as vendor packages, and a from-source core
# perl build contains no OpenSSL bindings at all. Assert that stays true —
# an SSLeay XS module would link the BUILDROOT libssl and violate the ssl
# variant host-ABI promise (section 15), so its appearance must fail loudly
# rather than slip through.
if find "$PERL_PREFIX" \( -path '*/Net/SSLeay*' -o -path '*/IO/Socket/SSL*' \) | grep .; then
    echo "FATAL: OpenSSL perl bindings found under $PERL_PREFIX (core perl must not ship Net::SSLeay/IO::Socket::SSL)" >&2
    exit 1
fi

# libperl.so links libcrypt (libcrypt.so.2 on EL9 — a soname many target
# hosts do NOT provide, e.g. Debian/Ubuntu ship libcrypt.so.1), so the
# host copy cannot be relied on: bundle the buildroot's libcrypt family
# into CORE/ next to libperl (the official tarball does the same) and give
# libperl an $ORIGIN RPATH so it finds it there — RUNPATH is not
# transitive, plperl.so's RUNPATH does not help libperl's own NEEDED.
# bin/perl needs no patchelf: its compiled-in RPATH already points at
# CORE/, where both libperl and the bundled libcrypt live.
cp -a /usr/lib64/libcrypt.so* "$PERL_CORE_DIR/" 2>/dev/null || true
cp -a /usr/lib64/libxcrypt.so* "$PERL_CORE_DIR/" 2>/dev/null || true
LIBPERL_REAL=$(find "$PERL_CORE_DIR" -maxdepth 1 -name 'libperl.so.*' -not -type l | head -1)
[ -n "$LIBPERL_REAL" ] || { echo "FATAL: no libperl.so.* in $PERL_CORE_DIR" >&2; exit 1; }
patchelf --set-rpath '$ORIGIN' "$LIBPERL_REAL"

###############################################################
# 11. Tcl -> /opt/percona-tcl (tree installed by RPM)
###############################################################
# The percona-tcl RPM already installed the complete runtime
# (bin/tclsh8.6 with a compiled RPATH to /opt/percona-tcl/lib, the
# libtcl8.6.so whose compiled TCL_LIBRARY default is
# /opt/percona-tcl/lib/tcl8.6, the stdlib, and the bundled pkgs incl.
# sqlite3/tdbc/itcl/thread and bin/sqlite3_analyzer). Nothing to stage and
# no TCL_LIBRARY wrapper anymore: bin/tclsh is the RPM's plain symlink to
# the real tclsh8.6. Section 0 asserted the load-bearing files; section 13
# runs the generic bundle_deps/patch_rpath pass over this prefix.

###############################################################
# 12. haproxy -> /opt/percona-haproxy
###############################################################
# Stage from the percona-haproxy RPM, mirroring the official tarball's
# component layout: sbin/haproxy, bin/{halog,iprange}, etc/haproxy/,
# etc/logrotate.d/haproxy.logrotate, etc/sysconfig/haproxy/
# haproxy.sysconfig (a DIRECTORY holding the file — official quirk),
# share/ = errorfiles + README, share/man/man1/{haproxy.1,halog.1}
# uncompressed. Systemd unit files stay out (not a tarball concern).
mkdir -p $HAPROXY_PREFIX/sbin
cp /usr/sbin/haproxy $HAPROXY_PREFIX/sbin/
for b in halog iprange; do
    [ -f "/usr/bin/$b" ] && cp "/usr/bin/$b" $HAPROXY_PREFIX/bin/ || true
done
mkdir -p $HAPROXY_PREFIX/etc/haproxy $HAPROXY_PREFIX/etc/logrotate.d \
         $HAPROXY_PREFIX/etc/sysconfig/haproxy
cp -rp /etc/haproxy/. $HAPROXY_PREFIX/etc/haproxy/
[ -f /etc/logrotate.d/haproxy ] && \
    cp /etc/logrotate.d/haproxy $HAPROXY_PREFIX/etc/logrotate.d/haproxy.logrotate || true
[ -f /etc/sysconfig/haproxy ] && \
    cp /etc/sysconfig/haproxy $HAPROXY_PREFIX/etc/sysconfig/haproxy/haproxy.sysconfig || true
mkdir -p $HAPROXY_PREFIX/share/man/man1
[ -d /usr/share/haproxy ] && cp -rp /usr/share/haproxy/. $HAPROXY_PREFIX/share/ || true
# haproxy links BOTH libpcre2-8 and libpcre2-posix, and libpcre2-posix is
# NOT installed on default Debian/Ubuntu hosts — haproxy would fail to load
# (acceptance-verified on ubuntu:24.04). The official tarball bundles the
# pcre2 pair into percona-haproxy/lib. Since the 2026-07 QA round the pcre2
# sonames are off the host baseline, so section 13's copy_deps bundles them
# anyway; this explicit copy is kept because it brings the COMPLETE symlink
# family in one step and does not depend on ldd resolving them. cp -a runs
# before section 13, whose copy_deps uses cp -pn, so the two never fight.
cp -a /usr/lib64/libpcre2-8.so* /usr/lib64/libpcre2-posix.so* $HAPROXY_PREFIX/lib/
for m in /usr/share/man/man1/haproxy.1* /usr/share/man/man1/halog.1*; do
    [ -e "$m" ] || continue
    case "$m" in
        *.gz) gunzip -c "$m" > "$HAPROXY_PREFIX/share/man/man1/$(basename "${m%.gz}")" ;;
        *)    cp -p "$m" $HAPROXY_PREFIX/share/man/man1/ ;;
    esac
done

###############################################################
# 12a. Strip python bytecode (QA item 6)
###############################################################
# The RPM's `make install` byte-compiles the stdlib and the distro
# python3.12-* site-packages RPMs ship __pycache__ too (copied in section
# 8). The official tarball ships ZERO .pyc/__pycache__; strip them all —
# python regenerates bytecode at run time when it can write, and runs fine
# without it when it cannot. Must run after all python staging (sections
# 7/8); section 15 gates on the count staying zero.
find "$PYTHON_PREFIX" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$PYTHON_PREFIX" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

###############################################################
# 13. Bundle .so deps and patchelf RPATH for ELF prefixes
###############################################################
# copy_deps resolves deps with ldd, i.e. through the system loader, and
# /opt/percona-{gdal,proj}/lib are not in ld.so.cache — so
# postgis_raster-3.so's NEEDED libgdal.so.NN/libproj.so.NN would come back
# "not found" and never be bundled (before the 2026-07 QA round they
# resolved to EPEL's fat gdal-libs from /usr/lib64 instead). Run the
# bundling passes with those two directories on LD_LIBRARY_PATH. The
# variable is exported inside a SUBSHELL function body, so it applies to
# the bundling only and never leaks into patch_rpath, the ELF patcher, the
# gates or the smoke probes (the dlopen smoke in particular must resolve
# through RUNPATHs alone). Neither directory holds anything but
# libgdal/libproj, so no other dependency can be shadowed by it.
bundle_deps_lean() (
    export LD_LIBRARY_PATH="$GDAL_PREFIX/lib:$PROJ_PREFIX/lib"
    bundle_deps "$@"
)
for prefix in $PG_PREFIX /opt/percona-pgbouncer \
              /opt/percona-pgpool-II /opt/percona-pgbackrest \
              $TCL_PREFIX $HAPROXY_PREFIX; do
    bundle_deps_lean "$prefix"
    patch_rpath "$prefix"
done
# (tclsh8.6's compiled /opt/percona-tcl/lib RPATH becomes the equivalent
# $ORIGIN/../lib via patch_rpath above; haproxy's sbin/ is covered by the
# sbin-aware bundle_deps/patch_rpath, bundling e.g. liblua/libcrypt.)
# Python: also walk the whole lib/pythonX.Y tree (lib-dynload/ C extensions,
# site-packages extensions like psycopg2/_psycopg) so their NEEDED libs
# (libsqlite3, libncursesw, libuuid, libpq, ...) are bundled into
# $PYTHON_PREFIX/lib.
bundle_deps $PYTHON_PREFIX "$PYTHON_PREFIX/lib/python${PY_VER}"
patch_rpath $PYTHON_PREFIX
# RPATH the C extensions at the bundled lib dir: the interpreter's own
# RUNPATH does not apply to dlopened extensions' own deps — and the
# embedded case (plpython3 inside postgres) never even runs bin/python3.
find "$PYTHON_PREFIX/lib/python${PY_VER}" -type f -name '*.so*' | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    patchelf --set-rpath '/opt/percona-python3/lib:$ORIGIN' "$f"
done
# Perl: walk the lib tree so XS-module deps (libdb for DB_File, ...) are
# bundled, then point the XS modules at the bundled libs (absolute /opt
# path — depth under auto/ varies so $ORIGIN-relative paths won't work).
# bin/perl keeps its compiled CORE RPATH (section 10) and bundle_deps does
# not touch RPATHs, so the perl prefix deliberately skips patch_rpath.
bundle_deps $PERL_PREFIX "$PERL_PREFIX/lib"
find "$PERL_PREFIX/lib" -type f -name '*.so' -path '*/auto/*' | while read -r f; do
    patchelf --set-rpath '/opt/percona-perl/lib:$ORIGIN' "$f"
done
# Note: etcd (Go static), pgbadger (Perl script), patroni (Python) -- no bundling needed

# Bundle OpenSSL into percona-python3 explicitly.
# _ssl/_hashlib.cpython-*.so are compiled against the buildroot's OpenSSL
# (3.5.x on current EL9), which may reference newer symbol-version nodes
# than the variant's host promise; the python tree resolves OpenSSL from
# its own lib/ (extension RPATHs above) and is excluded from the section-15
# host-ABI audit for exactly this reason. (EL8's OpenSSL is 1.1 — the .so.3
# glob finds nothing there and the extensions use the host 1.1 libs, same
# as every previous ssl1.1 artifact.)
for f in /usr/lib64/libssl.so.3* /usr/lib64/libcrypto.so.3*; do
    [ -f "$f" ] && cp -pn "$f" $PYTHON_PREFIX/lib/ 2>/dev/null || true
done

###############################################################
# 13a. GDAL/PROJ: reduce the two components to DATA ONLY
###############################################################
# percona-gdal/percona-proj are already installed AT their final tarball
# location (/opt/percona-{gdal,proj}) — nothing to stage, unlike every other
# component. What the ARTIFACT needs from them is only their resource
# directories: libgdal/libproj have those paths (/opt/percona-gdal/share/gdal,
# /opt/percona-proj/share/proj) compiled in, which is the whole zero-env-var
# mechanism, and it is why these are top-level components of their own rather
# than being folded into percona-postgresql${PG_MAJOR}.
#
# The LIBRARIES are not shipped here: the working copies are the ones
# bundle_deps_lean just put into $PG_PREFIX/lib, where postgis_raster's
# $ORIGIN RUNPATH finds libgdal and libgdal's own $ORIGIN rpath entry (added
# by percona-gdal's spec) finds libproj right next to it. Keeping the
# originals too would ship a second, DEAD copy of both libraries: unloadable
# (their libspatialite/libgeos/... deps live only in $PG_PREFIX/lib), several
# MB, and extra surface for the OpenSSL host-ABI audit. So lib/ goes as well,
# together with the development tree (include/, bin/ CLI tools, man pages,
# pkgconfig/cmake).
#
# ORDERING IS LOAD-BEARING: this runs AFTER section 13, because
# bundle_deps_lean resolves libgdal/libproj THROUGH these very lib/ dirs
# (LD_LIBRARY_PATH). Moving it earlier would silently leave both libraries
# unbundled. $GDAL_LIB/$PROJ_LIB are only used for their basenames from here
# on (the section-15 dlopen gate), so the paths going away is fine.
for d in $GDAL_PREFIX $PROJ_PREFIX; do
    [ -d "$d" ] || { echo "FATAL: $d missing" >&2; exit 1; }
    # ${d:?} — a defensive brake on an rm -rf built from a variable.
    rm -rf "${d:?}/lib" "${d:?}/include" "${d:?}/bin"
    # Keep only the compiled-in resource dirs under share/ (drops man/,
    # doc/, bash-completion/, ...).
    find "$d/share" -mindepth 1 -maxdepth 1 \
         ! -name gdal ! -name proj -exec rm -rf {} +
done
# What must remain, and what must NOT.
[ -f "$GDAL_PREFIX/share/gdal/gdalicon.png" ] || { echo "FATAL: $GDAL_PREFIX/share/gdal emptied by the prune" >&2; exit 1; }
[ -f "$PROJ_PREFIX/share/proj/proj.db" ] || { echo "FATAL: $PROJ_PREFIX/share/proj/proj.db emptied by the prune" >&2; exit 1; }
for d in $GDAL_PREFIX $PROJ_PREFIX; do
    [ -e "$d/lib" ] && { echo "FATAL: $d/lib still present — these components are data-only" >&2; exit 1; } || true
done

###############################################################
# 14. PL extension RPATHs -> the /opt language runtimes
###############################################################
# THE zero-env-var mechanism for the PLs (QA items 3-5): each PL .so
# carries a RUNPATH pointing at its /opt runtime tree, so its interpreter
# library (with /opt paths compiled in — section 0) resolves no matter how
# the server was started. The postgres binary itself needs only the plain
# $ORIGIN/../lib set by section 13's patch_rpath — the loader resolves a
# dlopened PL's NEEDED libs through the PL's OWN RUNPATH, not through the
# executable's. All mandatory: fail loudly if a PL .so is missing or
# patchelf cannot rewrite it.
for ext in plperl plpython3 pltcl; do
    [ -f "$PG_PREFIX/lib/$ext.so" ] || { echo "FATAL: $PG_PREFIX/lib/$ext.so missing" >&2; exit 1; }
done
patchelf --set-rpath "/opt/percona-perl/lib/${PERL_VER}/CORE:\$ORIGIN" "$PG_PREFIX/lib/plperl.so"
patchelf --set-rpath '/opt/percona-python3/lib:$ORIGIN' "$PG_PREFIX/lib/plpython3.so"
patchelf --set-rpath '/opt/percona-tcl/lib:$ORIGIN' "$PG_PREFIX/lib/pltcl.so"

# All other PostgreSQL lib/ .so files get $ORIGIN
find $PG_PREFIX/lib -name '*.so*' -type f | while read f; do
    case "$(basename "$f")" in
        plperl.so|plpython3.so|pltcl.so) continue ;;
    esac
    patchelf --set-rpath '$ORIGIN' "$f" 2>/dev/null || true
done

###############################################################
# 14a. Compiled socket-dir default: /run/postgresql -> /tmp
###############################################################
# The RPM build compiles the /run/postgresql socket dir into the binaries
# as TWO distinct NUL-terminated C string constants:
#
#  * "/run/postgresql"        — DEFAULT_PGSOCKET_DIR: libpq's client-side
#    connection default (psql, pgbench, pg_dump, pg_isready, ...) and the
#    value initdb writes into the generated postgresql.conf.
#  * "/run/postgresql, /tmp"  — the server's unix_socket_directories GUC
#    boot value (Red Hat patches postgres to LISTEN on both directories);
#    with the conf line left at its commented default, startup would try
#    to create a socket in /run/postgresql and FATAL on hosts where a
#    non-root user cannot create it.
#  * "/var/run/postgresql[, /tmp]" — older spellings of the same two
#    defaults (some builds/components use the pre-/run path); mapped to
#    /tmp likewise.
#
# The official from-source tarball compiles the stock /tmp for both.
# Rewrite each constant in place in every bundled ELF: the old bytes
# (string + NUL) become "/tmp\0" NUL-padded to the SAME length. C string
# readers stop at the first NUL, so the padding is invisible, and the
# identical length means no ELF offsets, section sizes or relocations
# change — a safe in-place edit. Result: the server listens on /tmp,
# initdb writes '/tmp' into the generated postgresql.conf (both -D and
# positional-DATADIR forms), and every client connects to /tmp by default
# — ZERO wrappers or environment variables, byte-level behavioral parity
# with the official tarball's compiled defaults. Must run AFTER all
# staging and RPATH work so no later step re-introduces an unpatched copy
# (the section-15 gate asserts exactly that).
"$PY_BIN" - <<'PYEOF'
import os

# LONGEST-FIRST is load-bearing: bytes.replace matches mid-string, so a
# shorter pattern can TAIL-MATCH inside a longer spelling and mangle it —
# e.g. "/run/postgresql\0" applied to an ELF embedding the older
# "/var/run/postgresql\0" spelling would consume its tail and leave
# "/var/tmp" (wrong semantics), with no "/run/postgresql" bytes left for
# the section-15 residual gate to catch. Listing the /var forms first
# consumes them intentionally (they too must become plain "/tmp") before
# the shorter patterns get a chance to tail-match.
REPLACEMENTS = []
for old in (
    b"/var/run/postgresql, /tmp\0",
    b"/run/postgresql, /tmp\0",
    b"/var/run/postgresql\0",
    b"/run/postgresql\0",
):
    new = b"/tmp\0".ljust(len(old), b"\0")
    assert len(old) == len(new)
    REPLACEMENTS.append((old, new))
# Guard the longest-first invariant against future edits.
assert [len(o) for o, _ in REPLACEMENTS] == sorted(
    (len(o) for o, _ in REPLACEMENTS), reverse=True
)
patched = 0
for dirpath, _dirs, files in os.walk("/opt"):
    for name in files:
        p = os.path.join(dirpath, name)
        # Regular files only: symlinks are reached via their target.
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        with open(p, "rb") as f:
            if f.read(4) != b"\x7fELF":
                continue
            data = b"\x7fELF" + f.read()
        new_data = data
        for old, new in REPLACEMENTS:
            new_data = new_data.replace(old, new)
        if new_data == data:
            continue
        with open(p, "wb") as f:
            f.write(new_data)
        patched += 1
        print("  socket-dir patched: %s" % p)
# At minimum postgres, initdb and the bundled libpq copies must match; zero
# hits means the RPMs no longer compile /run/postgresql in and this section
# (plus its gate) needs a human look — fail loudly rather than drift.
if patched == 0:
    raise SystemExit("FATAL: no ELF contained /run/postgresql — patch is a no-op")
print("socket-dir patch: %d ELF files patched" % patched)
PYEOF

###############################################################
# 15. Verification gate — fail the build on any breakage
###############################################################
# readelf is required by the OpenSSL host-ABI audit below. Assert it exists:
# if it were silently missing, the audit would see empty input and pass
# vacuously — the exact failure mode this gate exists to prevent.
command -v readelf >/dev/null || { echo "FATAL: readelf missing — SSL-ABI audit impossible" >&2; exit 1; }

# The SSL variant labels follow the official tarball naming and map 1:1 to
# the EL base of each repository: EL8=ssl1.1, EL9=ssl3. Fail loudly on
# anything unmapped, e.g. a future EL10/EL11.
# The variant is derived here, before the gate, because the OpenSSL
# host-ABI audit below picks its allowed-symbol policy from it; section 16
# reuses it for the artifact name.
EL_MAJOR=$( (. /etc/os-release 2>/dev/null && echo "${PLATFORM_ID#platform:el}") || true)
if [ -z "$EL_MAJOR" ]; then
    # Buildroots without a release package (no /etc/os-release): fall back
    # to glibc's %dist tag (glibc is present in every buildroot).
    EL_MAJOR=$(rpm -q --qf '%{release}' glibc | sed -n 's/.*\.el\([0-9][0-9]*\).*/\1/p')
fi
case "$EL_MAJOR" in
    8)  SSL_VARIANT=ssl1.1 ;;
    9)  SSL_VARIANT=ssl3 ;;
    *)  echo "FATAL: unmapped EL major version '$EL_MAJOR'" >&2; exit 1 ;;
esac

echo "=== Verification: NEEDED-soname audit ==="
# ldd would resolve against the fully-populated buildroot (ld.so.cache), hiding
# libraries we failed to bundle. Instead audit DT_NEEDED sonames directly: each
# must either be host-provided by design (is_system_lib) or bundled under /opt.
# Precompute the bundled-soname list once; a per-soname 'find /opt' rescan
# is O(tree size) for every NEEDED entry. -xtype f = regular files plus
# symlinks that resolve to one, so dangling symlinks never count as bundled.
find /opt -name '*.so*' -xtype f -printf '%f\n' | sort -u \
    > /tmp/bundled-sonames.txt
find /opt -type f \( -perm -u+x -o -name '*.so*' \) | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    patchelf --print-needed "$f" 2>/dev/null | while read -r soname; do
        if is_system_lib "$soname"; then
            continue
        fi
        if ! grep -qxF "$soname" /tmp/bundled-sonames.txt; then
            echo "UNRESOLVED: $f needs $soname (not bundled, not in system exclude list)"
        fi
    done
done > /tmp/needed-audit.txt
if [ -s /tmp/needed-audit.txt ]; then
    cat /tmp/needed-audit.txt
    echo "FATAL: unresolved libraries found" >&2
    exit 1
fi

echo "=== Verification: surplus dependency-chain audit ==="
# The EPEL gdal-libs/proj chain (replaced by percona-gdal/percona-proj) is
# what made this gate necessary: it dragged ~70 shared objects into the
# artifact, among them libflexiblas, whose ELF CONSTRUCTOR abort()s when its
# dlopen'ed BLAS backend plugin is absent — i.e. on every host that is not
# the buildroot. None of the libraries below has any business in a
# PostgreSQL tarball; their presence means a fat dependency chain crept back
# in (a new BuildRequires, a lost prjconf Prefer:, a re-optioned percona-gdal).
# Checked two ways: no bundled file may BE one of them, and no bundled ELF
# may NEED one of them (which would also fail the NEEDED audit above, but
# with a much less specific message).
# (libdf/libmfhdf are hdf4's two libraries — they do NOT start with
# "libhdf", which is hdf5's prefix, so both are named explicitly. libdf.so.0
# is the very library the ssl3 `Prefer: hdf-libs` line existed for.)
SURPLUS_LIBS="libflexiblas libarmadillo libhdf libdf libmfhdf libnetcdf libdap
libpoppler libmariadb libodbc libkml libxerces libarpack libsuperlu"
: > /tmp/surplus-audit.txt
for bad in $SURPLUS_LIBS; do
    find /opt -name "${bad}*" -printf 'SURPLUS-FILE: %p\n' >> /tmp/surplus-audit.txt
done
find /opt -type f \( -perm -u+x -o -name '*.so*' \) | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    patchelf --print-needed "$f" 2>/dev/null | while read -r soname; do
        for bad in $SURPLUS_LIBS; do
            case "$soname" in
                ${bad}*) echo "SURPLUS-NEEDED: $f needs $soname" ;;
            esac
        done
    done
done >> /tmp/surplus-audit.txt
if [ -s /tmp/surplus-audit.txt ]; then
    cat /tmp/surplus-audit.txt
    echo "FATAL: surplus dependency chain present in the artifact" >&2
    exit 1
fi

echo "=== Verification: host-baseline gate ==="
# Two-part self-consistency check on the universal host baseline (see the
# CONTRACT at the top of this script). QA finding 1 was exactly this: three
# libraries the artifact needed (libtirpc, libexpat, libpcre2-posix) were on
# the exclude list although minimal hosts do not ship them, so nothing
# bundled them and nothing complained.
#  1. No formerly-excluded soname may be matched by is_system_lib again —
#     catches a token being pasted back into SYSTEM_LIBS_EXCLUDE, or a new
#     token whose glob prefix happens to cover one of them.
#  2. Any ELF NEEDING one of them must find it WHERE THAT ELF CAN ACTUALLY
#     LOAD IT FROM, which is per component, not artifact-wide: every RUNPATH
#     this script sets is either the ELF's own component lib/ dir
#     ($ORIGIN/../lib, /opt/percona-<comp>/lib) or the ELF's own directory
#     ($ORIGIN — e.g. libperl.so in perl's CORE/). A libexpat.so.1 sitting in
#     percona-python3/lib does NOT satisfy a NEED from
#     percona-haproxy/sbin/haproxy, and accepting it would reproduce QA
#     finding 1 one component over. The generic NEEDED audit above is the
#     artifact-wide check; this one is deliberately stricter.
: > /tmp/baseline-audit.txt
for tok in $FORMERLY_EXCLUDED_LIBS; do
    if is_system_lib "$tok"; then
        echo "BASELINE: $tok is back on the host baseline — it is NOT present on every minimal host" >> /tmp/baseline-audit.txt
    fi
done
find /opt -type f \( -perm -u+x -o -name '*.so*' \) | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    # /opt/<component>/... -> the two directories the loader can reach
    # through the RUNPATHs this script sets.
    comp_lib=$(echo "$f" | awk -F/ 'NF >= 3 { print "/opt/" $3 "/lib" }')
    own_dir=$(dirname "$f")
    patchelf --print-needed "$f" 2>/dev/null | while read -r soname; do
        for tok in $FORMERLY_EXCLUDED_LIBS; do
            case "$soname" in
                ${tok}*)
                    # -e is false for a dangling symlink, so a broken
                    # symlink family cannot pass as bundled.
                    [ -e "$comp_lib/$soname" ] || [ -e "$own_dir/$soname" ] || \
                        echo "BASELINE: $f needs $soname, which is neither in $comp_lib nor next to it, nor host-universal"
                    ;;
            esac
        done
    done
done >> /tmp/baseline-audit.txt
if [ -s /tmp/baseline-audit.txt ]; then
    cat /tmp/baseline-audit.txt
    echo "FATAL: host-baseline contract violated" >&2
    exit 1
fi

echo "=== Verification: psql link audit ==="
# bin/psql must be the percona-psql (libedit) build, never the server RPM's
# readline one: the readline soname split (EL8 .so.7 vs modern .so.8) and
# readline's absence from minimal hosts is what the deleted psql wrapper
# used to paper over.
readelf -d "$PG_PREFIX/bin/psql" | grep NEEDED || true
if readelf -d "$PG_PREFIX/bin/psql" | grep -q 'libreadline'; then
    echo "FATAL: $PG_PREFIX/bin/psql links libreadline — percona-psql was not staged over the RPM psql" >&2
    exit 1
fi
readelf -d "$PG_PREFIX/bin/psql" | grep -q 'NEEDED.*libedit\.so\.0' || {
    echo "FATAL: $PG_PREFIX/bin/psql does not need libedit.so.0" >&2
    exit 1
}
[ -e "$PG_PREFIX/bin/psql.bin" ] && { echo "FATAL: psql.bin present — the readline wrapper machinery is supposed to be gone" >&2; exit 1; } || true

echo "=== Verification: OpenSSL host-ABI audit ($SSL_VARIANT) ==="
# libssl/libcrypto are deliberately NOT bundled (they are on the system
# exclude list above), so every bundled binary resolves them from the HOST
# at run time. The ssl variant label is therefore a host-compatibility
# promise: ssl1.1 must run on hosts with OpenSSL 1.1, ssl3 on hosts with
# any OpenSSL 3.0+. What enforces that promise at the ELF level is the
# set of versioned symbol references (version
# NEEDS, e.g. OPENSSL_3.0.0) each binary carries against libssl/libcrypto:
# the host's loader refuses to start a binary that needs a version node
# the host libraries do not define. The buildroot may ship a NEWER OpenSSL
# than the promise (the EL9 buildroot has 3.5.x), so a staging rebuild
# could silently start referencing newer nodes — this audit turns the
# variant label into a tested guarantee.
#
# Per-variant allowed version-node pattern (anchored full-line grep):
case "$SSL_VARIANT" in
    # Upstream OpenSSL 1.1 defines exactly two version nodes: OPENSSL_1_1_0
    # and OPENSSL_1_1_1. Allow ONLY those — Red Hat's 1.1.1 fork adds
    # private nodes (e.g. OPENSSL_1_1_1b, referenced by EL8's krb5/libssh),
    # which do not exist on stock-OpenSSL hosts (Debian 11 class), so any
    # RH-fork leakage into bundled binaries must fail here at build time.
    ssl1.1) OPENSSL_ALLOWED='OPENSSL_1_1_[01]' ;;
    # Must run on any OpenSSL 3.0 host: only 3.0.x nodes are acceptable.
    # Achievable on the EL9 base (Rocky 9.8+ ships OpenSSL 3.5) because
    # staging percona-postgresql patches pgcrypto to avoid the
    # EVP_MD_CTX_get_size_ex() 3.4 API — without that patch pgcrypto.so
    # would reference OPENSSL_3.4.0 and fail this gate.
    ssl3)   OPENSSL_ALLOWED='OPENSSL_3\.0\.[0-9]*' ;;
    *)      echo "FATAL: no SSL-ABI policy for $SSL_VARIANT" >&2; exit 1 ;;
esac
# Scan every ELF under /opt EXCEPT the percona-python3 tree: the python
# component bundles its own OpenSSL copy (libssl/libcrypto in its lib/,
# used by lib-dynload extensions like _ssl/_hashlib and by site-packages
# extensions (psycopg2's _psycopg) whose OpenSSL needs resolve to the
# bundled copy), and its loaders are pointed at those bundled libs via
# RPATH/LD_LIBRARY_PATH — so the python tree's OpenSSL symbol needs are
# satisfied internally and are NOT part of the host promise.
find /opt -path /opt/percona-python3 -prune -o \
        -type f \( -perm -u+x -o -name '*.so*' \) -print | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    # Parse the version NEEDS only — never version definitions. readelf -V
    # prints up to three blocks (Version symbols / Version definition /
    # Version needs); grepping the whole output would also match version
    # DEFINITIONS (e.g. the bundled libs' own OPENSSL_* defs) and needs
    # against non-OpenSSL libs (GLIBC_*). The awk below activates only
    # inside the "Version needs section" block, tracks the current
    # "File: <soname>" attribution line, and emits "<soname> <node>" pairs
    # only for the host-provided OpenSSL sonames (libssl.so.*/libcrypto.so.*).
    readelf -V "$f" 2>/dev/null | awk '
        /^Version needs section/ { inneeds = 1; next }
        /^Version (symbols|definition) section/ { inneeds = 0 }
        !inneeds { next }
        /File:/ { for (i = 1; i <= NF; i++) if ($i == "File:") fname = $(i + 1) }
        /Name:/ && fname ~ /^lib(ssl|crypto)\.so/ {
            for (i = 1; i <= NF; i++) if ($i == "Name:") print fname, $(i + 1)
        }
    ' | while read -r soname node; do
        # Anchored match: the node must be entirely covered by the allowed
        # pattern, otherwise it exceeds what the variant's hosts provide.
        if ! echo "$node" | grep -qx "$OPENSSL_ALLOWED"; then
            echo "SSL-ABI: $f references $node via $soname (exceeds $SSL_VARIANT promise)"
        fi
    done
done > /tmp/ssl-abi-audit.txt
if [ -s /tmp/ssl-abi-audit.txt ]; then
    cat /tmp/ssl-abi-audit.txt
    echo "FATAL: OpenSSL symbol-version needs exceed the $SSL_VARIANT promise" >&2
    exit 1
fi

echo "=== Verification: compiled socket-dir audit ==="
# Section 14a rewrote the compiled DEFAULT_PGSOCKET_DIR in every bundled
# ELF. Assert NO ELF under /opt still carries the plain byte string
# /run/postgresql: this both proves the patch actually ran and catches any
# future binary (new component, re-staged copy) that sneaks the RPM default
# back in. Text files are out of scope — only compiled-in defaults have
# runtime effect.
if ! "$PY_BIN" - <<'PYEOF'
import os, sys

BAD = b"/run/postgresql"
bad = 0
for dirpath, _dirs, files in os.walk("/opt"):
    for name in files:
        p = os.path.join(dirpath, name)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        with open(p, "rb") as f:
            if f.read(4) != b"\x7fELF":
                continue
            data = b"\x7fELF" + f.read()
        if BAD in data:
            bad += 1
            print("SOCKET-DIR: %s still contains /run/postgresql" % p)
sys.exit(1 if bad else 0)
PYEOF
then
    echo "FATAL: bundled ELF files still reference /run/postgresql (section 14a patch incomplete)" >&2
    exit 1
fi

echo "=== Verification: component inventory ==="
# The artifact must contain exactly these THIRTEEN top-level components
# (QA item 8 added percona-haproxy; the 2026-07 QA round added percona-gdal
# and percona-proj, whose resource paths are compiled as
# /opt/percona-{gdal,proj}/share/... and therefore have to be components of
# their own). A missing dir means a staging section silently did nothing; an
# extra dir means something leaked into /opt.
cat > /tmp/expected-components.txt << EOF
percona-etcd
percona-gdal
percona-haproxy
percona-patroni
percona-perl
percona-pgbackrest
percona-pgbadger
percona-pgbouncer
percona-pgpool-II
percona-postgresql${PG_MAJOR}
percona-proj
percona-python3
percona-tcl
EOF
ls /opt | LC_ALL=C sort > /tmp/actual-components.txt
if ! diff -u /tmp/expected-components.txt /tmp/actual-components.txt; then
    echo "FATAL: /opt component set does not match the expected 13 components" >&2
    exit 1
fi

echo "=== Verification: smoke commands ==="
# The interpreter probes run under env -i: the whole point of the /opt
# runtimes is that they need ZERO environment variables (QA items 3-5) —
# a probe that only passes with inherited env would be lying. python runs
# with -B: this build stage is root, so a bare import would re-litter the
# tree with the very __pycache__ dirs section 12a stripped (the bytecode
# audit below runs AFTER these probes to catch exactly that).
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/initdb" --version
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/postgres" --version
env -i "$PYTHON_PREFIX/bin/python3" -B -c 'import ssl, yaml; print("python OK")'
env -i "$PYTHON_PREFIX/bin/python3" -B -c 'import patroni; print("patroni import OK")'
env -i "$PERL_PREFIX/bin/perl" -e 'use strict; print "perl OK\n"'
echo 'puts "tcl OK"' | env -i "$TCL_PREFIX/bin/tclsh${TCL_VER}"
env -u LD_LIBRARY_PATH "$HAPROXY_PREFIX/sbin/haproxy" -v
# psql runs under a fully EMPTY environment: it must find libedit and libpq
# through its own RUNPATH ($ORIGIN/../lib) with no readline anywhere.
env -i "$PG_PREFIX/bin/psql" --version

echo "=== Verification: extension dlopen smoke ==="
# THE gate for QA finding 1. Every PostgreSQL extension/plugin module in
# lib/ is dlopen()ed exactly the way the backend does it, from an EMPTY
# environment so that only the module's own RUNPATH chain is used. That
# exercises three things at once: the NEEDED closure really is complete and
# reachable, every dependency's own NEEDED closure resolves too (RUNPATH is
# not inherited, so this catches a bundled lib the loader cannot satisfy),
# and every ELF CONSTRUCTOR in the chain runs — which is how the FlexiBLAS
# abort() that EPEL's gdal chain introduced would have failed the build
# instead of the user's server.
#
# RTLD_LAZY, not RTLD_NOW: extension modules reference postgres backend
# symbols that only exist inside the running server, so lazy binding is what
# makes the probe possible at all. Function symbols stay unbound while the
# library chain loads; data-symbol relocations are still resolved eagerly, so
# some modules legitimately fail with "undefined symbol: <backend symbol>".
# That is a PASS only when the symbol really is a POSTGRES-INTERNAL one: the
# probe looks the name up in the backend's own dynamic symbol table
# (postgres is linked --export-dynamic precisely so extensions resolve
# against it). An undefined symbol that postgres does NOT define means a
# bundled dependency has the wrong ABI — e.g. "undefined symbol: GEOSDensify"
# from a libgeos_c older than the PostGIS that was built against it — and
# that is FATAL, as is anything else: a missing library, a failing
# constructor, an abort.
#
# NOTE the mode constant: RTLD_LAZY lives in `os`, NOT in `ctypes` (which
# exports only RTLD_GLOBAL/RTLD_LOCAL) — ctypes.RTLD_LAZY is an
# AttributeError that would fail every single probe.
#
# Runs LAST of the functional gates, after section 14a's ELF string patch and
# all RUNPATH work, so what is probed is the exact final state of the files.
# Must run AFTER section 13/13a for the same reason.
#
# The backend symbol table, computed once. If nm is unavailable the file
# stays empty and the probe says so instead of silently accepting every
# undefined symbol (binutils is a BuildRequires, so this is a guard, not a
# supported mode).
: > /tmp/postgres-symbols.txt
if command -v nm >/dev/null 2>&1; then
    # sub(/@.*/): nm prints versioned symbols as name@@VERS. The backend has
    # no version script, so this is belt-and-braces — but a versioned entry
    # would never match the loader's plain symbol name.
    nm -D --defined-only "$PG_PREFIX/bin/postgres" 2>/dev/null \
        | awk '{ n = $NF; sub(/@.*/, "", n); if (n != "") print n }' \
        | sort -u > /tmp/postgres-symbols.txt
fi
[ -s /tmp/postgres-symbols.txt ] || \
    echo "  WARNING: no postgres symbol table — undefined-symbol classification degraded"
dlopen_probe() {
    local so="$1" out rc sym
    out=$(env -i "$PY_BIN" -B -c \
        'import ctypes, os, sys; ctypes.CDLL(sys.argv[1], mode=os.RTLD_LAZY)' \
        "$so" 2>&1) && rc=0 || rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "  dlopen OK: $so"
        return 0
    fi
    if echo "$out" | grep -q 'undefined symbol'; then
        # "<path>: undefined symbol: <name>" — the loader reports the first
        # unresolved symbol only, which is all we need to classify.
        sym=$(echo "$out" | sed -n 's/.*undefined symbol: *\([A-Za-z0-9_.]*\).*/\1/p' | head -1)
        if [ -n "$sym" ] && grep -qxF "$sym" /tmp/postgres-symbols.txt; then
            echo "  dlopen OK (unresolved postgres backend symbol '$sym', expected): $so"
            return 0
        fi
        if [ ! -s /tmp/postgres-symbols.txt ]; then
            echo "  dlopen OK (unresolved symbol '$sym', UNVERIFIED — no postgres symbol table): $so"
            return 0
        fi
        echo "DLOPEN-FAIL ($rc): $so — undefined symbol '$sym' is NOT a postgres backend symbol (bundled-dependency ABI mismatch?)"
        echo "$out" | sed 's/^/    /'
        return 1
    fi
    echo "DLOPEN-FAIL ($rc): $so"
    echo "$out" | sed 's/^/    /'
    return 1
}
# Modules are identified by the PG_MODULE_MAGIC block's Pg_magic_func
# symbol. binutils (nm) is a BuildRequires; the fallback probes every .so
# directly in lib/ instead, which is a superset (libpq and the bundled
# dependencies are dlopen-clean anyway) and never silently probes nothing.
command -v nm >/dev/null 2>&1 || echo "  NOTE: nm unavailable — probing every lib/*.so"
DLOPEN_TESTED=""
DLOPEN_COUNT=0
DLOPEN_FAILED=0
for so in "$PG_PREFIX"/lib/*.so; do
    [ -f "$so" ] || continue
    if command -v nm >/dev/null 2>&1; then
        nm -D --defined-only "$so" 2>/dev/null | grep -q 'Pg_magic_func' || continue
    fi
    DLOPEN_COUNT=$((DLOPEN_COUNT + 1))
    DLOPEN_TESTED="$DLOPEN_TESTED $(basename "$so")"
    dlopen_probe "$so" || DLOPEN_FAILED=$((DLOPEN_FAILED + 1))
done
echo "dlopen smoke: $DLOPEN_COUNT extension modules probed, $DLOPEN_FAILED failed"
if [ "$DLOPEN_FAILED" -ne 0 ]; then
    echo "FATAL: $DLOPEN_FAILED extension module(s) could not be dlopen'ed" >&2
    exit 1
fi
# A vacuous pass is the failure mode this gate must not have: postgis_raster
# is the module the whole GDAL/PROJ work exists for, so require it by name
# (glob-tolerant: the suffix tracks the PostGIS major version).
case "$DLOPEN_TESTED" in
    *postgis_raster*) ;;
    *) echo "FATAL: postgis_raster was not among the dlopen-probed modules ($DLOPEN_TESTED)" >&2; exit 1 ;;
esac
# 20-odd modules ship in lib/ (contrib + the Percona extensions + the 3
# PLs); a handful would mean nm found almost nothing.
if [ "$DLOPEN_COUNT" -lt 10 ]; then
    echo "FATAL: only $DLOPEN_COUNT modules probed — module detection is broken" >&2
    exit 1
fi

# Constructor-coverage caveat, and why the two probes below are not
# redundant: the loader resolves eager (data) relocations BEFORE running any
# constructor, so for a module that legitimately reports "undefined symbol"
# against a backend data symbol (CurrentMemoryContext & co.) the chain is
# mapped and its libraries relocated, but the constructors do not run. The
# bundled libgdal/libproj have no unresolved symbols, so probing them
# directly does run every constructor in the GDAL dependency chain — the
# FlexiBLAS abort() case — and at the same time asserts that section 13
# really bundled both libraries into the PostgreSQL component. Those copies
# are the ONLY ones in the artifact (section 13a keeps percona-gdal/
# percona-proj data-only), and postgis_raster's $ORIGIN RUNPATH plus
# libgdal's own $ORIGIN rpath entry is what makes them load with no
# environment at all.
for lib in "$(basename "$GDAL_LIB")" "$(basename "$PROJ_LIB")"; do
    bundled="$PG_PREFIX/lib/$lib"
    [ -e "$bundled" ] || {
        echo "FATAL: $bundled missing — copy_deps did not bundle it (LD_LIBRARY_PATH bundling pass broken?)" >&2
        exit 1
    }
    dlopen_probe "$bundled" || {
        echo "FATAL: $bundled cannot be dlopen'ed from an empty environment" >&2
        exit 1
    }
done

echo "=== Verification: python bytecode audit ==="
# Section 12a stripped all bytecode; the official tarball ships none
# (QA item 6). Sweep ALL of /opt so a future component cannot sneak any
# in. Deliberately the LAST gate before the artifact is created: anything
# that imports python modules during the build (e.g. the smoke probes
# above, when run without -B) regenerates __pycache__ as root.
find /opt \( -name '*.pyc' -o -name '*.pyo' -o \( -type d -name '__pycache__' \) \) > /tmp/pyc-audit.txt
if [ -s /tmp/pyc-audit.txt ]; then
    cat /tmp/pyc-audit.txt
    echo "FATAL: python bytecode found in the artifact (section 12a strip incomplete)" >&2
    exit 1
fi

###############################################################
# 16. Create the final artifact with the official tarball name
###############################################################
# The simpleimage recipe names its own output from raw (unexpanded)
# Name:/Version: tags, which cannot vary per repository. Instead we
# write the artifact directly into /usr/src/packages/OTHER (collected
# by OBS as a build result) and skip /.simpleimage.tar.gz entirely.
PG_FULL_VERSION=$(rpm -q --qf '%{version}' "percona-postgresql${PG_MAJOR}-server")
# SSL_VARIANT was derived at the top of section 15 (EL-major mapping),
# where the OpenSSL host-ABI audit also depends on it.
TARBALL="percona-postgresql-${PG_FULL_VERSION}-${SSL_VARIANT}-linux-$(uname -m).tar.gz"
mkdir -p /usr/src/packages/OTHER
cd /opt
tar -czf "/usr/src/packages/OTHER/${TARBALL}" -- *
echo "Created ${TARBALL}"
