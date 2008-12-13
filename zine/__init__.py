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
    :license: GNU GPL.
"""
__version__ = '0.1 alpha'
__url__ = 'http://zine.pocoo.org/'


from zine._core import setup, get_wsgi_app
__all__ = ('setup', 'get_wsgi_app')
