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

_PREFIX = 'PGADMIN_CONFIG_'
for _key, _value in os.environ.items():
    if not _key.startswith(_PREFIX) or len(_key) == len(_PREFIX):
        continue
    _literal = {'true': 'True', 'false': 'False'}.get(_value.strip().lower(), _value)
    try:
        globals()[_key[len(_PREFIX):]] = ast.literal_eval(_literal)
    except (ValueError, SyntaxError):
        globals()[_key[len(_PREFIX):]] = _value
del _PREFIX, _key, _value, _literal
