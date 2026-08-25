#!/bin/bash
#
# tarball-acceptance.sh — acceptance battery for the Percona PostgreSQL
# binary tarballs built by ppg:staging:<V>:tarballs (OBS simpleimage).
#
# It RUNS an already-built artifact; it never builds anything. Give it a
# tarball produced by OBS and it will, for every image of the variant's
# matrix:
#
#   * copy every top-level percona-* component to /opt (the documented
#     install step) inside a MINIMAL container image of a distro the variant
#     promises to support,
#   * create a non-root user, start a bare `postgres -D <datadir>` from an
#     EMPTY environment (env -i) after an env -i initdb,
#   * assert the compiled /tmp socket default (and that /run/postgresql is
#     never created),
#   * CREATE EXTENSION every single .control file shipped in
#     share/extension/, restarting once with shared_preload_libraries for
#     the extensions that need it,
#   * run the PostGIS/GDAL/PROJ deep checks, the three PLs, psql in both
#     pipe and pty mode, and every bundled client/tool with zero env,
#
# plus host-side ELF checks on the extracted tree (psql must link libedit
# and never libreadline; every NEEDED soname must resolve inside the
# artifact except the documented universal host baseline).
#
# The ONLY packages the battery may install into an image are the artifact's
# two DOCUMENTED host prerequisites:
#
#   * tzdata — the RPMs are built --with-system-tzdata, so initdb needs
#     /usr/share/zoneinfo;
#   * the distro's own OpenSSL runtime of the variant's generation (libssl3 /
#     libssl1.1 / openssl-libs) — libssl/libcrypto are deliberately NOT
#     bundled, which is exactly what the ssl1.1/ssl3 label means, and some
#     minimal images (debian:12-slim, ubuntu:20.04) ship no OpenSSL at all.
#     With --no-install such an image is reported NO-OPENSSL and skipped
#     instead.
#
# No user is created by installing anything (a passwd line is appended if the
# image has no useradd), and NOTHING else may ever be installed — not
# readline, libtirpc, expat, pcre2, gdal, proj, python, perl or tcl. If a
# check needs a tool the image lacks (readelf), the check is done on the HOST
# side against the extracted tarball instead.
#
# Exit status is non-zero if ANY check fails on ANY image.
#
# Usage:
#   tools/tarball-acceptance.sh percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz
#   tools/tarball-acceptance.sh <tarball> --images debian:12-slim,ubuntu:24.04
#   tools/tarball-acceptance.sh <tarball> --host-only
#
set -u

PROG=${0##*/}

usage() {
    cat <<EOF
Usage: $PROG <tarball.tar.gz> [options]

Options:
  --images LIST      Comma-separated container images to test, overriding the
                     per-variant default matrix (see --list-images).
  --engine ENGINE    podman | docker (default: podman if present, else docker).
  --workdir DIR      Where to extract and keep logs (default: a mktemp dir).
  --only-extensions  Run only server start + the extension sweep (skip the
                     PostGIS deep checks, the PLs, psql and the clients).
  --host-only        Run only the host-side ELF/inventory checks, no containers.
  --no-install       Install nothing at all in the images: an image without
                     tzdata or without an OpenSSL of the variant's generation
                     is reported and skipped instead.
  --host-timeout N   Wall-clock budget in seconds for the in-container battery
                     of ONE image (default 1200, or $TARBALL_ACCEPTANCE_HOST_TIMEOUT).
                     A host that exceeds it is reported as timed out; the run
                     continues with the next image.
  --keep             Keep the workdir and the containers on exit.
  --list-images      Print the default matrix for both variants and exit.
  -h, --help         This text.

The SSL variant is derived from the tarball file name (-ssl1.1- / -ssl3-);
it selects the default image matrix.
EOF
}

# ---------------------------------------------------------------------------
# Default image matrix per variant.
#
# ssl1.1 targets glibc >= 2.28 / OpenSSL 1.1 hosts, ssl3 glibc >= 2.34 /
# OpenSSL 3.x hosts, so each list is the oldest and newest host generation of
# that promise. -slim / -minimal on purpose: the QA findings this battery
# exists for were all "library absent from a minimal image".
# ---------------------------------------------------------------------------
IMAGES_SSL11="debian:11-slim ubuntu:20.04"
IMAGES_SSL3="debian:12-slim ubuntu:22.04 ubuntu:24.04 docker.io/rockylinux/rockylinux:9-minimal docker.io/rockylinux/rockylinux:10-minimal"

# ---------------------------------------------------------------------------
# Universal host baseline — copied VERBATIM from build-tarball.sh's
# SYSTEM_LIBS_EXCLUDE (27 tokens). These are the only sonames a bundled ELF
# may resolve from the host; everything else must be inside the artifact.
# The script prefers the builder's own list when it can reach it (see
# load_baseline) so the two can never drift; this copy is the fallback for
# running the battery outside a checkout.
# ---------------------------------------------------------------------------
BASELINE_FALLBACK="
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

# Sonames that were on the builder's exclude list before the 2026-07 QA round
# and must now always be BUNDLED. Copied verbatim from build-tarball.sh's
# FORMERLY_EXCLUDED_LIBS (read live from the builder when reachable, see
# load_baseline). These get the STRICT per-component reachability rule, the
# same asymmetry the builder has: everything else only has to be bundled
# somewhere in the artifact, because RUNPATHs legitimately point across
# components (plperl.so -> percona-perl's CORE dir, plpython3.so ->
# percona-python3/lib, pltcl.so -> percona-tcl/lib).
FORMERLY_EXCLUDED_FALLBACK="
libtirpc.so
libnsl.so
libeconf.so
libpcre2-8.so
libpcre2-posix.so
libexpat.so
libreadline.so
"

# The 13 top-level components of the artifact, as gated by build-tarball.sh's
# component-inventory check. percona-postgresql<major> is templated.
EXPECTED_COMPONENTS="
percona-etcd
percona-gdal
percona-haproxy
percona-patroni
percona-perl
percona-pgbackrest
percona-pgbadger
percona-pgbouncer
percona-pgpool-II
percona-postgresql@MAJOR@
percona-proj
percona-python3
percona-tcl
"

TARBALL=""
IMAGES=""
ENGINE=""
WORKDIR=""
ONLY_EXTENSIONS=0
HOST_ONLY=0
KEEP=0
INSTALL_OK=1
HOST_TIMEOUT=${TARBALL_ACCEPTANCE_HOST_TIMEOUT:-1200}

while [ $# -gt 0 ]; do
    case "$1" in
        --images)     IMAGES=$(echo "${2:?--images needs a value}" | tr ',' ' '); shift 2 ;;
        --engine)     ENGINE=${2:?--engine needs a value}; shift 2 ;;
        --workdir)    WORKDIR=${2:?--workdir needs a value}; shift 2 ;;
        --only-extensions) ONLY_EXTENSIONS=1; shift ;;
        --host-only)  HOST_ONLY=1; shift ;;
        --no-install) INSTALL_OK=0; shift ;;
        --host-timeout) HOST_TIMEOUT=${2:?--host-timeout needs a value}; shift 2 ;;
        --keep)       KEEP=1; shift ;;
        --list-images)
            echo "ssl1.1: $(echo "$IMAGES_SSL11" | tr ' ' ',')"
            echo "ssl3:   $(echo "$IMAGES_SSL3" | tr ' ' ',')"
            exit 0 ;;
        -h|--help)    usage; exit 0 ;;
        -*)           echo "$PROG: unknown option $1" >&2; usage >&2; exit 2 ;;
        *)
            [ -z "$TARBALL" ] || { echo "$PROG: only one tarball may be given" >&2; exit 2; }
            TARBALL=$1; shift ;;
    esac
