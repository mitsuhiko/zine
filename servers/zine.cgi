#!/usr/bin/env python3
"""Zine CGI runner template.

CGI starts the application for every request and is only retained for hosting
environments that provide no persistent WSGI process.
"""

import os
import sys
from wsgiref.handlers import CGIHandler


INSTANCE_FOLDER = os.environ.get("ZINE_INSTANCE", "/path/to/instance/folder")
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

if __name__ == "__main__":
    CGIHandler().run(application)
