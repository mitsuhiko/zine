# -*- coding: utf-8 -*-
"""
    textpress.cache
    ~~~~~~~~~~~~~~~

    This module implements the TextPress caching system.  This is essentially
    a binding to memcached.


    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from time import time
have_memcache = True
try:
    from cmemcache import memcache
except ImportError:
    try:
        import memcache
    except ImportError:
        have_memcache = False


def get_cache(app):
    """
    Return the cache for the application.  This is called during the
    application setup by the application itself.  No need to call that
    afterwards.
    """
    return systems[app.cfg['cache_system']](app)


def all_if_anonymous(timeout=None, cache_key=None):
    """
    Cache the complete response if the user is anonymous for a given timeout
    and the request is `GET` or `HEAD`.
    """
    def decorator(f):
        key = cache_key or 'view_func/%s.%s' % (f.__module__, f.__name__)
        def oncall(request, *args, **kwargs):
            want_cache = False
            if not request.user.is_somebody:
                response = request.app.cache.get(key)
                if response is not None:
                    return response
                want_cache = True
            response = f(request, *args, **kwargs)
            if want_cache:
                response.freeze()
                cache.set(key, response, timeout)
            return response
        oncall.__name__ = f.__name__
        oncall.__module__ = f.__module__
        oncall.__doc__ = f.__doc__
        return oncall
    return decorator


class BaseCache(object):
    """Baseclass for our cache systems."""

    def __init__(self, app):
        self.app = app
        self.default_timeout = app.cfg['cache_timeout']

    def get(self, key):
        return None

    def get_many(self, *keys):
        return [self.get(key) for key in keys]

    def add(self, key, value, timeout=None):
        pass

    def set(self, key, value, timeout=None):
        pass

    def delete(self, key):
        pass


class NullCache(BaseCache):
    """A cache that doesn't cache."""


class SimpleCache(BaseCache):
    """
    Simple memory cache for single process environments.  This class exists
    mainly for the development server and is not 100% thread safe.  It tries
    to use as many atomic operations as possible and no locks for simplicity
    but it could happen under heavy load that keys are added multiple times.
    """

    def __init__(self, app):
        super(SimpleCache, self).__init__(app)
        self._cache = {}
        self._expires = {}
        self._threshold = 500

    def _cull(self):
        now = time()
        for idx, key in enumerate(self._cache.keys()):
            if self._expires.get(key, 0) < now or idx % 3 == 0:
                self.delete(key)

    def get(self, key):
        now = time()
        if self._expires.get(key, 0) > now:
            return self._cache.get(key)

    def set(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        if len(self._cache) > self._threshold:
            self._cull()
        self._cache[key] = value
        self._expires[key] = timeout

    def add(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        if len(self._cache) > self._threshold:
            self._cull()
        self._cache.setdefault(key, value)
        self._expires[key] = time() + timeout

    def delete(self, key):
        self._cache.pop(key, None)
        self._expires.pop(key, None)


class MemcachedCache(BaseCache):
    """A cache that uses memcached as backend."""

    def __init__(self, app):
        super(Memcache, self).__init__(app)
        servers = [x.strip() for x in app.cfg['memcached_servers'].split(',')]
        self._client = memcache.Client(servers)

    def get(self, key):
        return self._client.get(key)

    def get_many(self, *keys):
        return self._client.get_multi(*keys)

    def add(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        self._client.add(key, value, timeout)

    def set(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        self._client.set(key, value, timeout)

    def delete(self, key):
        self._client.delete(key)


#: map the cache systems to strings for the configuration
systems = {
    'null':         NullCache,
    'simple':       SimpleCache,
    'memcached':    MemcachedCache
}