done

[ -n "$TARBALL" ] || { usage >&2; exit 2; }
[ -f "$TARBALL" ] || { echo "$PROG: no such file: $TARBALL" >&2; exit 2; }
TARBALL=$(cd "$(dirname "$TARBALL")" && pwd)/$(basename "$TARBALL")

# Variant from the file name — the artifact name is built from it in
# build-tarball.sh section 16.
case "$(basename "$TARBALL")" in
    *-ssl1.1-*) VARIANT=ssl1.1 ;;
    *-ssl3-*)   VARIANT=ssl3 ;;
    *) echo "$PROG: cannot derive the SSL variant from $(basename "$TARBALL")" >&2
       echo "       expected ...-ssl1.1-... or ...-ssl3-... in the name" >&2
       exit 2 ;;
esac

if [ -z "$IMAGES" ]; then
    case "$VARIANT" in
        ssl1.1) IMAGES=$IMAGES_SSL11 ;;
        ssl3)   IMAGES=$IMAGES_SSL3 ;;
    esac
fi

if [ "$HOST_ONLY" -eq 0 ]; then
    if [ -z "$ENGINE" ]; then
        for e in podman docker; do
            command -v "$e" >/dev/null 2>&1 && { ENGINE=$e; break; }
        done
    fi
    [ -n "$ENGINE" ] || { echo "$PROG: neither podman nor docker found (use --host-only)" >&2; exit 2; }
    command -v "$ENGINE" >/dev/null 2>&1 || { echo "$PROG: $ENGINE not found" >&2; exit 2; }
fi

# timeout(1) bounds the whole per-image battery. Absent (or a variant that
# does not take "timeout SECS CMD"), the run is unbounded — say so rather than
# pretending otherwise.
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1 && timeout 5 true >/dev/null 2>&1; then
    TIMEOUT_BIN=$(command -v timeout)
fi

if [ -z "$WORKDIR" ]; then
    WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/tarball-acceptance.XXXXXX")
    OWN_WORKDIR=1
else
    mkdir -p "$WORKDIR"
    OWN_WORKDIR=0
fi
EXTRACT=$WORKDIR/extract
CONTAINERS=$WORKDIR/containers.list
: > "$CONTAINERS"

cleanup() {
    if [ -s "$CONTAINERS" ] && [ "$KEEP" -eq 0 ]; then
        while read -r c; do
            [ -n "$c" ] || continue
            "$ENGINE" rm -f "$c" >/dev/null 2>&1
        done < "$CONTAINERS"
    fi
    if [ "$KEEP" -eq 0 ] && [ "$OWN_WORKDIR" -eq 1 ]; then
        rm -rf "$WORKDIR"
    else
        echo "workdir kept: $WORKDIR"
    fi
}
trap cleanup EXIT INT TERM

FAILURES=0
SKIPPED=0
note_fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL: $*"; }
hdr() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
hdr "Extracting $(basename "$TARBALL") ($VARIANT)"
mkdir -p "$EXTRACT"
tar -xzf "$TARBALL" -C "$EXTRACT" || { echo "$PROG: extraction failed" >&2; exit 1; }
PG_COMPONENT=$(cd "$EXTRACT" && ls -d percona-postgresql[0-9]* 2>/dev/null | head -1)
[ -n "$PG_COMPONENT" ] || { echo "$PROG: no percona-postgresql<major> component in the tarball" >&2; exit 1; }
PG_MAJOR=${PG_COMPONENT#percona-postgresql}
echo "PostgreSQL component: $PG_COMPONENT (major $PG_MAJOR)"

# ---------------------------------------------------------------------------
# Host-side check 1: component inventory (13 components)
# ---------------------------------------------------------------------------
hdr "Host check: component inventory"
echo "$EXPECTED_COMPONENTS" | sed "s/@MAJOR@/$PG_MAJOR/" | grep -v '^$' | LC_ALL=C sort > "$WORKDIR/expected-components.txt"
(cd "$EXTRACT" && ls) | LC_ALL=C sort > "$WORKDIR/actual-components.txt"
if diff -u "$WORKDIR/expected-components.txt" "$WORKDIR/actual-components.txt"; then
    echo "  OK: 13 components"
    RES_COMPONENTS="OK 13/13"
else
    n=$(wc -l < "$WORKDIR/actual-components.txt")
    note_fail "component set differs from the expected 13 (found $n)"
    RES_COMPONENTS="FAIL $n/13"
fi

# ---------------------------------------------------------------------------
# Host-side check 2: psql link audit
#
# Mirrors build-tarball.sh's "psql link audit": bin/psql must be the
# percona-psql (libedit) build. readelf is done here, on the host, precisely
# so the battery does not have to install binutils into a minimal image.
# ---------------------------------------------------------------------------
hdr "Host check: psql link audit"
PSQL_BIN=$EXTRACT/$PG_COMPONENT/bin/psql
RES_PSQL_LINK=OK
if [ ! -e "$PSQL_BIN" ]; then
    note_fail "$PG_COMPONENT/bin/psql missing"
    RES_PSQL_LINK=FAIL
elif ! command -v readelf >/dev/null 2>&1; then
    echo "  SKIP: readelf not available on the host"
    RES_PSQL_LINK=SKIP
else
    needed=$(readelf -d "$PSQL_BIN" 2>/dev/null | sed -n 's/.*NEEDED.*\[\(.*\)\].*/\1/p')
    if [ -z "$needed" ]; then
        note_fail "bin/psql is not an ELF binary (a wrapper script? the readline wrapper is supposed to be gone)"
        RES_PSQL_LINK=FAIL
    else
        echo "  NEEDED: $(echo "$needed" | tr '\n' ' ')"
        case "$needed" in
            *libreadline*) note_fail "bin/psql links libreadline — it must be the libedit percona-psql build"
                           RES_PSQL_LINK=FAIL ;;
        esac
        case "$needed" in
            *libedit.so.0*) ;;
            *) note_fail "bin/psql does not need libedit.so.0"; RES_PSQL_LINK=FAIL ;;
        esac
    fi
fi
if [ -e "$EXTRACT/$PG_COMPONENT/bin/psql.bin" ]; then
    note_fail "bin/psql.bin present — the host-readline wrapper machinery is supposed to be gone"
    RES_PSQL_LINK=FAIL
fi

