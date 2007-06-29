# -*- coding: utf-8 -*-
"""
    textpress.config
    ~~~~~~~~~~~~~~~~

    Implements the configuration. The config is saved in the database
    but there is no model for that because we want a more human accessible
    thing.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.database import configuration


#: variables the textpress core uses
DEFAULT_VARS = {
    # general settings
    'blog_title':           (unicode, u'My TextPress Blog'),
    'blog_tagline':         (unicode, u'just another textpress blog'),
    'timezone':             (unicode, u'Europe/Vienna'),
    'maintenance_mode':     (bool, False),
    'sid_cookie_name':      (unicode, u'textpress_sid'),
    'automatic_db_upgrade': (bool, True),
    'theme':                (unicode, u'myrtle'),

    # comments and traceback defaults
    'comments_enabled':     (bool, True),
    'pings_enabled':        (bool, True),

    # post view
    'posts_per_page':       (int, 10),
    'datetime_format':      (unicode, u'%Y-%m-%d %H:%M'),
    'date_format':          (unicode, u'%Y-%m-%d'),
    'use_flat_comments':    (bool, False)
}


class Configuration(object):
    """Helper class that manages configuration values."""

    def __init__(self, app):
        self.app = app
        self.config_vars = DEFAULT_VARS.copy()
        self._engine = app.database_engine
        self._cache = {}

    def __getitem__(self, key):
        if key not in self.config_vars:
            raise KeyError()
        if key in self._cache:
            return self._cache[key]
        conv, default = self.config_vars[key]
        c = configuration.c
        result = self._engine.execute(configuration.select(c.key == key))
        row = result.fetchone()
        conv, default = self.config_vars[key]
        if row is None:
            rv = default
        else:
            if conv is bool:
                conv = lambda x: x == 'True'
            try:
                rv = conv(row.value)
            except (ValueError, TypeError):
                rv = default
        self._cache[key] = rv
        return rv

    def __setitem__(self, key, value):
        if not key in self.config_vars:
            raise KeyError()
        svalue = str(value)
        c = configuration.c
        result = self._engine.execute(configuration.select(c.key == key))
        row = result.fetchone()
        if row is None:
            self._engine.execute(configuration.insert(), key=key, value=svalue)
        else:
            self._engine.execute(configuration.update(c.key == key),
                                 value=svalue)
        self._cache[key] = value

    def __iter__(self):
        return iter(self.config_vars)

    iterkeys = __iter__

    def itervalues(self):
        for key in self:
            yield self[key]

    def iteritems(self):
        for key in self:
            yield key, self[key]

    def values(self):
        return list(self.itervalues())

    def keys(self):
        return list(self)

    def items(self):
        return list(self.iteritems())

    def __len__(self):
        return len(self.config_vars)

    def __repr__(self):
        return '<Configuration %r>' % dict(self.items())
