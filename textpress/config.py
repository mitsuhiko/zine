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
    'blog_url':             (unicode, u''),
    'timezone':             (unicode, u'Europe/Vienna'),
    'maintenance_mode':     (bool, False),
    'sid_cookie_name':      (unicode, u'textpress_sid'),
    'theme':                (unicode, u'default'),

    # comments and traceback defaults
    'comments_enabled':     (bool, True),
    'pings_enabled':        (bool, True),

    # post view
    'posts_per_page':       (int, 10),
    'datetime_format':      (unicode, u'%Y-%m-%d %H:%M'),
    'date_format':          (unicode, u'%Y-%m-%d'),
    'use_flat_comments':    (bool, False)
}


def from_string(value, conv, default):
    if conv is bool:
        conv = lambda x: x == 'True'
    try:
        return conv(value)
    except (ValueError, TypeError), e:
        return default


def get_converter_name(conv):
    """Get the name of a converter"""
    return {
        bool:   'boolean',
        int:    'integer',
        float:  'float'
    }.get(conv, 'string')


class Configuration(object):
    """Helper class that manages configuration values."""

    def __init__(self, app):
        self.app = app
        self.config_vars = DEFAULT_VARS.copy()
        self._cache = {}
        self.clear_cache = self._cache.clear

    def __getitem__(self, key):
        if key not in self.config_vars:
            raise KeyError()
        if key in self._cache:
            return self._cache[key]
        conv, default = self.config_vars[key]
        c = configuration.c
        result = self.app.database_engine.execute(configuration.select(c.key == key))
        row = result.fetchone()
        conv, default = self.config_vars[key]
        if row is None:
            rv = default
        else:
            rv = from_string(row.value, conv, default)
        self._cache[key] = rv
        return rv

    def __setitem__(self, key, value):
        if not key in self.config_vars:
            raise KeyError()
        svalue = unicode(value)
        c = configuration.c
        result = self.app.database_engine.execute(configuration.select(c.key == key))
        row = result.fetchone()
        if row is None:
            self.app.database_engine.execute(configuration.insert(),
                                             key=key, value=svalue)
        else:
            self.app.database_engine.execute(configuration.update(c.key == key),
                                             value=svalue)

        from textpress.application import emit_event
        emit_event('after-configuration-key-updated', key, value)
        self._cache[key] = value

    def set_from_string(self, key, value, override=False):
        conv, default = self.config_vars[key]
        new = from_string(value, conv, default)
        if override or unicode(self[key]) != unicode(new):
            self[key] = new

    def revert_to_default(self, key):
        self.app.database_engine.execute(configuration.delete(configuration.c.key == key))
        self._cache.pop(key, None)

    def __iter__(self):
        return iter(self.config_vars)

    def __contains__(self, key):
        return key in self.config_vars

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

    def get_detail_list(self):
        """
        Return a list of categories with keys and some more
        details for the advanced configuration editor.
        """
        categories = {}

        for key, (conv, default) in self.config_vars.iteritems():
            c = configuration.c
            result = self.app.database_engine.execute(configuration.select(c.key == key))
            row = result.fetchone()
            if row is None:
                use_default = True
                value = unicode(default)
            else:
                use_default = False
                value = unicode(from_string(row.value, conv, default))
            if '/' in key:
                category, name = key.split('/', 1)
            else:
                category = '__core__'
                name = key
            categories.setdefault(category, []).append({
                'name':         name,
                'key':          key,
                'type':         get_converter_name(conv),
                'value':        value,
                'use_default':  use_default,
                'default':      default
            })

        return [{
            'items':    sorted(children, key=lambda x: x['name']),
            'name':     key
        } for key, children in sorted(categories.items())]

    def __len__(self):
        return len(self.config_vars)

    def __repr__(self):
        return '<Configuration %r>' % dict(self.items())
