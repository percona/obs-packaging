#!/bin/bash
# Builds the Percona PostgreSQL binary tarball from deb-installed content.
# Debian/Ubuntu counterpart of build-tarball.sh (the RPM-base builder) —
# same section structure, same helpers, same verification gate; only the
# source paths and package-manager queries differ. Runs chrooted as root
# inside an OBS simpleimage buildroot; writes the final artifact (with its
# official self-derived name) directly into /usr/src/packages/OTHER, where
# OBS collects build results. The recipe's own /.simpleimage.tar.gz
# handling is skipped (#!NoTarBall, and no such file is created).
set -e

PG_MAJOR=$(basename "$(ls -d /usr/lib/postgresql/*)")
[ -n "$PG_MAJOR" ] || { echo "FATAL: no /usr/lib/postgresql/* tree found" >&2; exit 1; }

# Debian multiarch library directory (x86_64 -> x86_64-linux-gnu).
MULTIARCH="$(uname -m)-linux-gnu"
LIBDIR=/usr/lib/${MULTIARCH}

# Debian bases ship a single python3 stack (3.10 on Ubuntu 22.04) — no
# parallel python3.12 like the EL8/EL9 RPM bases.
PY_BIN=$(command -v python3)
PY_VER=$("$PY_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')

# Interpreter versions discovered up front (used in wrappers below).
PERL_VER=$(perl -e 'printf "%vd", $^V')
TCL_VER=$(echo 'puts $tcl_version' | tclsh)

PG_PREFIX=/opt/percona-postgresql${PG_MAJOR}
PYTHON_PREFIX=/opt/percona-python3
PERL_PREFIX=/opt/percona-perl
TCL_PREFIX=/opt/percona-tcl

###############################################################
# System library exclusion list — these are always on the target
# system and must NOT be bundled (matches pg_tarballs_builder.sh).
# Sonames are identical across RPM and deb distros, so this is the
# same list as build-tarball.sh.
###############################################################
SYSTEM_LIBS_EXCLUDE="
libc.so
libm.so
libpthread.so
libdl.so
librt.so
libresolv.so
libnss_
libnsl.so
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
libeconf.so
libgcrypt.so
libgpg-error.so
libssl.so
libcrypto.so
libpcre2-8.so
libpcre2-posix.so
libtinfo.so
libreadline.so
libidn2.so
libunistring.so
libnghttp2.so
libexpat.so
libtirpc.so
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
        # (e.g. libldap.so.2 -> libldap_r.so.2.0.200); copy it explicitly
        # so the recreated symlinks never dangle.
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
# ELF .so files (e.g. python lib-dynload/ + dist-packages C extensions),
# so their NEEDED libs are bundled too.
bundle_deps() {
    local prefix="$1"
    shift
    local libdir="$prefix/lib"
    mkdir -p "$libdir"
    for pass in 1 2 3; do
        {
            find "$prefix/bin" "$libdir" -maxdepth 1 -type f 2>/dev/null
            [ $# -gt 0 ] && find "$@" -type f -name '*.so*' 2>/dev/null
        } | while read f; do
            file "$f" 2>/dev/null | grep -q ELF && copy_deps "$f" "$libdir" || true
        done
    done
}

# patchelf all ELF files in bin/ and lib/ to given RPATH
patch_rpath() {
    local prefix="$1"
    local rpath="${2:-\$ORIGIN/../lib}"
    find "$prefix/bin" "$prefix/lib" -maxdepth 1 -type f 2>/dev/null | while read f; do
        file "$f" 2>/dev/null | grep -q ELF && \
            patchelf --set-rpath "$rpath" "$f" 2>/dev/null || true
    done
}

###############################################################
# 1. Create isolated prefix directories
###############################################################
for tool in percona-postgresql${PG_MAJOR} percona-pgbouncer percona-pgpool-II \
            percona-pgbackrest percona-pgbadger percona-patroni \
            percona-python3 percona-perl percona-tcl percona-etcd; do
    mkdir -p /opt/${tool}/{bin,lib}
done

###############################################################
# 2. PostgreSQL: /usr/lib/postgresql/NN -> /opt/percona-postgresqlNN
###############################################################
# Debian's postgresql-common ships /usr/bin/psql & friends as pg_wrapper
# perl symlinks — the REAL binaries live in /usr/lib/postgresql/NN/bin,
# so stage from there, never from /usr/bin.
cp -rp /usr/lib/postgresql/${PG_MAJOR}/bin/. $PG_PREFIX/bin/
cp -rp /usr/lib/postgresql/${PG_MAJOR}/lib/. $PG_PREFIX/lib/
mkdir -p $PG_PREFIX/share
cp -rp /usr/share/postgresql/${PG_MAJOR}/. $PG_PREFIX/share/
# ecpg preprocessor + its runtime libs: on deb these live outside the PG
# tree (libecpg-dev ships /usr/bin/ecpg; libecpg6/libecpg-compat3/libpgtypes3
# ship the .so families in the multiarch dir). The official tarball carries
# them in the PG component, matching the RPM -devel package content.
cp /usr/bin/ecpg $PG_PREFIX/bin/
cp -a $LIBDIR/libecpg.so* $LIBDIR/libecpg_compat.so* $LIBDIR/libpgtypes.so* \
      $PG_PREFIX/lib/
# Headers: flat client/ecpg headers + libpq/ + informix/ + internal/ are
# already official-layout under /usr/include/postgresql; the server headers
# are nested one level deeper (<major>/server) than the official include/server.
mkdir -p $PG_PREFIX/include
cp -rp /usr/include/postgresql/. $PG_PREFIX/include/
if [ -d "$PG_PREFIX/include/${PG_MAJOR}/server" ]; then
    mv "$PG_PREFIX/include/${PG_MAJOR}/server" "$PG_PREFIX/include/server"
    rmdir "$PG_PREFIX/include/${PG_MAJOR}" 2>/dev/null || true
fi
# doc/
mkdir -p $PG_PREFIX/doc
for d in /usr/share/doc/percona-postgresql*-${PG_MAJOR}*; do
    [ -d "$d" ] && cp -rp "$d" $PG_PREFIX/doc/ || true
done

###############################################################
# 2b. PostgreSQL cleanup + psql wrapper + gather.sql
###############################################################
# Remove dev-only indent tools (shipped by percona-postgresql-server-dev)
# that the official tarball does not carry
rm -f $PG_PREFIX/bin/pg_bsd_indent $PG_PREFIX/bin/pgindent 2>/dev/null || true

# gather.sql from percona-pg-gather (installed to PG share/contrib on deb)
for f in /usr/share/postgresql/${PG_MAJOR}/contrib/gather.sql \
          /usr/share/percona-pg_gather/gather.sql /usr/bin/gather.sql; do
    [ -f "$f" ] && cp "$f" $PG_PREFIX/bin/ && break || true
done

# psql wrapper: rename real binary to psql.bin, create wrapper (matches reference tarball)
mv $PG_PREFIX/bin/psql $PG_PREFIX/bin/psql.bin
cat > $PG_PREFIX/bin/psql << 'EOF'
#!/bin/bash
PG_BIN_PATH=`dirname "$0"`
PG_LIB_PATH=$PG_BIN_PATH/../lib/
PLL=""
if [ -f /lib64/libreadline.so.8 ]; then
    PLL=/lib64/libreadline.so.8
elif [ -f /lib64/libreadline.so.7 ]; then
    PLL=/lib64/libreadline.so.7
elif [ -f /usr/lib/x86_64-linux-gnu/libreadline.so.8 ]; then
    PLL=/usr/lib/x86_64-linux-gnu/libreadline.so.8
fi
if [ -z "$PLL" ]; then
    LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$PG_BIN_PATH/../lib "$PG_BIN_PATH/psql.bin" "$@"
else
    LD_PRELOAD=$PLL LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$PG_BIN_PATH/../lib "$PG_BIN_PATH/psql.bin" "$@"
fi
EOF
chmod +x $PG_PREFIX/bin/psql

###############################################################
# 2c. Wrap postgres binary to set PL/Perl and PL/Tcl runtime paths
###############################################################
# Paths match docs install: extract to /opt/pgdistro/, then:
#   cp -r /opt/pgdistro/percona-perl /opt/
#   cp -r /opt/pgdistro/percona-tcl  /opt/
mv $PG_PREFIX/bin/postgres $PG_PREFIX/bin/postgres.real
cat > $PG_PREFIX/bin/postgres << EOF
#!/bin/sh
# Set bundled PL/Perl stdlib path (libperl.so @INC points to system paths by default)
export PERL5LIB="\${PERL5LIB:+\${PERL5LIB}:}/opt/percona-perl/lib/${PERL_VER}"
# Set bundled Tcl library path so pltcl can find init.tcl
export TCL_LIBRARY="/opt/percona-tcl/lib/tcl${TCL_VER}"
SELFDIR="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$SELFDIR/postgres.real" "\$@"
EOF
chmod +x $PG_PREFIX/bin/postgres

###############################################################
# 3. pgBouncer
###############################################################
cp /usr/sbin/pgbouncer /opt/percona-pgbouncer/bin/
[ -d /etc/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/etc && \
    cp -rp /etc/pgbouncer/. /opt/percona-pgbouncer/etc/ || true
# share/doc (the deb only ships a Debian changelog — copied opportunistically
# for parity with the RPM builder's doc handling)
[ -d /usr/share/doc/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/share/doc && \
    cp -rp /usr/share/doc/pgbouncer /opt/percona-pgbouncer/share/doc/ || true
[ -d /usr/share/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/share && \
    cp -rp /usr/share/pgbouncer /opt/percona-pgbouncer/share/ || true

###############################################################
# 4. pgPool-II
###############################################################
# Debian installs the daemon and all pcp_*/admin tools into /usr/sbin
# (pgpool_setup, watchdog_setup, wd_cli, pg_md5, pg_enc, pgproto included);
# scan /usr/bin too in case future packaging moves the client tools there.
find /usr/sbin /usr/bin -maxdepth 1 \( -name 'pgpool' -o -name 'pcp_*' -o -name 'pg_md5' \
    -o -name 'pgslap' -o -name 'pgpool_*' \
    -o -name 'pg_enc' -o -name 'pgproto' \
    -o -name 'watchdog_setup' -o -name 'wd_cli' \) -exec cp {} /opt/percona-pgpool-II/bin/ \;
# Config dir is /etc/pgpool2 on deb; the official tarball nests it as
# etc/pgpool2/ inside the component, so copy the directory itself.
[ -d /etc/pgpool2 ] && \
    mkdir -p /opt/percona-pgpool-II/etc && \
    cp -rp /etc/pgpool2 /opt/percona-pgpool-II/etc/ || true
# share/ and include/
[ -d /usr/share/pgpool2 ] && cp -rp /usr/share/pgpool2 /opt/percona-pgpool-II/share/ || true
# Headers from libpgpool-dev are already nested under /usr/include/pgpool2
# (pcp.h, libpcp_ext.h, pool_*.h) — exactly the reference include/pgpool2/ layout.
if [ -d /usr/include/pgpool2 ]; then
    mkdir -p /opt/percona-pgpool-II/include
    cp -rp /usr/include/pgpool2 /opt/percona-pgpool-II/include/
fi

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
# License (debs ship no LICENSE file; fall back to the Debian copyright file)
for f in /usr/share/doc/percona-pgbackrest/LICENSE \
          /usr/share/doc/percona-pgbackrest/copyright; do
    [ -f "$f" ] && cp "$f" /opt/percona-pgbackrest/pgbackrest_license && break || true
done

###############################################################
# 6. pgBadger -- flat layout (matches reference)
###############################################################
cp /usr/bin/pgbadger /opt/percona-pgbadger/pgbadger
rmdir /opt/percona-pgbadger/bin /opt/percona-pgbadger/lib 2>/dev/null || true
# Man page
find /usr/share/man -name 'pgbadger.1*' -exec sh -c 'f="{}"; case "$f" in *.gz) gunzip -c "$f" > /opt/percona-pgbadger/pgbadger.1p ;; *) cp "$f" /opt/percona-pgbadger/pgbadger.1p ;; esac' \; 2>/dev/null || true
# License and README (the deb ships only the Debian copyright file, which
# stands in for LICENSE; READMEs may be gzip-compressed under /usr/share/doc)
for d in /usr/share/doc/percona-pgbadger*; do
    [ -d "$d" ] || continue
    [ -f "$d/LICENSE" ] && cp "$d/LICENSE" /opt/percona-pgbadger/LICENSE || true
    [ ! -f /opt/percona-pgbadger/LICENSE ] && [ -f "$d/copyright" ] && \
        cp "$d/copyright" /opt/percona-pgbadger/LICENSE || true
    for readme in "$d"/README*; do
        [ -f "$readme" ] || continue
        case "$readme" in
            *.gz) gunzip -c "$readme" > /opt/percona-pgbadger/README.md ;;
            *)    cp "$readme" /opt/percona-pgbadger/README.md ;;
        esac
        break
    done
done

###############################################################
# 7. Bundle Python -> /opt/percona-python3
###############################################################
cp "/usr/bin/python${PY_VER}" "$PYTHON_PREFIX/bin/python${PY_VER}"

# Copy standard library (pure Python) and compiled extension modules into lib/
# (single /usr/lib tree on deb — no lib64 merge needed)
[ -d /usr/lib/python${PY_VER} ] && cp -rp /usr/lib/python${PY_VER} $PYTHON_PREFIX/lib/ || true

# NOTE: no lib64 compatibility symlink here. Debian builds python with
# sys.platlibdir='lib' (verified with the bundled binary: PYTHONHOME lookup
# resolves via lib/pythonX.Y only), unlike the EL pythons whose compiled-in
# platlibdir is 'lib64'.

# Copy libpython shared lib with symlinks
cp -a ${LIBDIR}/libpython${PY_VER}*.so* $PYTHON_PREFIX/lib/ 2>/dev/null || true
cp -a ${LIBDIR}/libpython3.so $PYTHON_PREFIX/lib/ 2>/dev/null || true
ln -sf libpython${PY_VER}.so.1.0 $PYTHON_PREFIX/lib/libpython${PY_VER}.so 2>/dev/null || true
ln -sf libpython${PY_VER}.so $PYTHON_PREFIX/lib/libpython3.so 2>/dev/null || true

# Copy libffi (reference bundles it)
cp -a ${LIBDIR}/libffi.so* $PYTHON_PREFIX/lib/ 2>/dev/null || true

# include/
[ -d /usr/include/python${PY_VER} ] && \
    mkdir -p $PYTHON_PREFIX/include && \
    cp -rp /usr/include/python${PY_VER} $PYTHON_PREFIX/include/ || true

# pkgconfig
mkdir -p $PYTHON_PREFIX/lib/pkgconfig
cp ${LIBDIR}/pkgconfig/python-${PY_VER}*.pc $PYTHON_PREFIX/lib/pkgconfig/ 2>/dev/null || true

# share/man (reference ships the python man page uncompressed + python3.1 alias)
mkdir -p $PYTHON_PREFIX/share/man/man1
for m in /usr/share/man/man1/python${PY_VER}.1*; do
    [ -e "$m" ] || continue
    case "$m" in
        *.gz) gunzip -c "$m" > $PYTHON_PREFIX/share/man/man1/python${PY_VER}.1 ;;
        *)    cp -p "$m" $PYTHON_PREFIX/share/man/man1/ ;;
    esac
done
[ -f $PYTHON_PREFIX/share/man/man1/python${PY_VER}.1 ] && \
    ln -sf python${PY_VER}.1 $PYTHON_PREFIX/share/man/man1/python3.1 || true

# Copy Python utility scripts and update shebangs to bundled python
# Note: with PY_VER=X.Y, pip3.${PY_VER#*.} = pip3.Y and 2to3-${PY_VER} = 2to3-X.Y
for script in pip pip3 pip3.${PY_VER#*.} 2to3 2to3-${PY_VER} \
              idle3 idle${PY_VER} pydoc3 pydoc${PY_VER} \
              python3-config python${PY_VER}-config \
              syncobj_admin jp.py; do
    [ -f "/usr/bin/$script" ] && cp "/usr/bin/$script" $PYTHON_PREFIX/bin/ || true
done
# ydiff is a Python module with no /usr/bin script; create a wrapper
# (pure-python modules live in /usr/lib/python3/dist-packages on deb)
if [ -f /usr/lib/python3/dist-packages/ydiff.py ]; then
    cat > $PYTHON_PREFIX/bin/ydiff << 'WEOF'
#!/opt/percona-python3/bin/python3
from ydiff import main
import sys
sys.exit(main())
WEOF
    chmod +x $PYTHON_PREFIX/bin/ydiff
fi
for script in $PYTHON_PREFIX/bin/pip $PYTHON_PREFIX/bin/pip3 \
              $PYTHON_PREFIX/bin/pip${PY_VER} \
              $PYTHON_PREFIX/bin/syncobj_admin $PYTHON_PREFIX/bin/ydiff \
              $PYTHON_PREFIX/bin/jp.py $PYTHON_PREFIX/bin/2to3 \
              $PYTHON_PREFIX/bin/2to3-${PY_VER} $PYTHON_PREFIX/bin/pydoc3 \
              $PYTHON_PREFIX/bin/pydoc${PY_VER} $PYTHON_PREFIX/bin/idle3 \
              $PYTHON_PREFIX/bin/idle${PY_VER}; do
    [ -f "$script" ] && \
        sed -i "1s|^#!.*python.*|#!/opt/percona-python3/bin/python3|" "$script" || true
done

###############################################################
# 8. Patroni -- copy from deb-installed location into bundled Python
###############################################################
# Debian's site.py resolves site directories under a foreign PYTHONHOME to
# <prefix>/lib/python3/dist-packages (verified with the bundled binary:
# site.getsitepackages() = [<prefix>/local/lib/pyX.Y/dist-packages,
# <prefix>/lib/python3/dist-packages, <prefix>/lib/pyX.Y/dist-packages]),
# so the bundled tree mirrors the host's version-agnostic dist-packages
# layout instead of the RPM builder's site-packages.
SITE_DEST=$PYTHON_PREFIX/lib/python3/dist-packages
mkdir -p "$SITE_DEST"

# All third-party python packages (pure AND compiled) live in the single
# version-agnostic /usr/lib/python3/dist-packages on deb; compiled .so
# extensions there target the distro python and match the bundled one.
# Debian packages ship egg-info directories more often than dist-info,
# so both spellings are globbed. cdiff/ydiff are extra deb-side patroni
# dependencies (Depends: python3-cdiff, python3-ydiff).
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
           consul py_consul-*.dist-info python_consul-*.egg-info \
           prettytable prettytable-*.dist-info prettytable-*.egg-info \
           packaging packaging-*.dist-info packaging-*.egg-info \
           typing_extensions typing_extensions-*.dist-info typing_extensions-*.egg-info \
           requests requests-*.dist-info requests-*.egg-info \
           charset_normalizer charset_normalizer-*.dist-info charset_normalizer-*.egg-info \
           chardet chardet-*.egg-info \
           idna idna-*.dist-info idna-*.egg-info \
           yaml PyYAML-*.dist-info PyYAML-*.egg-info _yaml \
           wcwidth wcwidth-*.dist-info wcwidth-*.egg-info \
           cryptography cryptography-*.dist-info cryptography-*.egg-info \
           cffi cffi-*.dist-info cffi-*.egg-info _cffi_backend* \
           pycparser pycparser-*.dist-info pycparser-*.egg-info \
           cdiff.py cdiff-*.egg-info ydiff.py ydiff-*.egg-info; do
    for match in /usr/lib/python3/dist-packages/$pkg; do
        [ -e "$match" ] && cp -rp "$match" "$SITE_DEST/" 2>/dev/null || true
    done
done

# Copy patroni binaries, rewriting shebang to bundled Python
mkdir -p /opt/percona-patroni/bin
for pbin in patroni patronictl patroni_barman patroni_raft_controller patroni_aws patroni_wale_restore; do
    [ -f "/usr/bin/$pbin" ] || continue
    cp "/usr/bin/$pbin" "/opt/percona-patroni/bin/$pbin"
    sed -i "1s|^#!.*|#!/opt/percona-python3/bin/python3|" "/opt/percona-patroni/bin/$pbin"
done

# share/doc and license (debs ship no LICENSE; use the copyright file)
mkdir -p /opt/percona-patroni/share/doc
for d in /usr/share/doc/percona-patroni*; do
    [ -d "$d" ] && cp -rp "$d"/. /opt/percona-patroni/share/doc/ || true
done
for f in /usr/share/doc/percona-patroni/LICENSE \
          /usr/share/doc/percona-patroni/copyright; do
    [ -f "$f" ] && cp "$f" /opt/percona-patroni/patroni_license && break || true
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
# 10. Bundle Perl -> /opt/percona-perl
###############################################################
# Debian scatters the perl tree across four Config-defined directories;
# flatten them into lib/<version>/ exactly like the RPM builder does with
# the EL lib64/share split:
#   archlib    /usr/lib/<multiarch>/perl/5.NN   (XS core modules + CORE/)
#   privlib    /usr/share/perl/5.NN             (pure-perl core)
#   vendorarch /usr/lib/<multiarch>/perl5/5.NN  (vendor XS: JSON::XS, ...)
#   vendorlib  /usr/share/perl5                 (vendor pure-perl)
PERL_ARCH=$(perl -MConfig -e 'print $Config{archname}')
PERL_ARCHLIB=$(perl -MConfig -e 'print $Config{archlib}')
PERL_PRIVLIB=$(perl -MConfig -e 'print $Config{privlib}')
PERL_VENDORARCH=$(perl -MConfig -e 'print $Config{vendorarch}')
PERL_VENDORLIB=$(perl -MConfig -e 'print $Config{vendorlib}')

cp /usr/bin/perl $PERL_PREFIX/bin/
[ -f "/usr/bin/perl${PERL_VER}" ] && cp "/usr/bin/perl${PERL_VER}" $PERL_PREFIX/bin/ || true

mkdir -p $PERL_PREFIX/lib/${PERL_VER}
[ -d "$PERL_ARCHLIB" ] && cp -rp "$PERL_ARCHLIB"/. $PERL_PREFIX/lib/${PERL_VER}/ || true
[ -d "$PERL_PRIVLIB" ] && cp -rp "$PERL_PRIVLIB"/. $PERL_PREFIX/lib/${PERL_VER}/ || true
[ -d "$PERL_VENDORARCH" ] && cp -rp "$PERL_VENDORARCH"/. $PERL_PREFIX/lib/${PERL_VER}/ || true
[ -d "$PERL_VENDORLIB" ] && cp -rp "$PERL_VENDORLIB"/. $PERL_PREFIX/lib/${PERL_VER}/ || true

# site_perl (usually empty in a fresh buildroot; copied for parity)
mkdir -p $PERL_PREFIX/lib/site_perl
[ -d /usr/local/lib/${MULTIARCH}/perl ] && \
    cp -rp /usr/local/lib/${MULTIARCH}/perl/. $PERL_PREFIX/lib/site_perl/ || true
[ -d /usr/local/share/perl ] && \
    cp -rp /usr/local/share/perl/. $PERL_PREFIX/lib/site_perl/ || true

# Prune Net::SSLeay from the staged tree. The official Percona tarball does
# not ship it, and its XS module (auto/Net/SSLeay/SSLeay.so) links the HOST
# libssl/libcrypto with newer version needs — that would violate the ssl
# variant host-ABI promise enforced by the verification gate (section 15).
# On Ubuntu it only appears if libnet-ssleay-perl got pulled in (e.g. via
# Recommends), so this is a safety net; sweep the whole prefix anyway:
# both the XS dirs (*/auto/Net/SSLeay) and the pure-perl parts
# (Net/SSLeay.pm + Net/SSLeay.pod + Net/SSLeay/ support dir). Note: the
# path patterns are anchored under Net/ so the unrelated
# Software::License::SSLeay module is left alone.
find "$PERL_PREFIX" -type d -path '*/Net/SSLeay' -prune -exec rm -rf {} +
find "$PERL_PREFIX" -type f \( -path '*/Net/SSLeay.pm' -o -path '*/Net/SSLeay.pod' \) -delete
# Prune IO::Socket::SSL as well: it is pure perl (no host-ABI impact) but
# hard-requires the Net::SSLeay XS module pruned above, so it could never
# load — and the official tarball's percona-perl tree does not ship it
# either (the only IO/Socket/SSL in the official artifact sits inside
# pgbackrest's private bin/vendor_perl bundle, which we do not stage).
find "$PERL_PREFIX" -type d -path '*/IO/Socket/SSL' -prune -exec rm -rf {} +
find "$PERL_PREFIX" -type f \( -path '*/IO/Socket/SSL.pm' -o -path '*/IO/Socket/SSL.pod' \) -delete

# Copy libcrypt into Perl CORE dir (reference does this)
CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
if [ -n "$CORE_DIR" ] && [ -d "$CORE_DIR" ]; then
    cp -a $LIBDIR/libcrypt.so* "$CORE_DIR/" 2>/dev/null || true
fi

# Man pages
mkdir -p $PERL_PREFIX/man/man1 $PERL_PREFIX/man/man3
cp /usr/share/man/man1/perl*.1* $PERL_PREFIX/man/man1/ 2>/dev/null || true

# Copy Perl utility scripts from /usr/bin/
for script in corelist cpan enc2xs encguess h2ph h2xs instmodsh json_pp \
              libnetcfg perlbug perldoc perlivp perlthanks piconv pl2pm \
              pod2html pod2man pod2text pod2usage podchecker prove ptar \
              ptardiff ptargrep shasum splain streamzip xsubpp zipdetails; do
    [ -f "/usr/bin/$script" ] && cp "/usr/bin/$script" $PERL_PREFIX/bin/ || true
done
# Update shebangs on Perl scripts to use bundled perl
for script in $PERL_PREFIX/bin/corelist $PERL_PREFIX/bin/cpan \
              $PERL_PREFIX/bin/enc2xs $PERL_PREFIX/bin/json_pp \
              $PERL_PREFIX/bin/pod2html $PERL_PREFIX/bin/pod2man \
              $PERL_PREFIX/bin/pod2text $PERL_PREFIX/bin/pod2usage \
              $PERL_PREFIX/bin/perldoc $PERL_PREFIX/bin/prove \
              $PERL_PREFIX/bin/ptar $PERL_PREFIX/bin/ptardiff \
              $PERL_PREFIX/bin/ptargrep $PERL_PREFIX/bin/shasum \
              $PERL_PREFIX/bin/instmodsh $PERL_PREFIX/bin/piconv \
              $PERL_PREFIX/bin/pl2pm $PERL_PREFIX/bin/podchecker \
              $PERL_PREFIX/bin/splain $PERL_PREFIX/bin/streamzip \
              $PERL_PREFIX/bin/xsubpp $PERL_PREFIX/bin/zipdetails; do
    [ -f "$script" ] && \
        sed -i "1s|^#!.*perl.*|#!/opt/percona-perl/bin/perl|" "$script" || true
done

###############################################################
# 11. Bundle Tcl -> /opt/percona-tcl
###############################################################
cp /usr/bin/tclsh${TCL_VER} $TCL_PREFIX/bin/
ln -sf tclsh${TCL_VER} $TCL_PREFIX/bin/tclsh

# Copy libtcl shared lib (Debian: real file libtclX.Y.so.0 + libtclX.Y.so
# dev symlink in the multiarch dir; pltcl.so's NEEDED soname is the
# unversioned libtclX.Y.so)
cp -a $LIBDIR/libtcl${TCL_VER}.so* $TCL_PREFIX/lib/ 2>/dev/null || true
cp -a $LIBDIR/libtclstub${TCL_VER}.a $TCL_PREFIX/lib/ 2>/dev/null || true

# Tcl library directories (stdlib is under /usr/share/tcltk on deb)
mkdir -p $TCL_PREFIX/lib/tcl${TCL_VER}
[ -d /usr/share/tcltk/tcl${TCL_VER} ] && \
    cp -rp /usr/share/tcltk/tcl${TCL_VER}/. $TCL_PREFIX/lib/tcl${TCL_VER}/ || true
[ -d /usr/share/tcltk/tcl8 ] && cp -rp /usr/share/tcltk/tcl8 $TCL_PREFIX/lib/ || true

# Tcl extension packages (itcl/tdbc/thread/sqlite live under /usr/lib/tcltk
# on deb when installed; absent from a minimal tcl buildroot)
for ext in /usr/lib/tcltk/${MULTIARCH}/* /usr/lib/tcltk/*; do
    [ -e "$ext" ] || continue
    case "$(basename "$ext")" in
        itcl*|tdbc*|thread*|sqlite*) cp -rp "$ext" $TCL_PREFIX/lib/ || true ;;
    esac
done

# tclConfig.sh
cp $LIBDIR/tclConfig.sh $TCL_PREFIX/lib/ 2>/dev/null || true
cp $LIBDIR/tclooConfig.sh $TCL_PREFIX/lib/ 2>/dev/null || true

# pkgconfig
mkdir -p $TCL_PREFIX/lib/pkgconfig
cp $LIBDIR/pkgconfig/tcl.pc $TCL_PREFIX/lib/pkgconfig/ 2>/dev/null || true

# include/ (tcl-dev nests headers under /usr/include/tclX.Y on deb)
mkdir -p $TCL_PREFIX/include
cp /usr/include/tcl${TCL_VER}/tcl*.h $TCL_PREFIX/include/ 2>/dev/null || true

# man pages (Debian ships Tcl C-API/command man pages in the separate
# tcl8.6-doc package, so usually only tclsh.1 is present — same accepted
# divergence as the RPM builder's tcl man handling)
mkdir -p $TCL_PREFIX/man/man1 $TCL_PREFIX/man/man3 $TCL_PREFIX/man/mann
cp /usr/share/man/man1/tclsh*.1* $TCL_PREFIX/man/man1/ 2>/dev/null || true
cp /usr/share/man/man3/Tcl*.3* $TCL_PREFIX/man/man3/ 2>/dev/null || true
cp /usr/share/man/mann/*.n* $TCL_PREFIX/man/mann/ 2>/dev/null || true

# sqlite3_analyzer (not packaged on deb; copied when available)
for f in /usr/bin/sqlite3_analyzer; do
    [ -f "$f" ] && cp "$f" $TCL_PREFIX/bin/ && break || true
done

###############################################################
# 12. Fix Perl, Tcl, Python for portable execution
###############################################################

# --- Perl ---
# libperl.so.X.Y.Z lives in the multiarch dir, not inside the perl tree
# (Debian archlib CORE/ has only headers); copy into CORE
CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
if [ -n "$CORE_DIR" ]; then
    # Copy only the real file (not symlinks) from the multiarch dir
    LIBPERL_REAL_PATH=$(find $LIBDIR -maxdepth 1 -name "libperl.so.*" -not -type l | head -1)
    LIBPERL_REAL=$(basename "$LIBPERL_REAL_PATH")
    cp -p "$LIBPERL_REAL_PATH" "$CORE_DIR/"
    # Recreate SONAME symlink and unversioned symlink pointing to real file
    ln -sf "$LIBPERL_REAL" "$CORE_DIR/libperl.so.${PERL_VER%.*}"  # e.g. libperl.so.5.34
    ln -sf "$LIBPERL_REAL" "$CORE_DIR/libperl.so"
    # RPATH libperl itself: RUNPATH is not transitive, so libperl.so must be
    # able to find its own deps (libcrypt copied into CORE/ above).
    patchelf --set-rpath '$ORIGIN' "$CORE_DIR/$LIBPERL_REAL"
fi
# patchelf perl binary so dynamic linker finds libperl in CORE at $ORIGIN
patchelf --set-rpath "\$ORIGIN/../lib/${PERL_VER}/CORE" "$PERL_PREFIX/bin/perl"

# --- Tcl ---
# patchelf tclsh so it finds libtclX.Y.so in $PREFIX/lib
patchelf --set-rpath '$ORIGIN/../lib' "$TCL_PREFIX/bin/tclsh${TCL_VER}"
# Replace tclsh symlink with wrapper that sets TCL_LIBRARY at runtime
rm -f "$TCL_PREFIX/bin/tclsh"
cat > "$TCL_PREFIX/bin/tclsh" << EOF
#!/bin/sh
SELFDIR="\$(cd "\$(dirname "\$0")" && pwd)"
PREFIX="\$(dirname "\$SELFDIR")"
export TCL_LIBRARY="\$PREFIX/lib/tcl${TCL_VER}"
export TCLLIBPATH="\$PREFIX/lib"
exec "\$SELFDIR/tclsh${TCL_VER}" "\$@"
EOF
chmod 755 "$TCL_PREFIX/bin/tclsh"

# --- Python ---
# The deb python3 binary has sys.prefix=/usr hardcoded; wrap it with PYTHONHOME
rm -f "$PYTHON_PREFIX/bin/python3"
cat > "$PYTHON_PREFIX/bin/python3" << EOF
#!/bin/sh
SELFDIR="\$(cd "\$(dirname "\$0")" && pwd)"
PREFIX="\$(dirname "\$SELFDIR")"
export PYTHONHOME="\$PREFIX"
# Prepend bundled lib/ so compiled extensions (e.g. _hashlib) find our OpenSSL
export LD_LIBRARY_PATH="\$PREFIX/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
exec "\$SELFDIR/python${PY_VER}" "\$@"
EOF
chmod 755 "$PYTHON_PREFIX/bin/python3"
ln -sf python3 "$PYTHON_PREFIX/bin/python" 2>/dev/null || true

###############################################################
# 13. Bundle .so deps and patchelf RPATH for ELF prefixes
###############################################################
for prefix in $PG_PREFIX /opt/percona-pgbouncer \
              /opt/percona-pgpool-II /opt/percona-pgbackrest; do
    bundle_deps "$prefix"
    patch_rpath "$prefix"
done
# Python: also walk the whole lib/pythonX.Y tree and the dist-packages tree
# (lib-dynload/ C extensions, dist-packages extensions like psycopg2/_psycopg)
# so their NEEDED libs (libsqlite3, libncursesw, libuuid, libpq, ...) are
# bundled into $PYTHON_PREFIX/lib.
bundle_deps $PYTHON_PREFIX "$PYTHON_PREFIX/lib/python${PY_VER}" "$PYTHON_PREFIX/lib/python3"
patch_rpath $PYTHON_PREFIX
# RPATH the C extensions at the bundled lib dir: the python3 wrapper sets
# LD_LIBRARY_PATH, but embedded interpreters (plpython3 inside postgres.real)
# don't run through the wrapper, and the executable's RUNPATH does not apply
# to dlopened extensions' own deps.
find "$PYTHON_PREFIX/lib/python${PY_VER}" "$PYTHON_PREFIX/lib/python3" \
        -type f -name '*.so*' 2>/dev/null | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    patchelf --set-rpath '/opt/percona-python3/lib:$ORIGIN' "$f"
done
# Perl: walk the lib tree so XS-module deps are bundled, then point the XS
# modules at the bundled libs (absolute /opt path — same convention as
# LANG_RPATH; depth under auto/ varies so $ORIGIN-relative paths won't work).
# Note: percona-perl/percona-tcl RPATHs for bin/ were already set in
# section 12 and bundle_deps does not touch RPATHs.
bundle_deps $PERL_PREFIX "$PERL_PREFIX/lib"
find "$PERL_PREFIX/lib" -type f -name '*.so' -path '*/auto/*' | while read -r f; do
    patchelf --set-rpath '/opt/percona-perl/lib:$ORIGIN' "$f"
done
# Note: etcd (Go static), pgbadger (Perl script), patroni (Python) -- no bundling needed

# Bundle OpenSSL into percona-python3 explicitly: the python tree keeps its
# OpenSSL needs internal (lib-dynload's _ssl/_hashlib and dist-packages
# extensions (psycopg2's _psycopg) resolve them to this bundled copy via
# RPATH/LD_LIBRARY_PATH), which is what lets the SSL-ABI audit below skip
# the python prefix. On Ubuntu 22.04 these link the distro OpenSSL 3.0 —
# bundling keeps python self-contained regardless of the host's OpenSSL.
for f in $LIBDIR/libssl.so.3* $LIBDIR/libcrypto.so.3*; do
    [ -f "$f" ] && cp -pn "$f" $PYTHON_PREFIX/lib/ 2>/dev/null || true
done

###############################################################
# 14. Fix PostgreSQL RPATH to include language runtime paths
###############################################################
# Find the actual CORE directory path dynamically
PERL_CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
PERL_CORE_REL=${PERL_CORE_DIR#/opt/}  # e.g., percona-perl/lib/5.34.0/CORE
LANG_RPATH='$ORIGIN/../lib:/opt/percona-python3/lib:/opt/'"${PERL_CORE_REL}"':/opt/percona-tcl/lib'
LANG_RPATH_LIB='$ORIGIN:/opt/percona-python3/lib:/opt/'"${PERL_CORE_REL}"':/opt/percona-tcl/lib'

# Patch the real postgres binary ($PG_PREFIX/bin/postgres is the shell wrapper
# created in section 2c; postmaster no longer exists in PG >= 16). Mandatory —
# fail loudly if patchelf cannot rewrite it.
patchelf --set-rpath "$LANG_RPATH" "$PG_PREFIX/bin/postgres.real"

# Patch PL language extension .so files
for ext in plperl.so plpython3.so pltcl.so; do
    [ -f "$PG_PREFIX/lib/$ext" ] && \
        patchelf --set-rpath "$LANG_RPATH_LIB" "$PG_PREFIX/lib/$ext" 2>/dev/null || true
done

# All other PostgreSQL lib/ .so files get $ORIGIN
find $PG_PREFIX/lib -name '*.so*' -type f | while read f; do
    case "$(basename "$f")" in
        plperl.so|plpython3.so|pltcl.so) continue ;;
    esac
    patchelf --set-rpath '$ORIGIN' "$f" 2>/dev/null || true
done

###############################################################
# 15. Verification gate — fail the build on any breakage
###############################################################
# The SSL variant labels follow the official tarball naming and map 1:1 to
# the deb base of the repository. Each deb base maps to exactly one variant;
# extend this table deliberately when a new base is added, and fail loudly
# on anything unmapped. Ubuntu 22.04 ships OpenSSL 3.0.2 / glibc 2.35, so
# it is the ssl3 base ("runs on any OpenSSL 3.0+ host") — staging EL9
# binaries could not keep that promise (Rocky 9.8+ links OPENSSL_3.4 nodes).
# The variant is derived here, before the gate, because the OpenSSL
# host-ABI audit below picks its allowed-symbol policy from it; section 16
# reuses it for the artifact name.
. /etc/os-release
case "${ID}-${VERSION_ID}" in
    ubuntu-22.04) SSL_VARIANT=ssl3 ;;
    *)  echo "FATAL: unmapped deb platform '${ID}-${VERSION_ID}'" >&2; exit 1 ;;
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

echo "=== Verification: OpenSSL host-ABI audit ($SSL_VARIANT) ==="
# libssl/libcrypto are deliberately NOT bundled (they are on the system
# exclude list above), so every bundled binary resolves them from the HOST
# at run time. The ssl variant label is therefore a host-compatibility
# promise: ssl3 must run on hosts with any OpenSSL 3.0+. What enforces that
# promise at the ELF level is the set of versioned symbol references
# (version NEEDS, e.g. OPENSSL_3.0.0) each binary carries against
# libssl/libcrypto: the host's loader refuses to start a binary that needs
# a version node the host libraries do not define. Ubuntu 22.04 ships
# OpenSSL 3.0.2, so staging-built binaries can only reference 3.0.x nodes —
# this audit turns that assumption into a tested guarantee (and is exactly
# why ssl3 moved off EL9, whose 3.5.x buildroot OpenSSL leaked
# OPENSSL_3.4.0 references into pgcrypto.so).
#
# Per-variant allowed version-node pattern (anchored full-line grep):
case "$SSL_VARIANT" in
    # Must run on any OpenSSL 3.0 host: only 3.0.x nodes are acceptable.
    ssl3)   OPENSSL_ALLOWED='OPENSSL_3\.0\.[0-9]*' ;;
    *)      echo "FATAL: no SSL-ABI policy for $SSL_VARIANT" >&2; exit 1 ;;
esac
# Scan every ELF under /opt EXCEPT the percona-python3 tree: the python
# component bundles its own OpenSSL copy (libssl/libcrypto in its lib/,
# used by lib-dynload extensions like _ssl/_hashlib and by dist-packages
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

echo "=== Verification: smoke commands ==="
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/initdb" --version
env -u LD_LIBRARY_PATH "$PG_PREFIX/bin/postgres.real" --version
"$PYTHON_PREFIX/bin/python3" -c 'import ssl, yaml; print("python OK")'
"$PYTHON_PREFIX/bin/python3" -c 'import patroni; print("patroni import OK")'
"$PERL_PREFIX/bin/perl" -e 'print "perl OK\n"'
echo 'puts "tcl OK"' | "$TCL_PREFIX/bin/tclsh"

###############################################################
# 16. Create the final artifact with the official tarball name
###############################################################
# The simpleimage recipe names its own output from raw (unexpanded)
# Name:/Version: tags, which cannot vary per repository. Instead we
# write the artifact directly into /usr/src/packages/OTHER (collected
# by OBS as a build result) and skip /.simpleimage.tar.gz entirely.
# Debian versions carry an epoch and revision (e.g. 2:17.10-1+2.1);
# strip both to get the upstream 17.10.
PG_FULL_VERSION=$(dpkg-query -W -f '${Version}' "percona-postgresql-${PG_MAJOR}")
PG_FULL_VERSION=${PG_FULL_VERSION#*:}
PG_FULL_VERSION=${PG_FULL_VERSION%%-*}
# SSL_VARIANT was derived at the top of section 15 (deb-base mapping),
# where the OpenSSL host-ABI audit also depends on it.
TARBALL="percona-postgresql-${PG_FULL_VERSION}-${SSL_VARIANT}-linux-$(uname -m).tar.gz"
mkdir -p /usr/src/packages/OTHER
cd /opt
tar -czf "/usr/src/packages/OTHER/${TARBALL}" -- *
echo "Created ${TARBALL}"