# ---------------------------------------------------------------------------
# Host-side check 3: NEEDED-soname closure against the universal baseline
#
# Same two-tier contract as build-tarball.sh section 15. An ELF may resolve a
# soname from the host only if it is on the universal baseline. Otherwise:
#
#   * artifact-wide rule (default): the soname must be bundled SOMEWHERE in
#     the tarball. Cross-component RUNPATHs are legitimate and deliberate —
#     builder section 14 points plperl.so at /opt/percona-perl/lib/<ver>/CORE,
#     plpython3.so at /opt/percona-python3/lib and pltcl.so at
#     /opt/percona-tcl/lib, and libperl/libpython3.12/libtcl8.6 live only in
#     those components.
#   * strict per-component rule, for the FORMERLY_EXCLUDED sonames only: those
#     must sit in the NEEDing ELF's own component lib/ or next to the ELF,
#     because that is all its RUNPATH can reach. A copy in another component
#     would reproduce QA finding 1 one component over, so it is reported as
#     MISPLACED.
# ---------------------------------------------------------------------------
load_baseline() {
    # Prefer the builder's own list, so the two literally cannot drift.
    local here builder
    here=$(cd "$(dirname "$0")" && pwd)
    builder=$here/../root/ppg/staging/$PG_MAJOR/tarballs/percona-postgresql-tarball/obs/build-tarball.sh
    if [ -r "$builder" ]; then
        BASELINE=$(sed -n '/^SYSTEM_LIBS_EXCLUDE="$/,/^"$/p' "$builder" | sed '1d;$d')
        FORMERLY_EXCLUDED=$(sed -n '/^FORMERLY_EXCLUDED_LIBS="$/,/^"$/p' "$builder" | sed '1d;$d')
        if [ -n "$BASELINE" ] && [ -n "$FORMERLY_EXCLUDED" ]; then
            BASELINE_SRC="build-tarball.sh"
            return
        fi
    fi
    BASELINE=$BASELINE_FALLBACK
    FORMERLY_EXCLUDED=$FORMERLY_EXCLUDED_FALLBACK
    BASELINE_SRC="embedded copy"
}
load_baseline

is_baseline() {
    local libname=$1 pattern
    for pattern in $BASELINE; do
        case "$libname" in ${pattern}*) return 0 ;; esac
    done
    return 1
}

is_formerly_excluded() {
    local libname=$1 pattern
    for pattern in $FORMERLY_EXCLUDED; do
        case "$libname" in ${pattern}*) return 0 ;; esac
    done
    return 1
}

hdr "Host check: NEEDED-soname closure (baseline from $BASELINE_SRC)"
RES_NEEDED=OK
if ! command -v readelf >/dev/null 2>&1; then
    echo "  SKIP: readelf not available on the host"
    RES_NEEDED=SKIP
