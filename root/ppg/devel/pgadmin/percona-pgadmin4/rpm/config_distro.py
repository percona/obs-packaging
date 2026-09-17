# Distribution configuration for percona-pgadmin4 (server mode).
#
# Precedence (lowest to highest): config.py (upstream defaults) < this file <
# config_local.py < /etc/pgadmin/config_system.py.  Container images and unit
# files override any setting through the environment: every PGADMIN_CONFIG_<NAME>
# variable becomes the setting <NAME>; the value is parsed as a Python literal
# (numbers, True/False/None, quoted strings, lists, dicts) and kept as a plain
# string when it is not one — the same contract as the upstream container image.
import ast
import os

SERVER_MODE = True
MINIFY_HTML = False
UPGRADE_CHECK_ENABLED = False
HELP_PATH = '/usr/share/doc/percona-pgadmin4/en_US'
LOG_FILE = '/var/log/pgadmin/pgadmin4.log'
SQLITE_PATH = '/var/lib/pgadmin/pgadmin4.db'
SESSION_DB_PATH = '/var/lib/pgadmin/sessions'
STORAGE_DIR = '/var/lib/pgadmin/storage'
AZURE_CREDENTIAL_CACHE_DIR = '/var/lib/pgadmin/azurecredentialcache'
KERBEROS_CCACHE_DIR = '/var/lib/pgadmin/krbccache'
DEFAULT_BINARY_PATHS = {
    "pg": "/usr/pgsql-18/bin",
    "pg-13": "/usr/pgsql-13/bin",
    "pg-14": "/usr/pgsql-14/bin",
    "pg-15": "/usr/pgsql-15/bin",
    "pg-16": "/usr/pgsql-16/bin",
    "pg-17": "/usr/pgsql-17/bin",
    "pg-18": "/usr/pgsql-18/bin",
}


def _apply_env_overrides():
    """Apply every PGADMIN_CONFIG_<NAME> environment variable as setting <NAME>.

    Kept in a function (rather than bare module-level statements) so that no
    loop variable is ever left unbound: with zero matching variables the
    ``for`` body never executes and there is nothing to clean up, so the
    module always imports successfully.
    """
    prefix = 'PGADMIN_CONFIG_'
    for key, value in os.environ.items():
        if not key.startswith(prefix) or len(key) == len(prefix):
            continue
        literal = {'true': 'True', 'false': 'False'}.get(value.strip().lower(), value)
        try:
            globals()[key[len(prefix):]] = ast.literal_eval(literal)
        except (ValueError, SyntaxError):
            globals()[key[len(prefix):]] = value


_apply_env_overrides()
del _apply_env_overrides
