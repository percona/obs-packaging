# WSGI entry point for gunicorn: `gunicorn … run_pgadmin:app`.
# Mirrors upstream's container run_pgadmin.py; the app module is pgAdmin4.py
# in this directory, which builds the Flask application on import.
import builtins
import os
import sys

# Set SERVER_MODE explicitly for the builtin check performed by config.py.
builtins.SERVER_MODE = True

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from pgAdmin4 import app  # noqa: E402,F401
