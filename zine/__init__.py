# -*- coding: utf-8 -*-
"""
    zine
    ~~~~

    Zine is a simple python weblog software.


    Get a WSGI Application
    ======================

    To get the WSGI application for Zine you can use the `make_app`
    function.  This function can either create a dispatcher for one instance
    or for multiple application instances where the current active instance
    is looked up in the WSGI environment.  The latter is useful for mass
    hosting via mod_wsgi or similar interfaces.

    Here a small example `zine.wsgi` for mod_wsgi::

        from zine import get_wsgi_app
        application = get_wsgi_app('/path/to/instance')


    :copyright: 2007-2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
__version__ = '0.1.2-dev'
__url__ = 'http://zine.pocoo.org/'


# implementation detail.  Stuff in __all__ and the initial import has to be
# the same.  Everything that is not listed in `__all__` or everything that
# does not start with two leading underscores is wiped out on reload and
# the core module is *not* reloaded, thus stuff will get lost if it's not
# properly listed.
from zine._core import setup, get_wsgi_app
__all__ = ('setup', 'get_wsgi_app')
