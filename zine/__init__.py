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

        from zine import make_app
        application = make_app('/path/to/instance')

    If you want to look up the application automatically just don't provide
    an instance path::

        from zine import make_app
        application = make_app('/path/to/instance')

    In that case it will create a new independent WSGI application when
    requested.  The path to the instance of the Zine installation for a
    given request must be in the `zine.instance` key of the WSGI
    environ.  Here an example mod_wsgi configuration for dynamic dispatching::


        RewriteEngine On
        RewriteCond %{REQUEST_URI} ^/([^/]+)
        RewriteRule . - [E=zine.instance:/var/zine/%1]
        WSGIScriptAliasMatch ^/([^/]+) /var/zine.wsgi

    You can create WSGI applications for not yet existing instances too, in
    that case Zine will display the web setup.


    Getting the Zine Application
    =================================

    The object returned by `make_app` is a wrapper around the central
    `Zine` application.  If you want access to this object you can use
    the `make_zine` function and pass it the path to the instance you
    want control over.  If that instance does not exist it will raise an
    exception however.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
__version__ = '0.1 alpha'
__url__ = 'http://zine.pocoo.org/'

# init the import system by importing it.  at the end of the module
# the import system is hooked into the python import system
import zine.pluginsystem

from zine.application import make_app, make_zine
