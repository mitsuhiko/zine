# -*- coding: utf-8 -*-
"""
    zine.cache
    ~~~~~~~~~~

    This module implements the Zine caching system.  This is essentially
    a binding to memcached.


    :copyright: Copyright 2007-2008 by Armin Ronacher.
    :license: BSD
"""
import os

from werkzeug.contrib.cache import NullCache, SimpleCache, FileSystemCache, \
     MemcachedCache

from zine.utils import local

try:
    from hashlib import md5
except ImportError:
    from md5 import new as md5


def get_cache(app):
    """Return the cache for the application.  This is called during the
    application setup by the application itself.  No need to call that
    afterwards.
    """
    return systems[app.cfg['cache_system']](app)


def get_cache_context(vary, eager_caching=False, request=None):
    """Returns a tuple in the form ``(request, status)`` where request is a
    request object and status a bool that is `True` if caching should be
    performed.
    """
    request = request or local.request
    return request, not (
        # don't cache if we have the null cache.  in theory the null cache
        # doesn't do anything anyways but if one tests for caching to
        # disable some more expensive caculations in the function we can
        # tell him to not perform anything if the cache won't hold the data
        request.app.cache is NullCache or

        # if this is an eager caching method and eager caching is disabled
        # we don't do anything here
        eager_caching and not request.app.cfg['enable_eager_caching'] or

        # don't perform caching if "user" is in vary and the current
        # active user is not an anonymous user
        ('user' in vary and request.user.is_somebody) or

        # also don't cache if `method` is in "vary" and the current
        # request is not GET / HEAD
        ('method' in vary and request.method not in ('GET', 'HEAD'))
    )


def result(cache_key, vary=(), eager_caching=False, timeout=None,
           admix_arguments=True, skip_posargs=0):
    """Cache the result of the function for a given timeout.  The `vary`
    argument can be used to keep different caches or limit the cache.
    Currently the following `vary` modifiers are available:

    ``'user'``
        cache only for anonymous users

    ``'method'``
        cache only if the current request is a GET or HEAD request.

    if `admix_arguments` is set to `True` the arguments passed to the function
    will be hashed and added to the cache key.  If you set `eager_caching` to
    `True` this method won't do anything if eager caching is disabled.
    """
    def decorator(f):
        def oncall(*args, **kwargs):
            request, want_cache = get_cache_context(vary, eager_caching)

            if want_cache:
                key = cache_key
                if admix_arguments:
                    key += ':%d' % hash((args[skip_posargs:],
                                        frozenset(kwargs.iteritems())))
                result = request.app.cache.get(key)
                if result is not None:
                    return result
            result = f(*args, **kwargs)
            if want_cache:
                request.app.cache.set(key, result, timeout)
            return result

        try:
            oncall.__name__ = f.__name__
            oncall.__doc__ = f.__doc__
            oncall.__module__ = f.__module__
        except AttributeError:
            pass
        return oncall
    return decorator


def response(vary=(), timeout=None, cache_key=None):
    """Cache a complete view function for a number of seconds.  This is a
    little bit different from `result` because it freezes the response
    properly and sets etags.  The current request path is added to the cache
    key to keep them cached properly.  If the response is not 200 no caching
    is performed.

    This method doesn't do anything if eager caching is disabled (by default).
    """
    from zine.application import Response
    if not 'method' in vary:
        vary = set(vary)
        vary.add('method')
    def decorator(f):
        key = cache_key or 'view_func/%s.%s' % (f.__module__, f.__name__)
        def oncall(request, *args, **kwargs):
            use_cache = get_cache_context(vary, True, request)[1]
            response = None
            if use_cache:
                cache_key = key + request.path.encode('utf-8')
                response = request.app.cache.get(key)

            if response is None:
                response = f(request, *args, **kwargs)

            # make sure it's one of our request objects so that we
            # have the `make_conditional` method on it.
            Response.force_type(response)

            if use_cache and response.status_code == 200:
                response.freeze()
                request.app.cache.set(key, response, timeout)
                response.make_conditional(request)
            return response
        oncall.__name__ = f.__name__
        oncall.__module__ = f.__module__
        oncall.__doc__ = f.__doc__
        return oncall
    return decorator


#: the cache system factories.
systems = {
    'null':         lambda app: NullCache(),
    'simple':       lambda app: SimpleCache(app.cfg['cache_timeout']),
    'memcached':    lambda app: MemcachedCache([x.strip() for x in
                        app.cfg['memcached_servers']],
                        app.cfg['cache_timeout']),
    'filesystem':   lambda app: FileSystemCache(
                        os.path.join(app.instance_folder,
                                     app.cfg['filesystem_cache_path']), 500,
                        app.cfg['cache_timeout'])
}
