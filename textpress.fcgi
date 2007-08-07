#!/usr/bin/python
"""
    TextPress FastCGI Runner
    ~~~~~~~~~~~~~~~~~~~~~~~~

    If FastCGI is your hosting environment this is the correct file.
    For working FastCGI support you have to have flup installed.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# here you can further configure the fastcgi and wsgi app settings
# but usually you don't have to touch them
from textpress import make_app
from flup.server.fcgi import WSGIServer
srv = WSGIServer(make_app(INSTANCE_FOLDER))

if __name__ == '__main__':
    srv.run()
