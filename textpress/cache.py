# -*- coding: utf-8 -*-
"""
    textpress.cache
    ~~~~~~~~~~~~~~~

    This module implements the TextPress caching system.  This is essentially
    a binding to memcached.


    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
try:
    from hashlib import md5
except ImportError:
    from md5 import new as md5
from time import time
from cPickle import loads, dumps, load, dump, HIGHEST_PROTOCOL
have_memcache = True
try:
    from cmemcache import memcache
except ImportError:
    try:
        import memcache
    except ImportError:
        have_memcache = False
from textpress.utils import local


def get_cache(app):
    """
    Return the cache for the application.  This is called during the
    application setup by the application itself.  No need to call that
    afterwards.
    """
    return systems[app.cfg['cache_system']](app)


def get_cache_context(vary, eager_caching=False, request=None):
    """
    Returns a tuple in the form ``(request, status)`` where request is a
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


def make_metaclass(vary=(), cache_key=None, eager_caching=False,
                   timeout=None, admix_arguments=True, parent=type):
    """
    This metaclass factory returns a new type that can be used as metaclass
    for classes that are cached.  If the parent of the class has already a
    metaclass you have to pass this class to the factory function using the
    `parent` keyword argument.
    """
    class CachedClass(parent):
        def __call__(cls, *args, **kwargs):
            if cache_key is None:
                module =  cls.__module__
                if module.startswith('textpress.'):
                    module = module[10:]
                key = 'instance/%s.%s' % (module, cls.__name__)
            else:
                key = cache_key
            return result(key, vary, eager_caching, timeout, admix_arguments,
                          1)(parent.__call__)(cls, *args, **kwargs)
    return CachedClass


def result(cache_key, vary=(), eager_caching=False, timeout=None,
           admix_arguments=True, skip_posargs=0):
    """
    Cache the result of the function for a given timeout.  The `vary` argument
    can be used to keep different caches or limit the cache.  Currently the
    following `vary` modifiers are available:

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
    """
    Cache a complete view function for a number of seconds.  This is a little
    bit different from `result` because it freezes the response properly and
    sets etags.  The current request path is added to the cache key to keep
    them cached properly.  If the response is not 200 no caching is performed.

    This method doesn't do anything if eager caching is disabled (by default).
    """
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

    def _prune(self):
        if len(self._cache) > self._threshold:
            now = time()
            for idx, key in enumerate(self._cache.keys()):
                if self._expires.get(key, 0) <= now or idx % 3 == 0:
                    self.delete(key)

    def get(self, key):
        now = time()
        if self._expires.get(key, 0) > now:
            rv = self._cache.get(key)
            if rv is not None:
                rv = loads(rv)
            return rv

    def set(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        self._prune()
        self._cache[key] = dumps(value, HIGHEST_PROTOCOL)
        self._expires[key] = time() + timeout

    def add(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        if len(self._cache) > self._threshold:
            self._prune()
        self._cache.setdefault(key, dumps(value, HIGHEST_PROTOCOL))
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


class FileSystemCache(BaseCache):
    """A cache that stores the items on the file system."""

    def __init__(self, app):
        super(FileSystemCache, self).__init__(app)
        self._path = os.path.join(app.instance_folder,
                                  app.cfg['filesystem_cache_path'])
        self._threshold = 500
        if not os.path.exists(self._path):
            os.makedirs(self._path)

    def _prune(self):
        entries = os.listdir(self._path)
        if len(entries) > self._threshold:
            now = time()
            for idx, key in enumerate(entries):
                try:
                    f = file(self._get_filename(key))
                    if pickle.load(f) > now and idx % 3 != 0:
                        f.close()
                        continue
                except:
                    f.close()
                self.delete(key)

    def _get_filename(self, key):
        hash = md5(key).hexdigest()
        return os.path.join(self._path, hash)

    def get(self, key):
        filename = self._get_filename(key)
        try:
            f = file(filename, 'rb')
            try:
                if load(f) >= time():
                    return load(f)
            finally:
                f.close()
            os.remove(filename)
        except:
            return None

    def add(self, key, value, timeout=None):
        filename = self._get_filename(key)
        if not os.path.exists(filename):
            self.set(key, value, timeout)

    def set(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        filename = self._get_filename(key)
        self._prune()
        try:
            f = file(filename, 'wb')
            try:
                dump(int(time() + timeout), f, 1)
                dump(value, f, HIGHEST_PROTOCOL)
            finally:
                f.close()
        except (IOError, OSError):
            pass

    def delete(self, key):
        try:
            os.remove(self._get_filename(filename))
        except (IOError, OSError):
            pass


#: map the cache systems to strings for the configuration
systems = {
    'null':         NullCache,
    'simple':       SimpleCache,
    'memcached':    MemcachedCache,
    'filesystem':   FileSystemCache
}
