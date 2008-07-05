# -*- coding: utf-8 -*-
"""
    textpress.pluginsystem
    ~~~~~~~~~~~~~~~~~~~~~~

    This module implements the plugin system.


    Plugin Distribution
    -------------------

    The best way to distribute plugins are `.plugin` files.  Those files are
    simple zip files that are uncompressed when installed from the plugin
    admin panel.  You can easily create .plugin files yourself.  Just finish
    the plugin and open the textpress shell::

        >>> app.plugins['<name of the plugin>'].dump('/target/filename.plugin')

    This will save the plugin as `.plugin` package. The preferred filename
    for templates is `<DISPLAY_NAME_WITHOUT_SPACES>-<VERSION>.plugin`.  So if
    you want to dump all the plugins you have into plugin files you can use
    this snippet::

        for plugin in app.plugins.itervalues():
            plugin.dump('%s-%s.plugin' % (
                ''.join(plugin.display_name.split()),
                plugin.version
            ))

    It's only possible to create packages of plugins that are bound to an
    application so just create a development instance for plugin development.


    Plugin Metadata
    ---------------

    To identify a plugin metadata are used. TextPress requires a file
    named `metadata.txt` to load some information about the plugin.

    TextPress currently supports the following metadata information:

        :Name:
            The full name of the plugin.
        :Plugin URL:
            The URL of the plugin (e.g download location)
        :Description:
            The full description of the plugin.
        :Author:
            The name of the author of the plugin.
            Use the this field in the form of ``Name <author@webpage.xy>``
            where `Name` is the full name of the author.
        :Author URL:
            The webpage of the plugin-author.
        :Contributors:
            Add a list of all contributors seperated by a comma.
            Use this field in the form of ``Name1 <n1@w1.xy>, Name2
            <n2@w2.xy>`` where `Name` is the full name of the author
            and the email is optional.
        :Version:
            The version of the deployed plugin.
        :Preview:
            *For themes only*
            A little preview of the theme deployed by the plugin.
        :Depends:
            A list of plugins the plugin depends on.  All plugin-names will
            be splitted by a comma and also named exactly as the depended plugin.
            All plugins in this list will be activated if found but if one
            is missed the admin will be informated about that and the plugin
            won't be activated.

    :copyright: 2006-2008 by Armin Ronacher, Christopher Grebs, Georg Brandl.
    :license: GNU GPL.
"""
import __builtin__
import sys
import new
import re
from os import path, listdir, walk, makedirs
from types import ModuleType
from shutil import rmtree
from time import localtime, time
from cStringIO import StringIO
from base64 import b64encode

import textpress
from urllib import quote, urlencode, FancyURLopener
from werkzeug import cached_property, escape

from textpress.application import get_application
from textpress.utils.mail import split_email, is_valid_email


_py_import = __builtin__.__import__


BUILTIN_PLUGIN_FOLDER = path.join(path.dirname(__file__), 'plugins')
PACKAGE_VERSION = 1


def textpress_import(name, *args):
    """Redirect imports for textpress.plugins to the module space."""
    if name == 'textpress.plugins' or name.startswith('textpress.plugins.'):
        app = get_application()
        if app is not None:
            name = 'textpress._space.%s%s' % (app.iid, name[17:])
    return _py_import(name, *args)


def register_application(app):
    """Register the application on the plugin space."""
    setattr(plugin_space, app.iid, PluginDispatcher(app))


def unregister_application(app):
    """Unregister the application on the plugin space."""
    prefix = 'textpress._space.%s' % app.iid
    for module in sys.modules.keys():
        if module.startswith(prefix):
            sys.modules.pop(module, None)
    try:
        delattr(plugin_space, app.iid)
    except AttributeError:
        pass


def find_plugins(app):
    """Return an iterator over all plugins available."""
    enabled_plugins = set()
    for plugin in app.cfg['plugins'].split(','):
        plugin = plugin.strip()
        if plugin:
            enabled_plugins.add(plugin)

    for folder in app.plugin_searchpath:
        if not path.isdir(folder):
            continue
        for filename in listdir(folder):
            full_name = path.join(folder, filename)
            if path.isdir(full_name) and \
               path.isfile(path.join(full_name, 'metadata.txt')):
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
    app.cfg.touch()
    return plugin


