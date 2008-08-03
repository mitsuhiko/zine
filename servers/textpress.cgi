#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
    TextPress CGI Runner
    ~~~~~~~~~~~~~~~~~~~~

    Run TextPress as CGI. Requires python 2.5 or python 2.4 with
    the wsgiref module installed.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# path to the TextPress application code.
TEXTPRESS_LIB = '/usr/lib/textpress'

# enable this to enable an internal CGI debugging feature.
CGI_DEBUG = False


# here you can further configure the wsgi app settings but usually you don't
# have to touch them
if CGI_DEBUG:
    import cgitb
    cgitb.enable()

import sys
sys.path.insert(0, TEXTPRESS_LIB)

from textpress import make_app
from wsgiref.handlers import CGIHandler
app = make_app(INSTANCE_FOLDER)

if __name__ == '__main__':
    CGIHandler().run(app)
