#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
    Zine FastCGI Runner
    ~~~~~~~~~~~~~~~~~~~

    If FastCGI is your hosting environment this is the correct file.
    For working FastCGI support you have to have flup installed.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# path to the Zine application code.
ZINE_LIB = '/usr/lib/zine'


# here you can further configure the fastcgi and wsgi app settings
# but usually you don't have to touch them
import sys
sys.path.insert(0, ZINE_LIB)

from zine import make_app
from flup.server.fcgi import WSGIServer
app = make_app(INSTANCE_FOLDER)
srv = WSGIServer(app)

if __name__ == '__main__':
    srv.run()
