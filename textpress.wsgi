"""
    TextPress mod_wsgi Runner
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Run TextPress in mod_wsgi.
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# here you can further configure the wsgi app settings but usually you don't
# have to touch them
from textpress import make_app
application = make_app(INSTANCE_FOLDER)