else
    find "$EXTRACT" -name '*.so*' -xtype f -printf '%f\n' | LC_ALL=C sort -u > "$WORKDIR/bundled-sonames.txt"
    : > "$WORKDIR/needed-audit.txt"
    find "$EXTRACT" -type f \( -perm -u+x -o -name '*.so*' \) -print | while read -r f; do
        rel=${f#"$EXTRACT"/}
        comp=${rel%%/*}
        comp_lib=$EXTRACT/$comp/lib
        own_dir=$(dirname "$f")
        readelf -d "$f" 2>/dev/null | sed -n 's/.*NEEDED.*\[\(.*\)\].*/\1/p' | while read -r soname; do
            is_baseline "$soname" && continue
            if is_formerly_excluded "$soname"; then
                [ -e "$comp_lib/$soname" ] && continue
                [ -e "$own_dir/$soname" ] && continue
                if grep -qxF "$soname" "$WORKDIR/bundled-sonames.txt"; then
                    echo "MISPLACED: $rel needs $soname — in the artifact but not in this component's lib/ nor next to the ELF, so its RUNPATH cannot reach it"
                else
                    echo "UNRESOLVED: $rel needs $soname — not bundled and not on the universal host baseline"
                fi
                continue
            fi
            grep -qxF "$soname" "$WORKDIR/bundled-sonames.txt" && continue
            echo "UNRESOLVED: $rel needs $soname — not bundled and not on the universal host baseline"
        done
    done > "$WORKDIR/needed-audit.txt"
    if [ -s "$WORKDIR/needed-audit.txt" ]; then
        sed 's/^/  /' "$WORKDIR/needed-audit.txt" | LC_ALL=C sort -u | head -40
        n=$(LC_ALL=C sort -u "$WORKDIR/needed-audit.txt" | wc -l)
        note_fail "$n unresolved/misplaced NEEDED soname(s) — full list in $WORKDIR/needed-audit.txt"
        RES_NEEDED="FAIL($n)"
    else
        echo "  OK: every NEEDED soname is bundled per component or on the universal baseline"
    fi
fi

# ---------------------------------------------------------------------------
# Host-side check 4: surplus dependency chain
#
# Same list as build-tarball.sh's "surplus dependency-chain audit". These
# libraries have no business in a PostgreSQL tarball; their presence means a
# fat dependency chain (EPEL's fully-optioned gdal-libs, historically) crept
# in. libflexiblas is the one that made this a runtime bug rather than mere
# bloat: its ELF CONSTRUCTOR abort()s when its dlopen'ed BLAS backend plugin
# is absent, i.e. on every host that is not the buildroot — QA finding 2.
# ---------------------------------------------------------------------------
SURPLUS_LIBS="libflexiblas libarmadillo libhdf libdf libmfhdf libnetcdf libdap
libpoppler libmariadb libodbc libkml libxerces libarpack libsuperlu"
hdr "Host check: surplus dependency chain"
: > "$WORKDIR/surplus-audit.txt"
for bad in $SURPLUS_LIBS; do
    find "$EXTRACT" -name "${bad}*" -printf '%P\n' >> "$WORKDIR/surplus-audit.txt"
done
if [ -s "$WORKDIR/surplus-audit.txt" ]; then
    sed 's/^/  SURPLUS: /' "$WORKDIR/surplus-audit.txt" | head -30
    n=$(wc -l < "$WORKDIR/surplus-audit.txt")
    note_fail "$n surplus library file(s) in the artifact (full list in $WORKDIR/surplus-audit.txt)"
    RES_SURPLUS="FAIL($n)"
else
    echo "  OK: none of the surplus libraries is present"
    RES_SURPLUS=OK
fi

if [ "$HOST_ONLY" -eq 1 ]; then
    echo
    echo "host-only run: components=$RES_COMPONENTS psql-link=$RES_PSQL_LINK needed=$RES_NEEDED surplus=$RES_SURPLUS"
    [ "$FAILURES" -eq 0 ] && { echo "HOST CHECKS PASSED"; exit 0; }
    echo "HOST CHECKS FAILED ($FAILURES)"
    exit 1
fi

# ---------------------------------------------------------------------------
# The guest battery — everything that must run ON the target host.
# Written out verbatim (quoted heredoc); it derives all paths itself and
# needs no environment.
# ---------------------------------------------------------------------------
GUEST=$WORKDIR/guest-battery.sh
cat > "$GUEST" <<'GUEST_EOF'
#!/bin/bash
# Runs INSIDE the target image as a non-root user. Emits
#   RESULT|<key>|<PASS|FAIL|SKIP>|<detail>
#   FAILURE|<key>|<name>|<detail>
# lines that the host side parses into the final matrix.
set -u

ONLY_EXTENSIONS=${1:-0}

OPT=/opt
PGROOT=$(ls -d "$OPT"/percona-postgresql[0-9]* 2>/dev/null | head -1)
BIN=$PGROOT/bin
WORK=/var/tmp/acceptance-$(id -u)
DATA=$WORK/data
LOG=$WORK/server.log
rm -rf "$WORK"; mkdir -p "$WORK"

result()  { echo "RESULT|$1|$2|$3"; }
failure() { echo "FAILURE|$1|$2|$3"; }
say()     { echo "-- $*"; }

# Per-step timeouts: one wedged client must not hang the battery. timeout(1)
# is coreutils and present on every target image (verified on debian 11/12-slim,
# ubuntu 20.04 and rockylinux 9-minimal), but check that the plain
# "timeout SECS CMD" form works rather than assuming the variant.
TMO=""
if command -v timeout >/dev/null 2>&1 && timeout 5 true >/dev/null 2>&1; then
    TMO=$(command -v timeout)
else
    echo "-- NOTE: no usable timeout(1) in this image — per-step timeouts disabled"
fi
tmo() {
    local secs=$1; shift
    if [ -n "$TMO" ]; then "$TMO" "$secs" "$@"; else "$@"; fi
}

# Every invocation of a bundled binary goes through env -i: the artifact's
# zero-environment promise is the thing under test.
pg() { local c=$1; shift; tmo 120 env -i "$BIN/$c" "$@"; }

SRV=""
start_server() {
    env -i "$BIN/postgres" -D "$DATA" "$@" >> "$LOG" 2>&1 &
    SRV=$!
    local waited=0
    while [ "$waited" -lt 90 ]; do
        waited=$((waited + 1))
        if env -i "$BIN/pg_isready" -q >/dev/null 2>&1; then return 0; fi
        kill -0 "$SRV" 2>/dev/null || return 1
        sleep 1
    done
    return 1
}
stop_server() {
    [ -n "$SRV" ] || return 0
    kill "$SRV" 2>/dev/null
    wait "$SRV" 2>/dev/null
    SRV=""
}
server_alive() { env -i "$BIN/pg_isready" -q >/dev/null 2>&1; }
crash_evidence() {
    grep -E 'terminated by signal|flexiblas|Abort|PANIC' "$LOG" 2>/dev/null \
        | tail -2 | tr '\n' ' ' | cut -c1-300
}

say "artifact: $PGROOT"
say "components: $(cd "$OPT" && ls | tr '\n' ' ')"
say "user: $(id)"

# --- initdb + bare server start, from an empty environment ----------------
if ! tmo 300 env -i "$BIN/initdb" -D "$DATA" -A trust > "$WORK/initdb.log" 2>&1; then
    result server FAIL "initdb failed: $(tail -3 "$WORK/initdb.log" | tr '\n' ' ' | cut -c1-300)"
    failure server initdb "$(tail -5 "$WORK/initdb.log" | tr '\n' ' ')"
    exit 1
fi
if ! start_server; then
    result server FAIL "postgres did not become ready: $(tail -5 "$LOG" | tr '\n' ' ' | cut -c1-300)"
    failure server startup "$(tail -10 "$LOG" | tr '\n' ' ')"
    exit 1
fi

# Compiled socket default: /tmp, never /run/postgresql. Both asserted.
SOCK_OK=1
if [ ! -S /tmp/.s.PGSQL.5432 ]; then
    SOCK_OK=0
    failure server socket "no /tmp/.s.PGSQL.5432 — the compiled socket default is not /tmp"
fi
if [ -e /run/postgresql ]; then
    SOCK_OK=0
    failure server run-postgresql "/run/postgresql exists — the artifact must never need it"
fi
if [ "$SOCK_OK" -eq 1 ]; then
    result server PASS "initdb+postgres via env -i, socket in /tmp, no /run/postgresql"
else
    result server FAIL "socket/dir assertions failed"
fi

# --- extension sweep: every shipped .control -------------------------------
# Extensions that legitimately need shared_preload_libraries. Anything else
# asking for a preload is reported as a failure rather than silently loaded.
PRELOAD_ALLOW="pg_tde pg_stat_monitor pg_cron pgaudit percona_pg_telemetry set_user"

EXT_TOTAL=0
EXT_OK=0
EXT_DEFERRED=""
EXT_FAILED=""
# Set as soon as a failure turns out to be psql itself failing to start (no
# host readline for the old wrapper build, say). Every check in this script
# drives the server through psql, so without this one broken client would
# print 76 identical failures.
PSQL_BROKEN=0

# try_ext <name> [may_defer]
#   may_defer=1 (pass 1) classifies a failure of a preload-needing extension
#   as NEEDS-PRELOAD; in pass 2 (may_defer=0) the real error is reported.
try_ext() {
    local name=$1 may_defer=${2:-1} db=acc_ext out rc
    # -f: a preloaded pg_cron keeps a background-worker connection open to
    # its cron.database_name, which a plain dropdb refuses to work around.
    pg dropdb --if-exists -f "$db" >/dev/null 2>&1
    if ! out=$(pg createdb "$db" 2>&1); then
        echo "createdb-failed: $out"
        return 1
    fi
    out=$(tmo 180 env -i "$BIN/psql" -X -q -d "$db" -v ON_ERROR_STOP=1 \
              -c "CREATE EXTENSION \"$name\" CASCADE" 2>&1) && rc=0 || rc=$?
    if [ "$rc" -eq 124 ]; then
        echo "TIMEOUT: CREATE EXTENSION did not finish within 180s"
        return 1
    fi
    if [ "$rc" -eq 0 ]; then
        return 0
    fi
    # plpgsql is installed in template1 by initdb, so "already exists" is a
    # pass, not a failure.
    case "$out" in
        *"already exists"*) return 0 ;;
    esac
    # A dead/recovering server means the backend crashed (the FlexiBLAS
    # constructor abort() is exactly this). Only CLASSIFY it here — this
    # function runs in a command substitution, so a restart done here would
    # leave the parent's server PID stale; the caller restarts.
    if ! server_alive; then
        echo "BACKEND-CRASH: $(echo "$out" | tr '\n' ' ' | cut -c1-200) [log: $(crash_evidence)]"
        return 1
    fi
    # Extensions that need shared_preload_libraries do not all say so:
    # pg_tde reports "can only be loaded at server startup", pg_cron reports
    # an unrecognized cron.* GUC. So every allowlisted extension gets the
    # preload retry, and so does anything whose message names the setting.
    if [ "$may_defer" = "1" ]; then
        for a in $PRELOAD_ALLOW; do
            if [ "$a" = "$name" ]; then echo "NEEDS-PRELOAD"; return 1; fi
        done
        case "$out" in
            *shared_preload_libraries*) echo "NEEDS-PRELOAD" ; return 1 ;;
        esac
    fi
    echo "$out" | tr '\n' ' ' | cut -c1-300
    return 1
}

