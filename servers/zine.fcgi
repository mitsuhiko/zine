#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
    Zine FastCGI Runner
    ~~~~~~~~~~~~~~~~~~~

    If FastCGI is your hosting environment this is the correct file.
    For working FastCGI support you have to have flup installed.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# path to the Zine application code.
ZINE_LIB = '/usr/lib/zine'

# these values can be use to override database pool settings.
# see deployment guide for more details.
POOL_SIZE = None
POOL_RECYCLE = None
POOL_TIMEOUT = None

# ----------------------------------------------------------------------------
# here you can further configure the fastcgi and wsgi app settings
# but usually you don't have to touch them.
import sys
import os

sys.path.insert(0, ZINE_LIB)

for key in 'POOL_SIZE', 'POOL_RECYCLE', 'POOL_TIMEOUT':
    value = locals().get(key)
    if value is not None:
        os.environ['ZINE_DATABASE_' + key] = value

from zine import get_wsgi_app
from flup.server.fcgi import WSGIServer
app = get_wsgi_app(INSTANCE_FOLDER)
srv = WSGIServer(app)

if __name__ == '__main__':
    srv.run()
