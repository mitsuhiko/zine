# -*- coding: utf-8 -*-
"""
    textpress
    ~~~~~~~~~

    TextPress is a simple python weblog software.


    Get a WSGI Application
    ======================

    To get the WSGI application for TextPress you can use the `make_app`
    function.  This function can either create a dispatcher for one instance
    or for multiple application instances where the current active instance
    is looked up in the WSGI environment.  The latter is useful for mass
    hosting via mod_wsgi or similar interfaces.

    Here a small example `textpress.wsgi` for mod_wsgi::

        from textpress import make_app
        application = make_app('/path/to/instance')

    If you want to look up the application automatically just don't provide
    an instance path::

        from textpress import make_app
        application = make_app('/path/to/instance')

    In that case it will create a new independent WSGI application when
    requested.  The path to the instance of the TextPress installation for a
    given request must be in the `textpress.instance` key of the WSGI
    environ.  Here an example mod_wsgi configuration for dynamic dispatching::


        RewriteEngine On
        RewriteCond %{REQUEST_URI} ^/([^/]+)
        RewriteRule . - [E=textpress.instance:/var/textpress/%1]
        WSGIScriptAliasMatch ^/([^/]+) /var/textpress.wsgi

    You can create WSGI applications for not yet existing instances too, in
    that case TextPress will display the web setup.


    Getting the TextPress Application
    =================================

    The object returned by `make_app` is a wrapper around the central
    `TextPress` application.  If you want access to this object you can use
    the `make_textpress` function and pass it the path to the instance you
    want control over.  If that instance does not exist it will raise an
    exception however.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
__version__ = '0.1 alpha'
__url__ = 'http://textpress.pocoo.org/'

from textpress.application import make_app, make_textpress