for ctl in "$PGROOT"/share/extension/*.control; do
    [ -f "$ctl" ] || continue
    name=$(basename "$ctl" .control)
    EXT_TOTAL=$((EXT_TOTAL + 1))
    if detail=$(try_ext "$name"); then
        EXT_OK=$((EXT_OK + 1))
    else
        case "$detail" in
            NEEDS-PRELOAD) EXT_DEFERRED="$EXT_DEFERRED $name" ;;
            *"bin/psql"*"error while loading shared libraries"*)
                EXT_FAILED="$EXT_FAILED $name"
                if [ "$PSQL_BROKEN" = "0" ]; then
                    PSQL_BROKEN=1
                    failure extension "$name" "$detail"
                    failure extensions ALL-BLOCKED "psql itself cannot start on this host — the whole sweep is blocked; see the psql check"
                fi ;;
            *) EXT_FAILED="$EXT_FAILED $name"; failure extension "$name" "$detail" ;;
        esac
        # A crashed backend takes the whole server down for a moment; bring
        # it back (in THIS shell, so $SRV stays valid) and keep sweeping.
        server_alive || { stop_server; start_server >/dev/null 2>&1 || true; }
    fi
done

# Second pass for the preload-requiring extensions: one restart with a
# preload list assembled from the allowlist.
if [ -n "$EXT_DEFERRED" ] && [ "$PSQL_BROKEN" = "1" ]; then
    for name in $EXT_DEFERRED; do EXT_FAILED="$EXT_FAILED $name"; done
    EXT_DEFERRED=""
fi
if [ -n "$EXT_DEFERRED" ]; then
    preload=""
    for name in $EXT_DEFERRED; do
        allowed=0
        for a in $PRELOAD_ALLOW; do [ "$a" = "$name" ] && allowed=1; done
        if [ "$allowed" -eq 1 ]; then
            preload="${preload:+$preload,}$name"
        else
            EXT_FAILED="$EXT_FAILED $name"
            failure extension "$name" "requires shared_preload_libraries but is not on the battery's preload allowlist"
        fi
    done
    if [ -n "$preload" ]; then
        # pg_cron refuses to be created outside the database named by
        # cron.database_name, so point that at the sweep's database.
        EXTRA_GUC=""
        case ",$preload," in
            *,pg_cron,*) EXTRA_GUC="-c cron.database_name=acc_ext" ;;
        esac
        say "restarting with shared_preload_libraries=$preload $EXTRA_GUC"
        stop_server
        # shellcheck disable=SC2086  # EXTRA_GUC is a deliberate word list
        if start_server -c "shared_preload_libraries=$preload" $EXTRA_GUC; then
            for name in $EXT_DEFERRED; do
                case ",$preload," in *",$name,"*) ;; *) continue ;; esac
                if detail=$(try_ext "$name" 0); then
                    EXT_OK=$((EXT_OK + 1))
                else
                    EXT_FAILED="$EXT_FAILED $name"
                    failure extension "$name" "with preload: $detail"
                    # shellcheck disable=SC2086
                    server_alive || { stop_server; start_server -c "shared_preload_libraries=$preload" $EXTRA_GUC >/dev/null 2>&1 || true; }
                fi
            done
        else
            for name in $EXT_DEFERRED; do
                EXT_FAILED="$EXT_FAILED $name"
                failure extension "$name" "server would not start with shared_preload_libraries=$preload: $(tail -3 "$LOG" | tr '\n' ' ')"
            done
            start_server >/dev/null 2>&1 || true
        fi
    fi
fi

if [ "$PSQL_BROKEN" = "1" ]; then
    result extensions FAIL "$EXT_OK/$EXT_TOTAL (blocked: psql cannot start on this host)"
elif [ -n "$EXT_FAILED" ]; then
    result extensions FAIL "$EXT_OK/$EXT_TOTAL (failed:$EXT_FAILED)"
else
    result extensions PASS "$EXT_OK/$EXT_TOTAL"
fi

if [ "$ONLY_EXTENSIONS" = "1" ]; then
    stop_server
    exit 0
fi

# --- PostGIS / GDAL / PROJ deep checks -------------------------------------
q() { tmo 180 env -i "$BIN/psql" -X -q -A -t -d "$1" -v ON_ERROR_STOP=1 -c "$2" 2>&1; }

GIS_DB=acc_gis
pg dropdb --if-exists -f "$GIS_DB" >/dev/null 2>&1
if ! pg createdb "$GIS_DB" >/dev/null 2>&1; then
    result postgis FAIL "createdb $GIS_DB failed"
elif ! out=$(q "$GIS_DB" "CREATE EXTENSION postgis CASCADE; CREATE EXTENSION postgis_raster CASCADE;"); then
    result postgis FAIL "CREATE EXTENSION postgis/postgis_raster failed: $(echo "$out" | tr '\n' ' ' | cut -c1-250)"
    failure postgis create "$out"
    server_alive || { stop_server; start_server >/dev/null 2>&1 || true; }
else
    gis_fail=""
    gis_warn=""
    full=$(q "$GIS_DB" "SELECT postgis_full_version();")
    # PostGIS only appends the "DATABASE_PATH=" suffix to the PROJ version it
    # reports above a PROJ version floor (it comes from proj_context_get_
    # database_path(), PROJ >= 7). ssl1.1 links PROJ 6.3.2, so the suffix is
    # legitimately absent there — that is a WARN, not a failure. What is NOT
    # acceptable is the suffix naming some OTHER proj.db: that means PostGIS
    # found a distro PROJ database instead of the bundled one.
    case "$full" in
        *"DATABASE_PATH=/opt/percona-proj/share/proj/proj.db"*)
            ;;
        *DATABASE_PATH=*)
            gis_fail="$gis_fail full_version-proj-db"
            failure postgis proj-db "postgis_full_version() reports a DATABASE_PATH outside /opt/percona-proj: $full" ;;
        *)
            gis_warn="$gis_warn no-proj-db-path"
            say "NOTE: postgis_full_version() prints no DATABASE_PATH= (PROJ too old to report it) — ST_Transform below is the proj.db proof" ;;
    esac
    case "$full" in
        *GDAL*) ;;
        *) gis_fail="$gis_fail full_version-gdal"
           failure postgis gdal "postgis_full_version() does not mention GDAL: $full" ;;
    esac
    case "$full" in
        *PROJ*) ;;
        *) gis_fail="$gis_fail full_version-proj"
           failure postgis proj "postgis_full_version() does not mention PROJ: $full" ;;
    esac

    # Known 3857 coordinates of (1,1) in EPSG:4326.
    xy=$(q "$GIS_DB" "SELECT round(ST_X(g)::numeric,3) || ' ' || round(ST_Y(g)::numeric,3) FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(1,1),4326),3857) AS g) t;")
    if [ "$xy" != "111319.491 111325.143" ]; then
        gis_fail="$gis_fail st_transform"
        failure postgis st_transform "expected '111319.491 111325.143', got '$xy'"
    fi

    # Raster: the module whose missing libs (libtirpc/libexpat/libpcre2-posix)
    # were QA finding 1.
    rast=$(q "$GIS_DB" "SELECT ST_AsText(ST_Envelope(ST_AddBand(ST_MakeEmptyRaster(10,10,0,0,1,-1,0,0,4326),'8BUI'::text,1,0)));")
    case "$rast" in
        POLYGON*) ;;
        *) gis_fail="$gis_fail raster"
           failure postgis raster "ST_AddBand/ST_Envelope did not return a polygon: $(echo "$rast" | tr '\n' ' ' | cut -c1-250)" ;;
    esac
    server_alive || { stop_server; start_server >/dev/null 2>&1 || true; }

    gdalv=$(q "$GIS_DB" "SELECT postgis_gdal_version();")
    case "$gdalv" in
        *"GDAL_DATA not found"*)
            gis_fail="$gis_fail gdal_data"
            failure postgis gdal_data "postgis_gdal_version() reports GDAL_DATA not found: $gdalv" ;;
        "") gis_fail="$gis_fail gdal_version"
            failure postgis gdal_version "postgis_gdal_version() returned nothing" ;;
    esac

    if [ -n "$gis_fail" ]; then
        result postgis FAIL "$gis_fail"
    elif [ -n "$gis_warn" ]; then
        result postgis PASS "full_version+ST_Transform+raster+GDAL_DATA (warn:$gis_warn)"
    else
        result postgis PASS "full_version+ST_Transform+raster+GDAL_DATA"
    fi
fi

# --- the three PLs, zero env ----------------------------------------------
PL_DB=acc_pl
pl_fail=""
pg dropdb --if-exists -f "$PL_DB" >/dev/null 2>&1
if ! pg createdb "$PL_DB" >/dev/null 2>&1; then
    pl_fail="createdb"
else
    for pl in plperl plpython3u pltcl; do
        case "$pl" in
            plperl)     body="DO \$\$ elog(NOTICE, 'plperl ok'); \$\$ LANGUAGE plperl;" ;;
            plpython3u) body="DO \$\$ plpy.notice('plpython3u ok') \$\$ LANGUAGE plpython3u;" ;;
            # PL/Tcl has no inline (DO) handler, so it is exercised through a
            # real function instead.
            pltcl)      body="CREATE FUNCTION acc_pltcl() RETURNS text AS \$\$ return \"pltcl ok\" \$\$ LANGUAGE pltcl; SELECT acc_pltcl();" ;;
        esac
        if ! out=$(q "$PL_DB" "CREATE EXTENSION IF NOT EXISTS $pl; $body"); then
            pl_fail="$pl_fail $pl"
            failure pls "$pl" "$(echo "$out" | tr '\n' ' ' | cut -c1-250)"
            server_alive || { stop_server; start_server >/dev/null 2>&1 || true; }
        fi
    done
fi
if [ -n "$pl_fail" ]; then
    result pls FAIL "failed:$pl_fail"
else
    result pls PASS "plperl+plpython3u+pltcl DO blocks"
fi

# --- psql: pipe mode and pty (interactive) mode, no host readline ---------
psql_fail=""
if ! out=$(echo '\conninfo' | tmo 60 env -i "$BIN/psql" -X -d postgres 2>&1) || \
   ! echo "$out" | grep -q 'You are connected'; then
    psql_fail="$psql_fail pipe"
    failure psql pipe "$(echo "$out" | tr '\n' ' ' | cut -c1-250)"
fi
# A pty is what makes psql initialise its line editor; this is the check that
# proves libedit works with NO readline installed on the host — precisely the
# thing rockylinux:*-minimal (util-linux-core, i.e. no script(1)) most needs
# proving. So when script(1) is missing, fall back to a pty driven by the
# artifact's OWN bundled python (host python3 is absent from minimal images
# too), and only degrade the cell if that fails as well.
PTY_MODE=""
pty_run() {
    # The query is 41+1, not 42, on purpose: a pty echoes whatever is written
    # to it, so the *input* line comes back in the captured output too. Only
    # the computed "42" proves psql actually ran the statement through its
    # interactive line editor.
    printf '\\conninfo\nSELECT 41+1 AS pty_check;\n\\q\n' | tmo 90 "$@" 2>&1
}
pty_ran() { echo "$1" | tr -d '\r' | grep -qE '^[[:space:]]*42[[:space:]]*$'; }
PY_BUNDLED=$OPT/percona-python3/bin/python3
if command -v script >/dev/null 2>&1; then
    PTY_MODE="script"
    out=$(pty_run env -i TERM=xterm script -q -c "$BIN/psql -X -P pager=off -d postgres" /dev/null)
elif [ -x "$PY_BUNDLED" ]; then
    PTY_MODE="bundled-python"
    # Feeds stdin through a real pty and echoes everything psql writes back.
    cat > "$WORK/pty_psql.py" <<'PYEOF'
import os, pty, select, sys, time
argv = sys.argv[1:]
data = sys.stdin.buffer.read()
pid, fd = pty.fork()
if pid == 0:
    os.environ.clear()
    os.environ["TERM"] = "xterm"
    os.execv(argv[0], argv)
os.write(fd, data)
out = b""
deadline = time.time() + 60
while time.time() < deadline:
    try:
        r = select.select([fd], [], [], 1)[0]
    except OSError:
        break
    if r:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    else:
        try:
            if os.waitpid(pid, os.WNOHANG)[0]:
                break
        except ChildProcessError:
            break
try:
    os.waitpid(pid, 0)
except (ChildProcessError, OSError):
    pass
sys.stdout.buffer.write(out)
PYEOF
    say "NOTE: 'script' absent from this image — driving the pty with the artifact's own python3"
    out=$(pty_run env -i "$PY_BUNDLED" "$WORK/pty_psql.py" \
              "$BIN/psql" -X -P pager=off -d postgres)
else
    PTY_MODE="none"
    out=""
    say "NOTE: no pty driver in this image (no script(1), no bundled python3) — interactive psql check skipped"
fi
case "$PTY_MODE" in
    none)
        psql_fail="$psql_fail pty-skipped" ;;
    *)
        if ! pty_ran "$out"; then
            psql_fail="$psql_fail pty"
            failure psql pty "interactive psql under a pty ($PTY_MODE) did not run the query: $(echo "$out" | tr '\n' ' ' | cut -c1-250)"
        fi ;;
esac
if [ -n "$psql_fail" ]; then
    case "$psql_fail" in
        # "PASS*" (not plain PASS) so the matrix cell itself says the pty leg
        # of this check never ran; the host side prints the legend line.
        " pty-skipped") result psql "PASS*" "pipe mode OK (no pty driver available in this image)" ;;
        *) result psql FAIL "failed:$psql_fail" ;;
    esac
else
    result psql PASS "pipe + pty ($PTY_MODE), no host readline"
fi

# --- bundled clients and tools, zero env ---------------------------------
cl_fail=""
check() {
    local label=$1; shift
    local out
    if ! out=$(tmo 300 env -i "$@" 2>&1); then
        cl_fail="$cl_fail $label"
        failure clients "$label" "$(echo "$out" | tr '\n' ' ' | cut -c1-250)"
    fi
}
check pg_isready   "$BIN/pg_isready"
pg dropdb --if-exists -f acc_bench >/dev/null 2>&1
pg createdb acc_bench >/dev/null 2>&1
check pgbench      "$BIN/pgbench" -q -i -s 1 acc_bench
check patronictl   "$OPT/percona-patroni/bin/patronictl" --help
check haproxy      "$OPT/percona-haproxy/sbin/haproxy" -v
check pgbackrest   "$OPT/percona-pgbackrest/bin/pgbackrest" version
check pgbouncer    "$OPT/percona-pgbouncer/bin/pgbouncer" --version
check pgpool       "$OPT/percona-pgpool-II/bin/pgpool" --version
check etcd         "$OPT/percona-etcd/bin/etcd" --version
check pgbadger     "$OPT/percona-perl/bin/perl" "$OPT/percona-pgbadger/pgbadger" --version
if [ ! -f "$PGROOT/bin/gather.sql" ]; then
    cl_fail="$cl_fail pg_gather"
    failure clients pg_gather "bin/gather.sql (pg_gather) missing from the artifact"
fi
if [ -n "$cl_fail" ]; then
    result clients FAIL "failed:$cl_fail"
else
    result clients PASS "libpq+patroni+haproxy+pgbackrest+pgbouncer+pgpool+etcd+pgbadger+pg_gather"
fi

# Final re-assertion: nothing in the whole run may have created it.
if [ -e /run/postgresql ]; then
    failure server run-postgresql "/run/postgresql was created during the run"
    result runpg FAIL "created during the run"
else
    result runpg PASS "never created"
fi

stop_server
exit 0
GUEST_EOF
chmod 0755 "$GUEST"

# Root-side setup inside the image: tzdata (the ONLY package this battery may
# install), a non-root user, and the documented /opt copy step.
SETUP=$WORKDIR/guest-setup.sh
cat > "$SETUP" <<'SETUP_EOF'
#!/bin/sh
# $1 = ssl variant (ssl1.1|ssl3), $2 = 1 if the two documented host
# prerequisites (tzdata, the distro OpenSSL runtime) may be installed.
set -u
VARIANT=${1:?variant}
INSTALL_OK=${2:-1}

pkg_install() {
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
    elif command -v microdnf >/dev/null 2>&1; then
        microdnf -y --nodocs install "$@"
    elif command -v dnf >/dev/null 2>&1; then
        dnf -y --setopt=install_weak_deps=False install "$@"
    elif command -v yum >/dev/null 2>&1; then
        yum -y install "$@"
    else
        echo "-- WARNING: no package manager in this image"
        return 1
    fi
}

# tzdata: the RPMs are built --with-system-tzdata, so initdb needs
# /usr/share/zoneinfo.
if [ ! -d /usr/share/zoneinfo ]; then
    if [ "$INSTALL_OK" = "1" ]; then
        echo "-- installing tzdata (absent from this image)"
        pkg_install tzdata || true
    else
        echo "-- NOTE: no /usr/share/zoneinfo and --no-install given"
    fi
fi
[ -d /usr/share/zoneinfo ] || echo "-- WARNING: still no /usr/share/zoneinfo"

# OpenSSL: libssl/libcrypto are deliberately host-provided — that is exactly
# what the ssl1.1/ssl3 variant label promises — so an image with no OpenSSL at
# all (debian:12-slim, ubuntu:20.04) is not a host of the promised class.
# Install the distro's own runtime of the right generation, or report
# NO-OPENSSL so the host side can skip the image instead of blaming the
# artifact.
case "$VARIANT" in
    ssl1.1) SSL_SONAME=libssl.so.1.1; DEB_SSL_PKG=libssl1.1 ;;
    *)      SSL_SONAME=libssl.so.3;   DEB_SSL_PKG=libssl3 ;;
esac
have_ssl() {
    for d in /usr/lib64 /lib64 /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu /usr/lib /lib; do
        [ -e "$d/$SSL_SONAME" ] && return 0
    done
    return 1
}
SSL_ATTEMPTED=0
if ! have_ssl; then
    if [ "$INSTALL_OK" = "1" ]; then
        echo "-- installing the distro OpenSSL runtime ($SSL_SONAME absent from this image)"
        SSL_ATTEMPTED=1
        if command -v apt-get >/dev/null 2>&1; then
            pkg_install "$DEB_SSL_PKG" || true
        else
            pkg_install openssl-libs || true
        fi
    fi
fi
# Three distinct outcomes, because "the image ships none" and "the install
# failed" (no network, no repo metadata) need different verdicts: the first is
# a skip, the second is a failure of this host, not a silent loss of coverage.
if have_ssl; then
    echo "ACC_OPENSSL=present"
elif [ "$SSL_ATTEMPTED" = "1" ]; then
    echo "ACC_OPENSSL=missing-after-install-attempt"
else
    echo "ACC_OPENSSL=missing-install-disabled"
fi

# A non-root OS user to run the server (the documented prerequisite). No
# package is installed for this: if useradd is missing, a passwd line is
# appended by hand.
ACC_USER=pgacceptance
if ! id "$ACC_USER" >/dev/null 2>&1; then
    if command -v useradd >/dev/null 2>&1; then
        useradd -m "$ACC_USER" >/dev/null 2>&1 || useradd "$ACC_USER" >/dev/null 2>&1
    fi
fi
if ! id "$ACC_USER" >/dev/null 2>&1; then
    uid=4242
    echo "$ACC_USER:x:$uid:0::/home/$ACC_USER:/bin/sh" >> /etc/passwd
    mkdir -p "/home/$ACC_USER"
fi
ACC_UID=$(id -u "$ACC_USER")
mkdir -p "/home/$ACC_USER"
chown "$ACC_UID" "/home/$ACC_USER" 2>/dev/null || true

# The documented install step: copy EVERY top-level percona-* component
# to /opt. Nothing else is done to the image.
mkdir -p /opt
cp -a /src/percona-* /opt/ || { echo "-- FATAL: /opt copy failed"; exit 1; }
echo "-- /opt: $(ls /opt | tr '\n' ' ')"
[ -e /run/postgresql ] && echo "-- WARNING: /run/postgresql exists in the base image"
echo "ACC_UID=$ACC_UID"
SETUP_EOF
chmod 0755 "$SETUP"

# ---------------------------------------------------------------------------
# Run the battery per image
# ---------------------------------------------------------------------------
MATRIX=$WORKDIR/matrix.txt
: > "$MATRIX"

run_image() {
    local image=$1
    local safe cid uid rc log
    safe=$(echo "$image" | tr '/:.' '___')
    log=$WORKDIR/log-$safe.txt
    hdr "Image: $image"

    if ! "$ENGINE" image exists "$image" >/dev/null 2>&1 && \
       ! "$ENGINE" image inspect "$image" >/dev/null 2>&1; then
        echo "  pulling $image"
        if ! "$ENGINE" pull -q "$image" >/dev/null 2>&1; then
            note_fail "$image: pull failed"
            echo "$image|PULL-FAIL|-|-|-|-|-" >> "$MATRIX"
            return 1
        fi
    fi

    cid=acceptance-$safe-$$
    if ! "$ENGINE" run -d --name "$cid" \
            -v "$EXTRACT:/src:ro,z" "$image" sleep infinity >/dev/null 2>&1; then
        note_fail "$image: container would not start"
        echo "$image|RUN-FAIL|-|-|-|-|-" >> "$MATRIX"
        return 1
    fi
    echo "$cid" >> "$CONTAINERS"

    "$ENGINE" cp "$SETUP" "$cid:/setup.sh" >/dev/null 2>&1
    "$ENGINE" cp "$GUEST" "$cid:/battery.sh" >/dev/null 2>&1

    : > "$log"
    "$ENGINE" exec "$cid" /bin/sh /setup.sh "$VARIANT" "$INSTALL_OK" > "$WORKDIR/setup-$safe.out" 2>&1
    rc=$?
    tee -a "$log" < "$WORKDIR/setup-$safe.out"
    if [ "$rc" -ne 0 ]; then
        note_fail "$image: setup failed (see $log)"
        echo "$image|SETUP-FAIL|-|-|-|-|-" >> "$MATRIX"
        return 1
    fi
    uid=$(sed -n 's/^ACC_UID=//p' "$log" | tail -1)
    [ -n "$uid" ] || uid=4242

    # An image with no OpenSSL of the variant's generation is not a host of
    # the class the variant label promises: skip it loudly rather than
    # reporting an artifact failure. An OpenSSL install that was ATTEMPTED and
    # failed is a different thing — an environment problem that must not pass
    # as a skip.
    if grep -q '^ACC_OPENSSL=missing-install-disabled' "$log"; then
        echo "  SKIP: this image ships no OpenSSL for $VARIANT and installing it is disabled"
        echo "$image|NO-OPENSSL|-|-|-|-|-" >> "$MATRIX"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi
    if grep -q '^ACC_OPENSSL=missing-after-install-attempt' "$log"; then
        note_fail "$image: installing the distro OpenSSL runtime failed (no network? no repo metadata?) — see $log"
        echo "$image|SSL-INSTALL-FAIL|-|-|-|-|-" >> "$MATRIX"
        return 1
    fi

    local guest_rc=0
    if [ -n "$TIMEOUT_BIN" ]; then
        "$TIMEOUT_BIN" "$HOST_TIMEOUT" \
            "$ENGINE" exec --user "$uid:0" "$cid" /bin/bash /battery.sh "$ONLY_EXTENSIONS" \
            > "$WORKDIR/guest-$safe.out" 2>&1 || guest_rc=$?
    else
        echo "  NOTE: no usable timeout(1) on this host — the battery runs unbounded"
        "$ENGINE" exec --user "$uid:0" "$cid" /bin/bash /battery.sh "$ONLY_EXTENSIONS" \
            > "$WORKDIR/guest-$safe.out" 2>&1 || guest_rc=$?
    fi
    tee -a "$log" < "$WORKDIR/guest-$safe.out"
    if [ "$guest_rc" -eq 124 ]; then
        note_fail "$image: the battery exceeded the ${HOST_TIMEOUT}s host budget and was killed (--host-timeout)"
    fi

    # Parse the guest's RESULT/FAILURE lines.
    local row="" key
    for key in server psql extensions postgis pls clients; do
        local line status detail
        line=$(grep "^RESULT|$key|" "$log" | tail -1)
        if [ -z "$line" ]; then
            if [ "$ONLY_EXTENSIONS" = "1" ] && [ "$key" != server ] && [ "$key" != extensions ]; then
                status="-"
            else
                status="MISSING"
            fi
            detail=""
        else
            status=$(echo "$line" | cut -d'|' -f3)
            detail=$(echo "$line" | cut -d'|' -f4)
        fi
        case "$key" in
            extensions) row="$row|$status ${detail%% *}" ;;
            *)          row="$row|$status" ;;
        esac
        case "$status" in
            FAIL|MISSING) note_fail "$image: $key $status ${detail}" ;;
        esac
    done
    echo "$image$row" >> "$MATRIX"

    if grep -q '^FAILURE|' "$log"; then
        echo
        echo "  failures on $image (by name):"
        grep '^FAILURE|' "$log" | head -25 | while IFS='|' read -r _ k n d; do
            printf '    %-11s %-28s %s\n' "$k" "$n" "$(echo "$d" | cut -c1-140)"
        done
        nf=$(grep -c '^FAILURE|' "$log")
        [ "$nf" -le 25 ] || echo "    ... and $((nf - 25)) more (see $log)"
    fi

    if [ "$KEEP" -eq 0 ]; then
        "$ENGINE" rm -f "$cid" >/dev/null 2>&1
        grep -v "^$cid$" "$CONTAINERS" > "$CONTAINERS.tmp" 2>/dev/null || :
        mv "$CONTAINERS.tmp" "$CONTAINERS" 2>/dev/null || :
    fi
}

IMAGE_COUNT=0
for image in $IMAGES; do
    IMAGE_COUNT=$((IMAGE_COUNT + 1))
    run_image "$image"
done

# ---------------------------------------------------------------------------
# Final matrix
# ---------------------------------------------------------------------------
hdr "Acceptance matrix — $(basename "$TARBALL") ($VARIANT)"
printf '%-46s %-9s %-9s %-13s %-9s %-9s %-9s\n' HOST SERVER PSQL EXTENSIONS POSTGIS PLs CLIENTS
while IFS='|' read -r h server psql ext gis pls clients; do
    printf '%-46s %-9s %-9s %-13s %-9s %-9s %-9s\n' \
        "$h" "$server" "$psql" "$ext" "$gis" "$pls" "$clients"
done < "$MATRIX"
# A "PASS*" cell is a pass whose pty leg could not be exercised (see the
# guest battery's psql section): neither script(1) nor the artifact's bundled
# python3 was usable as a pty driver on that image.
if grep -q 'PASS\*' "$MATRIX"; then
    echo "  * pty check unavailable on this image (no script(1) and no usable bundled python3 pty driver)"
fi
echo
echo "host checks: components=$RES_COMPONENTS psql-link=$RES_PSQL_LINK needed=$RES_NEEDED surplus=$RES_SURPLUS"
echo "logs: $WORKDIR"

[ "$SKIPPED" -eq 0 ] || echo "images skipped (no host OpenSSL of this variant): $SKIPPED"
if [ "$FAILURES" -ne 0 ]; then
    echo "ACCEPTANCE FAILED ($FAILURES failing check(s))"
    exit 1
fi
# Nothing failed — but a run in which no image was actually exercised has
# proved nothing about the artifact on a host, so it is not a pass.
if [ "$IMAGE_COUNT" -gt 0 ] && [ "$SKIPPED" -eq "$IMAGE_COUNT" ]; then
    echo "ACCEPTANCE INCOMPLETE (all $IMAGE_COUNT image(s) skipped — no host was exercised; host-side checks passed)"
    exit 3
fi
if [ "$SKIPPED" -eq 0 ]; then
    echo "ACCEPTANCE PASSED"
else
    echo "ACCEPTANCE PASSED ($SKIPPED of $IMAGE_COUNT image(s) skipped)"
fi
exit 0
