#!/bin/bash
# percona-pgadmin4 container entrypoint.
#
# Prepares the container environment (secrets, first-run setup, servers.json /
# preferences.json import, TLS validation, OpenShift random-UID tolerance) and
# execs the RPM launcher /usr/bin/percona-pgadmin4-gunicorn, which owns the
# gunicorn command line, PGADMIN_LISTEN_*/GUNICORN_* handling and TLS wiring
# (PGADMIN_ENABLE_TLS=true -> /certs/server.cert + /certs/server.key).
#
# Environment honored here (upstream dpage/pgadmin4 names):
#   PGADMIN_DEFAULT_EMAIL, PGADMIN_DEFAULT_PASSWORD[_FILE]
#   PGADMIN_CONFIG_CONFIG_DATABASE_URI[_FILE]
#   PGADMIN_SERVER_JSON_FILE (default /pgadmin4/servers.json)
#   PGADMIN_PREFERENCES_JSON_FILE (default /pgadmin4/preferences.json)
#   PGADMIN_REPLACE_SERVERS_ON_STARTUP ("True" to re-import with --replace)
#   PGADMIN_ENABLE_TLS ("true"; certs must exist in /certs)
set -euo pipefail

PGADMIN_DIR=/usr/lib/python3.12/site-packages/pgadmin4
SQLITE_PATH="${PGADMIN_CONFIG_SQLITE_PATH:-/var/lib/pgadmin/pgadmin4.db}"

# --- OpenShift random-UID fixup -------------------------------------------
# Under an arbitrary UID (gid 0) there is no passwd entry; some libraries need
# one. /etc/passwd is group-0 writable (image build).
if ! whoami >/dev/null 2>&1; then
    if [ -w /etc/passwd ]; then
        echo "pgadmin:x:$(id -u):0:pgadmin user:/var/lib/pgadmin:/sbin/nologin" >> /etc/passwd
    fi
fi

# --- Docker-secret _FILE variants -----------------------------------------
# file_env VAR: honor VAR_FILE by reading VAR's value from the file; VAR and
# VAR_FILE together are an error (upstream semantics).
file_env() {
    local var="$1" fileVar="$1_FILE" val=""
    if [ -n "${!var:-}" ] && [ -n "${!fileVar:-}" ]; then
        echo "error: both ${var} and ${fileVar} are set (but are exclusive)" >&2
        exit 1
    fi
    if [ -n "${!fileVar:-}" ]; then
        if [ ! -r "${!fileVar}" ]; then
            echo "error: ${fileVar} is set to '${!fileVar}' but the file is not readable" >&2
            exit 1
        fi
        val="$(< "${!fileVar}")"
        export "${var}"="${val}"
        unset "${fileVar}"
    fi
}
file_env PGADMIN_DEFAULT_PASSWORD
file_env PGADMIN_CONFIG_CONFIG_DATABASE_URI

# --- External configuration database --------------------------------------
# When CONFIG_DATABASE_URI points at an existing, initialised external config
# DB, first-run setup must not run (and must not demand DEFAULT_EMAIL).
external_config_db_exists="False"
if [ -n "${PGADMIN_CONFIG_CONFIG_DATABASE_URI:-}" ]; then
    result=$(cd "${PGADMIN_DIR}/pgadmin/utils" && /usr/bin/python3.12 -c "
import os, ast
from check_external_config_db import check_external_config_db
raw = os.environ['PGADMIN_CONFIG_CONFIG_DATABASE_URI']
try:
    uri = ast.literal_eval(raw)
except (ValueError, SyntaxError):
    uri = raw
print(check_external_config_db(uri))
" 2>/dev/null) || true
    if [ -n "${result:-}" ]; then
        external_config_db_exists="${result}"
    fi
fi

# --- First-run setup + one-time imports ------------------------------------
if [ ! -e "${SQLITE_PATH}" ] && [ "${external_config_db_exists}" = "False" ]; then
    if [ -z "${PGADMIN_DEFAULT_EMAIL:-}" ] || [ -z "${PGADMIN_DEFAULT_PASSWORD:-}" ]; then
        echo 'You need to define the PGADMIN_DEFAULT_EMAIL and PGADMIN_DEFAULT_PASSWORD or PGADMIN_DEFAULT_PASSWORD_FILE environment variables.' >&2
        exit 1
    fi

    # Same init the launcher would run; the launcher sees the DB afterwards
    # and skips its own first-run branch (no double-init).
    (cd "${PGADMIN_DIR}" && \
        PGADMIN_SETUP_EMAIL="${PGADMIN_DEFAULT_EMAIL}" \
        PGADMIN_SETUP_PASSWORD="${PGADMIN_DEFAULT_PASSWORD}" \
        /usr/bin/python3.12 setup.py setup-db)

    server_json="${PGADMIN_SERVER_JSON_FILE:-/pgadmin4/servers.json}"
    if [ -f "${server_json}" ]; then
        /usr/bin/pgadmin4-cli load-servers "${server_json}" --user "${PGADMIN_DEFAULT_EMAIL}"
    fi

    prefs_json="${PGADMIN_PREFERENCES_JSON_FILE:-/pgadmin4/preferences.json}"
    if [ -f "${prefs_json}" ]; then
        /usr/bin/pgadmin4-cli set-prefs "${PGADMIN_DEFAULT_EMAIL}" --input-file "${prefs_json}"
    fi
elif [ "${PGADMIN_REPLACE_SERVERS_ON_STARTUP:-}" = "True" ]; then
    server_json="${PGADMIN_SERVER_JSON_FILE:-/pgadmin4/servers.json}"
    if [ -f "${server_json}" ]; then
        /usr/bin/pgadmin4-cli load-servers "${server_json}" --user "${PGADMIN_DEFAULT_EMAIL}" --replace
    fi
fi

# --- TLS pre-flight ---------------------------------------------------------
# The launcher wires the certs; fail early and clearly when they are missing.
if [ "${PGADMIN_ENABLE_TLS:-}" = "true" ]; then
    if [ ! -r /certs/server.cert ] || [ ! -r /certs/server.key ]; then
        echo 'PGADMIN_ENABLE_TLS is set but /certs/server.cert and/or /certs/server.key are missing or unreadable.' >&2
        exit 1
    fi
fi

exec /usr/bin/percona-pgadmin4-gunicorn
