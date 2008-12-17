# -*- coding: utf-8 -*-
"""
    Zine mod_wsgi Runner
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Run Zine in mod_wsgi.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD
"""

# path to the instance. the folder for the instance must exist,
# if there is not instance information in that folder the websetup
# will show an assistent
INSTANCE_FOLDER = '/path/to/instance/folder'

# path to the Zine application code.
ZINE_LIB = '/usr/lib/zine'

# here you can further configure the wsgi app settings but usually you don't
# have to touch them
import sys
if ZINE_LIB not in sys.path:
    sys.path.insert(0, ZINE_LIB)

from zine import get_wsgi_app
application = get_wsgi_app(INSTANCE_FOLDER)
