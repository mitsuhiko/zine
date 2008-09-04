# -*- coding: utf-8 -*-
"""
    zine.utils.datastructures
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Various data structures.

    :copyright: Copyright 2008 by Armin Ronacher
    :license: GNU GPL.
"""


class ReadOnlyMultiMapping(object):
    """Provides a read only view to multiple mappings."""

    def __init__(self, *mappings):
        self._mappings = mappings

    def __getitem__(self, name):
        for mapping in self._mappings:
            if name in mapping:
                return mapping[name]
        raise KeyError(name)

    def get(self, name, default=None):
        """Return a key or the default value if no value exists."""
        try:
            return self[name]
        except KeyError:
            return default

    def __contains__(self, name):
        try:
            self[name]
        except KeyError:
            return False
        return True

    def _dict_method(name):
        def proxy(self):
            return getattr(self.as_dict(), name)()
        proxy.__name__ = name
        proxy.__doc__ = getattr(dict, name).__doc__
        return proxy

    __iter__ = iterkeys = _dict_method('iterkeys')
    itervalues = _dict_method('itervalues')
    iteritems = _dict_method('iteritems')
    keys = _dict_method('keys')
    values = _dict_method('values')
    items = _dict_method('items')
    __len__ = _dict_method('__len__')
    del _dict_method

    def as_dict(self):
        result = {}
        for mapping in self._mappings:
            result.update(mapping)
        return result
