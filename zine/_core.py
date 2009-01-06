# -*- coding: utf-8 -*-
"""
    zine._core
    ~~~~~~~~~~

    Internal core module that survives reloads.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import os
from thread import allocate_lock
from time import time, sleep

_setup_lock = allocate_lock()

#: the initialized application
_application = None


class InstanceNotInitialized(RuntimeError):
    """Raised if an application was created for a not yet initialized
    instance folder.
    """


def _create_zine(instance_folder, timeout=5, in_reloader=True):
    """Creates a new Zine object and initialized it.  This is also aware of
    ongoing reloads.  If funky things occur and these do not resolve
    after `timeout` seconds a `RuntimeError` is raised.
    """
    global _application
    _setup_lock.acquire()
    try:
        if _application is not None:
            return _application

        if not in_reloader:
            from zine.application import Zine as cls
        else:
            started = time()
            while 1:
                try:
                    from zine.application import Zine as cls
                except ImportError:
                    cls = None
                if cls is not None:
                    break
                if time() > started + timeout:
                    raise RuntimeError('timed out while waiting for '
                                       'reload to finish.')
                sleep(0.05)

        _application = app = object.__new__(cls)
        try:
            app.__init__(instance_folder)
        except InstanceNotInitialized:
            _application = None
            raise
        return app
    finally:
        _setup_lock.release()


def _unload_zine():
    """Unload all zine libraries."""
    global _application
    import sys

    _setup_lock.acquire()
    try:
        _application = None

        for name, module in sys.modules.items():
            # in the main module delete everything but the stuff
            # that we want to have there.  Also make sure that
            # zine._core (which python internally imports) is not
            # removed.
            if name == 'zine':
                preserve = set(module.__all__) | set(['_core'])
                for key, value in module.__dict__.items():
                    if key not in preserve and not key.startswith('__'):
                        module.__dict__.pop(key, None)
            elif name.startswith('zine.') and name != 'zine._core':
                # get rid of the module
                sys.modules.pop(name, None)
                # zero out the dict
                try:
                    for key, value in module.__dict__.iteritems():
                        setattr(module, key, None)
                    value = None
                except:
                    pass
    finally:
        _setup_lock.release()


def setup(instance_folder):
    """Creates a new instance of the application.  This must be called only
    once per interpreter and afterwards (until python shuts down or all
    zine modules are unloaded and the references are deleted) zine is
    created and `get_application` returns the application object.

    The setup function returns the application that was set up.
    """
    if _application is not None:
        raise RuntimeError('application already set up')
    return _create_zine(instance_folder, in_reloader=False)


def get_wsgi_app(instance_folder):
    """This function returns a proxy WSGI application that dispatches to
    Zine or the web setup.  It is however not possible to use this function
    to set up multiple instances of zine in the same python interpreter.

    This function MUST NOT BE CALLED for environments where anything but
    the WSGI server or zine itself work with the zine API.  The reloading
    process depends that only zine controls stuff outside of the internal
    core module.  You have been warned.
    """
    # the reloader eats import errors, so make sure that the application
    # properly before we create our proxy application.
    import zine.application

    _dispatch_lock = allocate_lock()
    def application(environ, start_response):
        _dispatch_lock.acquire()
        try:
            app = _application
            if app is not None and app.wants_reload:
                _unload_zine()
                app = None
            if app is None:
                try:
                    app = _create_zine(instance_folder)
                except InstanceNotInitialized:
                    from zine.websetup import WebSetup
                    app = WebSetup(instance_folder)
        finally:
            _dispatch_lock.release()
        return app(environ, start_response)
    return application


def override_environ_config(pool_size=None, pool_recycle=None,
                            pool_timeout=None, behind_proxy=None):
    """Some configuration parameters are not stored in the zine.ini but
    in the os environment.  These are process wide configuration settings
    used for different deployments.
    """
    for key, value in locals().items():
        if value is not None:
            if key == 'behind_proxy':
                value = int(bool(value))
            os.environ['ZINE_' + key.upper()] = str(value)
