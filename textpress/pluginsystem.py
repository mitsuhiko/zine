# -*- coding: utf-8 -*-
"""
    textpress.pluginsystem
    ~~~~~~~~~~~~~~~~~~~~~~

    This module implements the plugin system.

    Limitations: all applications share the load path.  So strange things could
    occour if someone has the same plugins in different locations.  We should
    fix that somewhere in the future.


    Plugin Distribution
    ===================

    The best way to distribute plugins are `.plugin` files.  Those files are
    simple zip files that are uncompressed when installed from the plugin
    admin panel.  You can easily create .plugin files yourself.  Just finish
    the plugin and open the textpress shell::

        >>> app.plugins['<name of the plugin>'].dump('/target/filename.plugin')

    This will save the plugin as `.plugin` package. The preferred filename
    for templates is `<DISPLAY_NAME>-<VERSION>.plugin`. So if you want to
    dump all the plugins you have into plugin files you can use this snippet::

        for plugin in app.plugins.itervalues():
            plugin.dump('%s-%s.plugin' % (
                plugin.display_name,
                plugin.version
            ))

    It's only possible to create packages of plugins that are bound to an
    application so just create a development instance for plugin development.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import sys
import new
import re
from os import path, listdir, walk, makedirs
from shutil import rmtree
from time import localtime, time

import textpress
from urllib import quote
from textpress.application import get_application
from textpress.database import plugins, db
from textpress.utils import lazy_property, escape


BUILTIN_PLUGIN_FOLDER = path.join(path.dirname(__file__), 'plugins')
PACKAGE_VERSION = 1

_author_mail_re = re.compile(r'^(.*?)(?:\s+<(.+)>)?$')


def find_plugins(app):
    """Return an iterator over all plugins available."""
    enabled_plugins = set()
    for row in app.database_engine.execute(plugins.select()):
        if row.active:
            enabled_plugins.add(row.name)

    for folder in app.plugin_searchpath + [BUILTIN_PLUGIN_FOLDER]:
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


def install_package(app, package):
    """Install a plugin from a package to the instance plugin folder."""
    from zipfile import ZipFile, ZipInfo, error as BadZipFile
    import py_compile
    try:
        f = ZipFile(package)
    except (IOError, BadZipFile):
        raise InstallationError('invalid')

    # get the package version
    try:
        package_version = int(f.read('TEXTPRESS_PACKAGE'))
        plugin_name = f.read('TEXTPRESS_PLUGIN')
    except (KeyError, ValueError), e:
        raise InstallationError('invalid')

    # check if the package version is handleable
    if package_version > PACKAGE_VERSION:
        raise InstallationError('version')

    # check if there is already a plugin with the same name
    plugin_path = path.join(app.instance_folder, 'plugins', plugin_name)
    if path.exists(plugin_path):
        raise InstallationError('exists')

    # make sure that we have a folder
    try:
        makedirs(plugin_path)
    except (IOError, OSError):
        pass

    # now read all the files and write them to the folder
    for filename in f.namelist():
        if not filename.startswith('pdata/'):
            continue
        dst_filename = path.join(plugin_path, *filename[6:].split('/'))
        try:
            makedirs(path.dirname(dst_filename))
        except (IOError, OSError):
            pass
        try:
            dst = file(dst_filename, 'wb')
        except IOError:
            raise InstallationError('ioerror')
        try:
            dst.write(f.read(filename))
        finally:
            dst.close()

        if filename.endswith('.py'):
            py_compile.compile(dst_filename)

    plugin = Plugin(app, plugin_name, plugin_path, False)
    app.plugins[plugin_name] = plugin
    return plugin


def get_package_metadata(package):
    """
    Get the metadata of a plugin in a package. Pass it a filepointer or
    filename. Raises a `ValueError` if the package is not valid.
    """
    from zipfile import ZipFile, ZipInfo, error as BadZipFile
    try:
        f = ZipFile(package)
    except (IOError, BadZipFile):
        raise ValueError('not a valid package')

    # get the package version
    try:
        package_version = int(f.read('TEXTPRESS_PACKAGE'))
        plugin_name = f.read('TEXTPRESS_PLUGIN')
    except (KeyError, ValueError), e:
        raise ValueError('not a valid package')
    if package_version > PACKAGE_VERSION:
        raise ValueError('incompatible package version')

    try:
        metadata = parse_metadata(f.read('pdata/metadata.txt'))
    except KeyError:
        metadata = {}
    metadata['uid'] = plugin_name
    return metadata


def parse_metadata(string_or_fp):
    """
    Parse the metadata and return it as dict.
    """
    result = {}
    if isinstance(string_or_fp, basestring):
        fileiter = iter(string_or_fp.splitlines(True))
    else:
        fileiter = iter(string_or_fp.readline, '')
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
        try:
            result[str('_'.join(key.lower().split()))] = value.lstrip()
        except UnicodeError:
            continue
    return result


class InstallationError(ValueError):
    """
    Raised during plugin installation.
    """

    def __init__(self, code):
        self.code = code
        ValueError.__init__(self, code)


class Plugin(object):
    """Wraps a plugin module."""

    def __init__(self, app, name, path_, active):
        self.app = app
        self.name = name
        self.path = path_
        self.active = active
        self.builtin_plugin = path.commonprefix([
            path.realpath(path_), path.realpath(BUILTIN_PLUGIN_FOLDER)]) == \
            BUILTIN_PLUGIN_FOLDER

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

    def remove(self):
        """Remove the plugin from the instance folder."""
        if self.builtin_plugin:
            raise ValueError('cannot remove builtin plugins')
        if self.active:
            raise ValueError('cannot remove active plugin')
        rmtree(self.path)
        del self.app.plugins[self.name]

    def dump(self, fp):
        """Dump the plugin as package into the filepointer or file."""
        from zipfile import ZipFile, ZipInfo
        f = ZipFile(fp, 'w')

        # write all files into a "pdata/" folder
        offset = len(self.path) + 1
        for dirpath, dirnames, filenames in walk(self.path):
            for filename in filenames:
                if filename.endswith('.pyc') or \
                   filename.endswith('.pyo'):
                    continue
                f.write(path.join(dirpath, filename),
                        path.join('pdata', dirpath[offset:], filename))

        # add the package information files
        for name, data in [('TEXTPRESS_PLUGIN', self.name),
                           ('TEXTPRESS_PACKAGE', PACKAGE_VERSION)]:
            zinfo = ZipInfo(name, localtime(time()))
            zinfo.compress_type = f.compression
            zinfo.external_attr = (33188 & 0xFFFF) << 16L
            f.writestr(zinfo, str(data))

        f.close()

    @lazy_property
    def metadata(self):
        try:
            f = file(path.join(self.path, 'metadata.txt'))
        except IOError:
            return {}
        try:
            return parse_metadata(f)
        finally:
            f.close()

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
