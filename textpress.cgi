#!/usr/bin/python
"""
    TextPress CGI Runner
    ~~~~~~~~~~~~~~~~~~~~

    Run TextPress as CGI. Requires python 2.5 or python 2.4 with
    the wsgiref module installed.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# here you can further configure the wsgi app settings but usually you don't
# have to touch them
from textpress import make_app
from wsgiref.handlers import CGIHandler
app = make_app(INSTANCE_FOLDER)

if __name__ == '__main__':
    CGIHandler().run(app)