def get_package_metadata(package):
    """Get the metadata of a plugin in a package. Pass it a filepointer or
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
    """Parse the metadata and return it as dict."""
    result = {}
    if isinstance(string_or_fp, basestring):
        fileiter = iter(string_or_fp.splitlines(True))
    else:
        fileiter = iter(string_or_fp.readline, '')
    for line in fileiter:
        line = line.strip().decode('utf-8')
        if not line or line.startswith('#'):
            continue
        if not ':' in line:
            key = line.strip()
            value = ''
        else:
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
    """Raised during plugin installation."""

    def __init__(self, code):
        self.code = code
        ValueError.__init__(self, code)


class SetupError(RuntimeError):
    """Raised by plugins if they want to stop their setup.  If a plugin raises
    a `SetupError` during the init, it will be disabled automatically.
    """


class PackageUploader(FancyURLopener, object):
    """Helper class for uploading packages. This is not a public
    interface, always use the Plugin upload function.
    """

    version = 'TextPress Package Uploader/%s' % textpress.__version__
    upload_url = 'http://textpress.pocoo.org/developers/upload_plugin'

    def __init__(self, plugin, email, password):
        FancyURLopener.__init__(self)
        self.plugin = plugin
        self.email = email
        self.password = password

    def upload(self):
        stream = StringIO()
        self.plugin.dump(stream)
        fp = self.open(self.upload_url, urlencode({
            'package_data':     b64encode(stream.getvalue()),
            'email':            self.email,
            'password':         self.password
        }))
        return fp.read().strip()


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
        self.setup_error = None

    def activate(self):
        """Activate the plugin.

        :return: A tuple in the form of ``(loaded_successfully,
                 loaded_dependences, missing_dependences)`` where the first
                 item represents if the plugin was loaded and the latter ones
                 represents loaded/missing dependences.
        """
        plugins = set(x.strip() for x in self.app.cfg['plugins'].split(','))
        loaded_dependences = set()
        missing_dependences = set()
        # handle dependences
        if self.depends:
            for dep in self.depends:
                if (dep in self.app.plugins and
                    not self.app.plugins[dep].active):

                    loaded_dependences.add(dep)
                elif dep not in self.app.plugins:
                    missing_dependences.add(dep)

        if not missing_dependences:
            for dep_to_load in loaded_dependences:
                dep_obj = self.app.plugins[dep_to_load]
                if not dep_obj.active:
                    dep_obj.activate()

            loaded = loaded_dependences.copy()
            loaded.update([self.name])
            plugins.update(loaded)
            self.app.cfg.change_single('plugins',
                ', '.join(x for x in sorted(plugins) if x))

        return ((missing_dependences and False or True), loaded_dependences,
                missing_dependences)

    def deactivate(self):
        """Deactivate this plugin."""
        plugins = set(x.strip() for x in self.app.cfg['plugins'].split(','))
        plugins.discard(self.name)
        self.app.cfg.change_single('plugins',
            ', '.join(x for x in sorted(plugins) if x))

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
            # don't recurse into hidden dirs
            for i in range(len(dirnames)-1, -1, -1):
                if dirnames[i].startswith('.'):
                    del dirnames[i]
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

    def upload(self, email, password):
        """Upload the plugin to the textpress server."""
        return PackageUploader(self, email, password).upload()

    @cached_property
    def metadata(self):
        try:
            f = file(path.join(self.path, 'metadata.txt'))
        except IOError:
            return {}
        try:
            return parse_metadata(f)
        finally:
            f.close()

    @cached_property
    def module(self):
        """The module of the plugin. The first access imports it."""
        try:
            # we directly import from the textpress module space
            return __import__('textpress._space.%s.%s' %
                              (self.app.iid, self.name), None, None,
                              ['setup'])
        except:
            if not self.app.cfg['plugin_guard']:
                raise
            self.setup_error = sys.exc_info()

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
        return split_email(self.metadata.get('author', u'Nobody')) + \
               (self.metadata.get('author_url'),)

    @property
    def contributors(self):
        """The Contributors of the plugin."""
        data = self.metadata.get('contributors', '')
        if not data:
            return []
        return [split_email(c.strip()) for c in
        self.metadata.get('contributors', '').split(',')]

    @property
    def html_contributors_info(self):
        result = []
        for contributor in self.contributors:
            name, contact = contributor
            if not contact:
                result.append(escape(name))
            else:
                result.append('<a href="%s">%s</a>' % (
                    escape(is_valid_email(contact) and 'mailto:'+contact or
                           contact),
                    escape(name)
                ))
        return u', '.join(result)

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
        x = self.author_info
        return x[0] or x[1]

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

    @property
    def depends(self):
        """
        Iterator of all plugins this one depends on.

        Plugins listed here won't be loaded automaticly.
        """
        depends = self.metadata.get('depends', '')
        return depends and (x.strip() for x in depends.split(',')) or []

    def setup(self):
        """Setup the plugin."""
        try:
            self.module.setup(self.app, self)
        except:
            if self.setup_error is None:
                self.setup_error = sys.exc_info()
            if not self.app.cfg['plugin_guard']:
                raise

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class PseudoModule(ModuleType):
    """A pseudo module that is automatically registered in sys.modules."""

    def __init__(self, name):
        ModuleType.__init__(self, name)
        self.__package__ = self.__name__
        sys.modules[self.__name__] = self

    # use the object repr to avoid confusion; this is not a regular module
    __repr__ = object.__repr__


class PluginSpace(PseudoModule):
    """The module space is a special module that dispatches to plugins from
    different applications.
    """

    def __init__(self):
        PseudoModule.__init__(self, 'textpress._space')


class PluginDispatcher(PseudoModule):
    """A pseudo module that loads plugins."""

    def __init__(self, app):
        PseudoModule.__init__(self, 'textpress._space.%s' % app.iid)
        self._tp_app = app
        self.__path__ = app.plugin_searchpath


plugin_space = PluginSpace()
__builtin__.__import__ = textpress_import
textpress_import.__doc__ = _py_import
textpress_import.__name__ = '__import__'
