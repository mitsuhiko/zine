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
import re
from os import path, listdir

import textpress
from urllib import quote
from textpress.application import get_application
from textpress.database import plugins, db
from textpress.utils import lazy_property, escape


GLOBAL_PLUGIN_FOLDER = path.join(path.dirname(__file__), 'plugins')

_author_mail_re = re.compile(r'^(.*?)(?:\s+<(.+)>)?$')


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
        fileiter = iter(f)
        try:
            for line in fileiter:
                line = line.strip().decode('utf-8')
                if not line or line.startswith('#'):
                    continue
                key, value = line.split(':', 1)
                while value.endswith('\\'):
                    try:
                        value = value[:-1] + fileiter.next().rstrip('\n')
                    except StopIteration:
                        pass
                result[u'_'.join(key.lower().split())] = value.lstrip()
        finally:
            f.close()
        return result

    @lazy_property
    def module(self):
        """The module of the plugin. The first access imports it."""
        from textpress import plugins
        return __import__('textpress.plugins.' + self.name, None, None, ['setup'])

    @property
    def display_name(self):
        """The full name from the metadata."""
        return self.metadata.get('name', self.name)

    @property
    def html_display_name(self):
        """The display name as HTML link."""
        link = self.plugin_url
        if link:
            return u'<a href="%s">%s</a>' % (
                escape(link),
                escape(self.display_name)
            )
        return escape(self.display_name)

    @property
    def plugin_url(self):
        """Return the URL of the plugin."""
        return self.metadata.get('plugin_url')

    @property
    def description(self):
        """Return the description of the plugin."""
        return self.metadata.get('description', u'')

    @property
    def author_info(self):
        """The author, mail and author URL of the plugin."""
        return _author_mail_re.search(self.metadata.get(
            'author', u'Nobody')).groups() + \
            (self.metadata.get('author_url'),)

    @property
    def html_author_info(self):
        """Return the author info as html link."""
        name, email, url = self.author_info
        if not url:
            if not email:
                return escape(name)
            url = 'mailto:%s' % quote(email)
        return u'<a href="%s">%s</a>' % (
            escape(url),
            escape(name)
        )

    @property
    def author(self):
        """Return the author of the plugin."""
        return self.author_info[0]

    @property
    def author_email(self):
        """Return the author email address of the plugin."""
        return self.author_info[1]

    @property
    def author_url(self):
        """Return the URL of the author of the plugin."""
        return self.author_info[2]

    @property
    def version(self):
        """The version of the plugin."""
        return self.metadata.get('version')

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
