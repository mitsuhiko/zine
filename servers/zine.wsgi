"""Zine mod_wsgi runner template."""

import os
import sys


# Set this to the writable Zine instance directory.
INSTANCE_FOLDER = os.environ.get("ZINE_INSTANCE", "/path/to/instance/folder")

# Installed packages normally need no path adjustment. Set ZINE_LIB only when
# loading Zine from a non-standard location.
ZINE_LIB = os.environ.get("ZINE_LIB")

POOL_SIZE = None
POOL_RECYCLE = None
POOL_TIMEOUT = None
BEHIND_PROXY = None

if ZINE_LIB and ZINE_LIB not in sys.path:
    sys.path.insert(0, ZINE_LIB)

from zine import get_wsgi_app, override_environ_config

override_environ_config(POOL_SIZE, POOL_RECYCLE, POOL_TIMEOUT, BEHIND_PROXY)
application = get_wsgi_app(INSTANCE_FOLDER)
