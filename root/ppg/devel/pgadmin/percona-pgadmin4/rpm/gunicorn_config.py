# gunicorn configuration for percona-pgadmin4-gunicorn.
# Log to stdout/stderr (container-friendly); the launcher passes bind/workers/TLS
# on the command line so environment variables stay the single knob.
import logging

logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'generic': {
            'format': '%(asctime)s [%(process)d] [%(levelname)s] %(message)s',
            'datefmt': '[%Y-%m-%d %H:%M:%S %z]',
            'class': 'logging.Formatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': 'ext://sys.stdout',
        },
        'error_console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': 'ext://sys.stderr',
        },
    },
    'loggers': {
        'gunicorn.error': {'level': 'INFO', 'handlers': ['error_console'], 'propagate': False},
        'gunicorn.access': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
    },
    'root': {'level': logging.INFO, 'handlers': ['console']},
}
