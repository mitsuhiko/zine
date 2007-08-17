# -*- coding: utf-8 -*-
"""
    textpress.pluginsystem
    ~~~~~~~~~~~~~~~~~~~~~~

    This module implements the plugin system.

    Limitations: all applications share the load path. So strange things could
    occour if someone has the same plugins in different locations. We should
    fix that somewhere in the future.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import sys
import new
from os import path, listdir

import textpress
from textpress.application import get_application
from textpress.database import plugins, db
from textpress.utils import lazy_property


GLOBAL_PLUGIN_FOLDER = path.join(path.dirname(__file__), 'plugins')


def find_plugins(app):
    """Return an iterator over all plugins available."""
    enabled_plugins = set()
    for row in app.database_engine.execute(plugins.select()):
        if row.active:
            enabled_plugins.add(row.name)

    for folder in app.plugin_searchpath + [GLOBAL_PLUGIN_FOLDER]:
        if not path.exists(folder):
            continue
        if folder not in global_searchpath:
            global_searchpath.append(folder)
        for filename in listdir(folder):
            full_name = path.join(folder, filename)
            if path.isdir(full_name) and \
               path.exists(path.join(full_name, 'metadata.txt')):
                yield Plugin(app, filename, path.abspath(full_name),
                             filename in enabled_plugins)


class Plugin(object):
    """Wraps a plugin module."""

    def __init__(self, app, name, path, active):
        self.app = app
        self.name = name
        self.path = path
        self.active = active

    def activate(self):
        """Activate the plugin."""
        def do(con):
            result = con.execute(db.select([plugins.c.active],
                                           plugins.c.name == self.name))
            row = result.fetchone()
            if row is not None:
                if row.active:
                    return
                con.execute(plugins.update(plugins.c.name == self.name),
                            active=True)
            else:
                con.execute(plugins.insert(), name=self.name, active=True)
            self.active = True
        self.app.database_engine.transaction(do)

    def deactivate(self):
        """Deactivate this plugin."""
        def do(con):
            result = con.execute(db.select([plugins.c.active],
                                           plugins.c.name == self.name))
            row = result.fetchone()
            if row is not None:
                if not row.active:
                    return
                con.execute(plugins.update(plugins.c.name == self.name),
                            active=False)
            else:
                con.execute(plugins.insert(), name=self.name, active=False)
            self.active = False
        self.app.database_engine.transaction(do)

    @lazy_property
    def metadata(self):
        result = {}
        f = file(path.join(self.path, 'metadata.txt'))
        try:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                key, value = line.split(':', 1)
                result[key.rstrip().lower()] = value.lstrip()
        finally:
            f.close()
        return result

    @lazy_property
    def module(self):
        """The module of the plugin. The first access imports it."""
        from textpress import plugins
        return __import__('textpress.plugins.' + self.name, None, None, [''])

    def setup(self):
        """Setup the plugin."""
        self.module.setup(self.app, self)

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


# setup the pseudo package for the plugins
plugin_module = new.module('plugins')
sys.modules['textpress.plugins'] = textpress.plugins = plugin_module
plugin_module.__path__ = global_searchpath = []
