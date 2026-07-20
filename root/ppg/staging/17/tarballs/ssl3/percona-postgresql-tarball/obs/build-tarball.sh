#!/bin/bash
# Builds the Percona PostgreSQL binary tarball from RPM-installed content.
# Runs chrooted as root inside an OBS simpleimage buildroot; writes the
# final artifact to /.simpleimage.tar.gz (picked up via #!NoTarBall).
set -e

PG_MAJOR=$(basename "$(ls -d /usr/pgsql-*)" | sed 's/^pgsql-//')
[ -n "$PG_MAJOR" ] || { echo "FATAL: no /usr/pgsql-* tree found" >&2; exit 1; }

# Prefer the parallel 3.12 stack (EL8/EL9); fall back to the default python3 (EL10+).
PY_BIN=$(command -v python3.12 || command -v python3)
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
# system and must NOT be bundled (matches pg_tarballs_builder.sh)
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

# Run copy_deps over all ELF files in a prefix (3 passes for dep depth)
bundle_deps() {
    local prefix="$1"
    local libdir="$prefix/lib"
    mkdir -p "$libdir"
    for pass in 1 2 3; do
        find "$prefix/bin" "$libdir" -maxdepth 1 -type f 2>/dev/null | while read f; do
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
# 2b. PostgreSQL cleanup + psql wrapper + gather.sql
###############################################################
# Remove RPM service helpers that don't belong in the tarball
rm -f $PG_PREFIX/bin/postgresql-${PG_MAJOR}-* 2>/dev/null || true

# gather.sql from percona-pg_gather (installed to pgsql share/contrib)
for f in /usr/pgsql-${PG_MAJOR}/share/contrib/gather.sql \
          /usr/share/percona-pg_gather/gather.sql /usr/bin/gather.sql \
          /usr/share/pgsql/gather.sql; do
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
cp /usr/bin/pgbouncer /opt/percona-pgbouncer/bin/
[ -d /etc/pgbouncer ] && \
    mkdir -p /opt/percona-pgbouncer/etc && \
    cp -rp /etc/pgbouncer/. /opt/percona-pgbouncer/etc/ || true
# share/ and doc/
for d in /usr/share/doc/percona-pgbouncer*; do
    [ -d "$d" ] && mkdir -p /opt/percona-pgbouncer/doc && cp -rp "$d" /opt/percona-pgbouncer/doc/ || true
done
[ -d /usr/share/pgbouncer ] && cp -rp /usr/share/pgbouncer /opt/percona-pgbouncer/share/ || true

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
for d in /usr/include/pgpool*; do
    [ -e "$d" ] && mkdir -p /opt/percona-pgpool-II/include && cp -rp "$d" /opt/percona-pgpool-II/include/ || true
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
# License
for d in /usr/share/doc/percona-pgbackrest*; do
    [ -d "$d" ] && cp "$d"/LICENSE /opt/percona-pgbackrest/pgbackrest_license 2>/dev/null || true
done

###############################################################
# 6. pgBadger -- flat layout (matches reference)
###############################################################
cp /usr/bin/pgbadger /opt/percona-pgbadger/pgbadger
rmdir /opt/percona-pgbadger/bin /opt/percona-pgbadger/lib 2>/dev/null || true
# Man page
find /usr/share/man -name 'pgbadger.1*' -exec sh -c 'f="{}"; case "$f" in *.gz) gunzip -c "$f" > /opt/percona-pgbadger/pgbadger.1p ;; *) cp "$f" /opt/percona-pgbadger/pgbadger.1p ;; esac' \; 2>/dev/null || true
# License and README
for d in /usr/share/doc/percona-pgbadger*; do
    [ -d "$d" ] || continue
    [ -f "$d/LICENSE" ] && cp "$d/LICENSE" /opt/percona-pgbadger/LICENSE || true
    for readme in "$d"/README*; do
        [ -f "$readme" ] && cp "$readme" /opt/percona-pgbadger/README.md && break || true
    done
done

###############################################################
# 7. Bundle Python -> /opt/percona-python3
###############################################################
cp "$PY_BIN" "$PYTHON_PREFIX/bin/python${PY_VER}"

# Copy standard library (pure Python) and compiled extension modules into lib/
[ -d /usr/lib/python${PY_VER} ] && cp -rp /usr/lib/python${PY_VER} $PYTHON_PREFIX/lib/ || true
[ -d /usr/lib64/python${PY_VER} ] && cp -rp /usr/lib64/python${PY_VER}/. $PYTHON_PREFIX/lib/python${PY_VER}/ 2>/dev/null || true

# Python binary has sys.platlibdir='lib64' compiled in, so it searches lib64/pythonX.Y/
# Create a symlink so PYTHONHOME lookup via lib64 resolves to our lib/ tree
mkdir -p $PYTHON_PREFIX/lib64
ln -sf ../lib/python${PY_VER} $PYTHON_PREFIX/lib64/python${PY_VER}

# Copy libpython shared lib with symlinks
LIBPYTHON_DIR=/usr/lib64
cp -a ${LIBPYTHON_DIR}/libpython${PY_VER}*.so* $PYTHON_PREFIX/lib/ 2>/dev/null || true
cp -a ${LIBPYTHON_DIR}/libpython3.so $PYTHON_PREFIX/lib/ 2>/dev/null || true
ln -sf libpython${PY_VER}.so.1.0 $PYTHON_PREFIX/lib/libpython${PY_VER}.so 2>/dev/null || true
ln -sf libpython${PY_VER}.so $PYTHON_PREFIX/lib/libpython3.so 2>/dev/null || true

# Copy libffi (reference bundles it)
cp -a /usr/lib64/libffi.so* $PYTHON_PREFIX/lib/ 2>/dev/null || true

# include/
[ -d /usr/include/python${PY_VER} ] && \
    mkdir -p $PYTHON_PREFIX/include && \
    cp -rp /usr/include/python${PY_VER} $PYTHON_PREFIX/include/ || true

# pkgconfig
mkdir -p $PYTHON_PREFIX/lib/pkgconfig
cp /usr/lib64/pkgconfig/python-${PY_VER}*.pc $PYTHON_PREFIX/lib/pkgconfig/ 2>/dev/null || true

# Copy Python utility scripts and update shebangs to bundled python
# Note: with PY_VER=X.Y, pip3.${PY_VER#*.} = pip3.Y and 2to3-${PY_VER} = 2to3-X.Y
for script in pip pip3 pip3.${PY_VER#*.} 2to3 2to3-${PY_VER} \
              idle3 idle${PY_VER} pydoc3 pydoc${PY_VER} \
              python3-config python${PY_VER}-config \
              syncobj_admin jp.py; do
    [ -f "/usr/bin/$script" ] && cp "/usr/bin/$script" $PYTHON_PREFIX/bin/ || true
done
# ydiff is a Python module with no /usr/bin script; create a wrapper
if [ -f /usr/lib/python${PY_VER}/site-packages/ydiff.py ]; then
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
# 8. Patroni -- copy from RPM-installed location into bundled Python
###############################################################
SITE_DEST=$PYTHON_PREFIX/lib/python${PY_VER}/site-packages
mkdir -p "$SITE_DEST"

# Patroni may be installed under a different Python version (e.g. system python3.9).
# Search ALL Python site-packages directories to find the packages.
# Pure Python packages work across any Python version; compiled .so extensions
# that match the bundled Python version will also be usable.
for pkg in patroni patroni-*.dist-info patroni-*.egg-info \
           click click-*.dist-info \
           dateutil python_dateutil-*.dist-info \
           psutil psutil-*.dist-info psutil-*.egg-info \
           urllib3 urllib3-*.dist-info \
           six.py six-*.dist-info \
           certifi certifi-*.dist-info \
           dns dnspython-*.dist-info \
           pysyncobj pysyncobj-*.dist-info \
           kazoo kazoo-*.dist-info \
           etcd python_etcd-*.dist-info python_etcd-*.egg-info \
           boto3 boto3-*.dist-info botocore botocore-*.dist-info \
           consul py_consul-*.dist-info \
           prettytable prettytable-*.dist-info \
           packaging packaging-*.dist-info \
           typing_extensions typing_extensions-*.dist-info \
           requests requests-*.dist-info \
           charset_normalizer charset_normalizer-*.dist-info \
           idna idna-*.dist-info \
           yaml PyYAML-*.dist-info _yaml \
           wcwidth wcwidth-*.dist-info \
           cryptography cryptography-*.dist-info \
           cffi cffi-*.dist-info _cffi_backend* \
           pycparser pycparser-*.dist-info; do
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
for d in /usr/share/doc/percona-patroni*; do
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
# 10. Bundle Perl -> /opt/percona-perl
###############################################################
PERL_ARCH=$(perl -MConfig -e 'print $Config{archname}')

cp /usr/bin/perl $PERL_PREFIX/bin/
[ -f "/usr/bin/perl${PERL_VER}" ] && cp "/usr/bin/perl${PERL_VER}" $PERL_PREFIX/bin/ || true

# Core modules (arch-specific with CORE/ containing libperl.so)
mkdir -p $PERL_PREFIX/lib/${PERL_VER}
[ -d /usr/lib64/perl5/${PERL_VER} ] && \
    cp -rp /usr/lib64/perl5/${PERL_VER}/. $PERL_PREFIX/lib/${PERL_VER}/ || true
# Also check non-versioned path
[ -d /usr/lib64/perl5 ] && [ ! -d /usr/lib64/perl5/${PERL_VER} ] && \
    cp -rp /usr/lib64/perl5/. $PERL_PREFIX/lib/${PERL_VER}/ || true

# Pure-perl modules
[ -d /usr/share/perl5/${PERL_VER} ] && \
    cp -rp /usr/share/perl5/${PERL_VER}/. $PERL_PREFIX/lib/${PERL_VER}/ || true
[ -d /usr/share/perl5 ] && [ ! -d /usr/share/perl5/${PERL_VER} ] && \
    cp -rp /usr/share/perl5/. $PERL_PREFIX/lib/${PERL_VER}/ || true

# Vendor modules
[ -d /usr/lib64/perl5/vendor_perl ] && \
    cp -rp /usr/lib64/perl5/vendor_perl/. $PERL_PREFIX/lib/${PERL_VER}/ || true
[ -d /usr/share/perl5/vendor_perl ] && \
    cp -rp /usr/share/perl5/vendor_perl/. $PERL_PREFIX/lib/${PERL_VER}/ || true

# site_perl
mkdir -p $PERL_PREFIX/lib/site_perl
[ -d /usr/local/lib64/perl5 ] && cp -rp /usr/local/lib64/perl5/. $PERL_PREFIX/lib/site_perl/ || true
[ -d /usr/local/share/perl5 ] && cp -rp /usr/local/share/perl5/. $PERL_PREFIX/lib/site_perl/ || true

# Copy libcrypt into Perl CORE dir (reference does this)
CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
if [ -n "$CORE_DIR" ] && [ -d "$CORE_DIR" ]; then
    cp -a /usr/lib64/libcrypt.so* "$CORE_DIR/" 2>/dev/null || true
    cp -a /usr/lib64/libxcrypt.so* "$CORE_DIR/" 2>/dev/null || true
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

# Copy libtcl shared lib
cp -a /usr/lib64/libtcl${TCL_VER}.so $TCL_PREFIX/lib/ 2>/dev/null || true
cp -a /usr/lib64/libtclstub${TCL_VER}.a $TCL_PREFIX/lib/ 2>/dev/null || true

# Tcl library directories (stdlib is in /usr/share/tclX.Y/, arch files in /usr/lib64/tclX.Y/)
mkdir -p $TCL_PREFIX/lib/tcl${TCL_VER}
[ -d /usr/share/tcl${TCL_VER} ] && cp -rp /usr/share/tcl${TCL_VER}/. $TCL_PREFIX/lib/tcl${TCL_VER}/ || true
[ -d /usr/lib64/tcl${TCL_VER} ] && cp -rp /usr/lib64/tcl${TCL_VER}/. $TCL_PREFIX/lib/tcl${TCL_VER}/ 2>/dev/null || true
cp -rp /usr/lib64/tcl8 $TCL_PREFIX/lib/ 2>/dev/null || true

# Tcl extension packages
for ext in /usr/lib64/itcl* /usr/lib64/tdbc* /usr/lib64/thread* /usr/lib64/sqlite*; do
    [ -e "$ext" ] && cp -rp "$ext" $TCL_PREFIX/lib/ || true
done

# tclConfig.sh
cp /usr/lib64/tclConfig.sh $TCL_PREFIX/lib/ 2>/dev/null || true
cp /usr/lib64/tclooConfig.sh $TCL_PREFIX/lib/ 2>/dev/null || true

# pkgconfig
mkdir -p $TCL_PREFIX/lib/pkgconfig
cp /usr/lib64/pkgconfig/tcl.pc $TCL_PREFIX/lib/pkgconfig/ 2>/dev/null || true

# include/
mkdir -p $TCL_PREFIX/include
cp /usr/include/tcl*.h $TCL_PREFIX/include/ 2>/dev/null || true
cp /usr/include/tclDecls.h $TCL_PREFIX/include/ 2>/dev/null || true

# man pages
mkdir -p $TCL_PREFIX/man/man1 $TCL_PREFIX/man/man3 $TCL_PREFIX/man/mann
cp /usr/share/man/man1/tclsh*.1* $TCL_PREFIX/man/man1/ 2>/dev/null || true
cp /usr/share/man/man3/Tcl*.3* $TCL_PREFIX/man/man3/ 2>/dev/null || true
cp /usr/share/man/mann/*.n* $TCL_PREFIX/man/mann/ 2>/dev/null || true

# sqlite3_analyzer (Tcl-based SQLite analysis tool)
for f in /usr/bin/sqlite3_analyzer /usr/lib64/sqlite3_analyzer \
          /usr/lib64/sqlite3/sqlite3_analyzer; do
    [ -f "$f" ] && cp "$f" $TCL_PREFIX/bin/ && break || true
done

###############################################################
# 12. Fix Perl, Tcl, Python for portable execution
###############################################################

# --- Perl ---
# libperl.so.X.Y.Z lives in /usr/lib64, not inside perl5/ tree; copy into CORE
CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
if [ -n "$CORE_DIR" ]; then
    # Copy only the real file (not symlinks) from /usr/lib64
    LIBPERL_REAL_PATH=$(find /usr/lib64 -maxdepth 1 -name "libperl.so.*" -not -type l | head -1)
    LIBPERL_REAL=$(basename "$LIBPERL_REAL_PATH")
    cp -p "$LIBPERL_REAL_PATH" "$CORE_DIR/"
    # Recreate SONAME symlink and unversioned symlink pointing to real file
    ln -sf "$LIBPERL_REAL" "$CORE_DIR/libperl.so.${PERL_VER%.*}"  # e.g. libperl.so.5.32
    ln -sf "$LIBPERL_REAL" "$CORE_DIR/libperl.so"
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
# The RPM python3 binary has sys.prefix=/usr hardcoded; wrap it with PYTHONHOME
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
              /opt/percona-pgpool-II /opt/percona-pgbackrest \
              $PYTHON_PREFIX; do
    bundle_deps "$prefix"
    patch_rpath "$prefix"
done
# Note: etcd (Go static), pgbadger (Perl script), patroni (Python) -- no bundling needed
# Note: percona-perl and percona-tcl are NOT in the loop — their RPATHs were set above

# Bundle OpenSSL into percona-python3 explicitly.
# _hashlib.cpython-*.so is compiled against the build env's OpenSSL (3.4+) which may
# be newer than what's on the target system. Bundling ensures Python works portably.
for f in /usr/lib64/libssl.so.3* /usr/lib64/libcrypto.so.3*; do
    [ -f "$f" ] && cp -pn "$f" $PYTHON_PREFIX/lib/ 2>/dev/null || true
done

###############################################################
# 14. Fix PostgreSQL RPATH to include language runtime paths
###############################################################
# Find the actual CORE directory path dynamically
PERL_CORE_DIR=$(find $PERL_PREFIX -name "CORE" -type d | head -1)
PERL_CORE_REL=${PERL_CORE_DIR#/opt/}  # e.g., percona-perl/lib/5.32.1/CORE
LANG_RPATH='$ORIGIN/../lib:/opt/percona-python3/lib:/opt/'"${PERL_CORE_REL}"':/opt/percona-tcl/lib'
LANG_RPATH_LIB='$ORIGIN:/opt/percona-python3/lib:/opt/'"${PERL_CORE_REL}"':/opt/percona-tcl/lib'

# Patch postgres and postmaster binaries
for pgbin in postgres postmaster; do
    [ -f "$PG_PREFIX/bin/$pgbin" ] && \
        patchelf --set-rpath "$LANG_RPATH" "$PG_PREFIX/bin/$pgbin" 2>/dev/null || true
done

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
echo "=== Verification: ldd audit ==="
find /opt -type f \( -perm -u+x -o -name '*.so*' \) | while read -r f; do
    file "$f" 2>/dev/null | grep -q ELF || continue
    ldd "$f" 2>/dev/null | grep 'not found' | while read -r line; do
        lib=$(echo "$line" | awk '{print $1}')
        if ! is_system_lib "$lib"; then
            echo "UNRESOLVED: $f -> $line"
        fi
    done
done > /tmp/ldd-audit.txt
if [ -s /tmp/ldd-audit.txt ]; then
    cat /tmp/ldd-audit.txt
    echo "FATAL: unresolved libraries found" >&2
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
# 16. Create tarball of /opt only (skip default simpleimage tar)
###############################################################
cd /opt
tar -czf /.simpleimage.tar.gz *
