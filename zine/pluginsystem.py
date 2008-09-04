# -*- coding: utf-8 -*-
"""
    zine.pluginsystem
    ~~~~~~~~~~~~~~~~~

    This module implements the plugin system.


    Plugin Distribution
    -------------------

    The best way to distribute plugins are `.plugin` files.  Those files are
    simple zip files that are uncompressed when installed from the plugin
    admin panel.  You can easily create .plugin files yourself.  Just finish
    the plugin and use the `scripts/bundle-plugin` script or do it
    programmatically::

        app.plugins['<name of the plugin>'].dump('/target/filename.plugin')

    This will save the plugin as `.plugin` package. The preferred filename
    for templates is `<FILESYSTEM_NAME>-<VERSION>.plugin`.  So if
    you want to dump all the plugins you have into plugin files you can use
    this snippet::

        for plugin in app.plugins.itervalues():
            plugin.dump('%s-%s.plugin' % (
                plugin.filesystem_name,
                plugin.version
            ))

    It's only possible to create packages of plugins that are bound to an
    application so just create a development instance for plugin development.


    Plugin Metadata
    ---------------

    To identify a plugin metadata are used. Zine requires a file
    named `metadata.txt` to load some information about the plugin.

    Zine currently supports the following metadata information:

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
        The website of the plugin-author.
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

    Each key can be suffixed with "[LANG_CODE]" for internationlization::

        Title: Example Plugin
        Title[de]: Beispielplugin


    Warnings for the Professionals
    ------------------------------

    Zine separates multiple instances in the interpreter as good as it
    can.  That you can still interact with different instances is the nature
    of Python.  But just because you can you shouldn't do that.  Actually you
    are not allowed to do that because Zine supports reloading of plugins
    at runtime which requires that a plugin can shut down without leaving
    traces behind.  Additionally plugin must never do monkey patching because
    that cannot be undone savely again.

    There is no callback that is called on plugin unloading, what Zine
    does, is dropping all references it has to the plugins and waits for
    Python to deallocate the memory.  As plugin developer you have no chance
    to execute code before unloading.


    :copyright: 2006-2008 by Armin Ronacher, Christopher Grebs, Georg Brandl.
    :license: GNU GPL.
"""
import __builtin__
import re
import sys
import imp
from os import path, listdir, walk, makedirs
from types import ModuleType
from shutil import rmtree
from time import localtime, time
from cStringIO import StringIO
from base64 import b64encode

from urllib import quote
from werkzeug import cached_property, escape, find_modules, import_string

from zine.application import get_application
from zine.utils.mail import split_email, is_valid_email
from zine.i18n import Translations, lazy_gettext


_py_import = __builtin__.__import__
_i18n_key_re = re.compile(r'^(.*?)\[([^\]]+)\]$')

#: a dict of all managed applications by iid.
#: every application in this dict has a plugin space this module
#: controls.  This is only used internally
_managed_applications = {}

PACKAGE_VERSION = 1


def zine_import(name, *args):
    """Redirect imports for zine.plugins to the module space."""
    if name == 'zine.plugins' or name.startswith('zine.plugins.'):
        app = get_application()
        if app is not None:
            name = 'zine._space.%s%s' % (app.iid, name[12:])
    return _py_import(name, *args)


def get_plugin_space(app):
    """Return the plugin space for the given application."""
    return _py_import('zine._space.' + app.iid, None, None, ['__name__'])


def uncloak_path(path):
    """Uncloak an import path."""
    parts = path.split('.')
    if parts[:2] == ['zine', '_space'] and len(parts) > 3:
        return 'zine.plugins.' + '.'.join(parts[3:])
    return path


def register_application(app):
    """Register the application on the global plugin space."""
    module = PluginSpace(app)
    sys.modules[module.__name__] = module
    setattr(_global_plugin_space, app.iid, module)
    _managed_applications[app.iid] = app


def unregister_application(app):
    """Unregister the application on the plugin space."""
    _managed_applications.pop(app.iid, None)
    prefix = 'zine._space.%s' % app.iid
    for module in sys.modules.keys():
        if module.startswith(prefix):
            sys.modules.pop(module, None)
    try:
        delattr(_global_plugin_space, app.iid)
    except AttributeError:
        pass


def find_plugins(app):
    """Return an iterator over all plugins available."""
    enabled_plugins = set()
    found_plugins = set()
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
               path.isfile(path.join(full_name, 'metadata.txt')) and \
               filename not in found_plugins:
                found_plugins.add(filename)
                yield Plugin(app, str(filename), path.abspath(full_name),
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
        package_version = int(f.read('ZINE_PACKAGE'))
        plugin_name = f.read('ZINE_PLUGIN')
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

    # get the package version and name
    try:
        package_version = int(f.read('ZINE_PACKAGE'))
        plugin_name = f.read('ZINE_PLUGIN')
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
    """Parse the metadata and return it as metadata object."""
    result = {}
    translations = {}
    if isinstance(string_or_fp, basestring):
        fileiter = iter(string_or_fp.splitlines(True))
    else:
        fileiter = iter(string_or_fp.readline, '')
    fileiter = (line.decode('utf-8') for line in fileiter)
    for line in fileiter:
        line = line.strip()
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
        key = '_'.join(key.lower().split()).encode('ascii', 'ignore')
        value = value.lstrip()
        match = _i18n_key_re.match(key)
        if match is not None:
            key, lang = match.groups()
            translations.setdefault(lang, {})[key] = value
        else:
            result[key] = value
    return MetaData(result, translations)


class PluginSpace(ModuleType):
    """A special module that holds all managed plugins.  It has an
    attribute called app that is a reference to the application that owns
    the plugin space.  If the application is already unregistered that
    attribute is `None`.  There is also an attribute called `iid`
    which is the internal identifier for the plugin space.

    The plugin space is used internally only.  The public interface to
    the plugin space is :attr:`zine.application.Zine.plugins` which is
    a dict of :class:`Plugin` objects.
    """

    def __init__(self, app):
        ModuleType.__init__(self, 'zine._space.%s' % app.iid)
        self.__path__ = app.plugin_searchpath

    @property
    def app(self):
        """Returns the application for this plugin space."""
        return _managed_applications.get(self.iid)

    @property
    def iid(self):
        """The internal ID of the application / plugin space."""
        return self.__name__.split('.')[2]

    def __iter__(self):
        """Yields all modules this plugin space knows about.  This could also
        yield modules that are importable but no plugins (eg: `metadata.txt`
        is missing etc.)
        """
        for module_name in find_modules(self.__name__, include_packages=True):
            yield module_name.rsplit('.', 1)[-1]

    def __repr__(self):
        return '<PluginSpace %r>' % self.iid


class MetaData(object):
    """Holds metadata.  This object has a dict like interface to the metadata
    from the file and will return the values for the current language by
    default.  It's however possible to get an "untranslated" version of the
    metadata by calling the `untranslated` method.
    """

    def __init__(self, values, i18n_values=None):
        self._values = values
        self._i18n_values = i18n_values or {}

    def untranslated(self):
        """Return a metadata object without translations."""
        return MetaData(self._values)

    def __getitem__(self, name):
        locale = str(get_application().locale)
        if name in self._i18n_values.get(locale, ()):
            return self._i18n_values[locale][name]
        if name in self._values:
            return self._values[name]
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
    del _dict_method

    def as_dict(self):
        result = self._values.copy()
        result.update(self._i18n_values.get(str(get_application().locale), {}))
        return result


class InstallationError(ValueError):
    """Raised during plugin installation."""

    MESSAGES = {
        'invalid':  lazy_gettext('Could not install the plugin because the '
                                 'file uploaded is not a valid plugin file.'),
        'version':  lazy_gettext('The plugin uploaded has a newer package '
                                 'version than this Zine installation '
                                 'can handle.'),
        'exists':   lazy_gettext('A plugin with the same UID is already '
                                 'installed.  Aborted.'),
        'ioerror':  lazy_gettext('Could not install the package because the '
                                 'installer wasn\'t able to write the package '
                                 'information. Wrong permissions?')
    }

    def __init__(self, code):
        self.message = self.MESSAGES[code]
        self.code = code
        ValueError.__init__(self, code)


class SetupError(RuntimeError):
    """Raised by plugins if they want to stop their setup.  If a plugin raises
    a `SetupError` during the init, it will be disabled automatically.
    """


class Plugin(object):
    """Wraps a plugin module."""

    def __init__(self, app, name, path_, active):
        self.app = app
        self.name = name
        self.path = path_
        self.active = active
        self.instance_plugin = path.commonprefix([
            path.realpath(path_), path.realpath(app.plugin_folder)]) == \
            app.plugin_folder
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

        return not missing_dependences, loaded_dependences, \
                   missing_dependences

    def deactivate(self):
        """Deactivate this plugin."""
        plugins = set(x.strip() for x in self.app.cfg['plugins'].split(','))
        plugins.discard(self.name)
        self.app.cfg.change_single('plugins',
            ', '.join(x for x in sorted(plugins) if x))

    def remove(self):
        """Remove the plugin from the instance folder."""
        if not self.instance_plugin:
            raise ValueError('cannot remove non instance-plugins')
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
        for name, data in [('ZINE_PLUGIN', self.name),
                           ('ZINE_PACKAGE', PACKAGE_VERSION)]:
            zinfo = ZipInfo(name, localtime(time()))
            zinfo.compress_type = f.compression
            zinfo.external_attr = (33188 & 0xFFFF) << 16L
            f.writestr(zinfo, str(data))

        f.close()

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
    def translations(self):
        """The translations for this application."""
        locale_path = path.join(self.path, 'i18n')
        return Translations.load(locale_path, [self.app.cfg['language']])

    @cached_property
    def is_documented(self):
        """This property is True if the plugin has documentation."""
        for lang in self.app.cfg['language'], 'en':
            if path.isfile(path.join(self.path, 'docs', lang, 'index.page')):
                return True
        return False

    @cached_property
    def module(self):
        """The module of the plugin. The first access imports it.
        When the `unregister_application` function deletes the references to
        the modules from the sys.modules dict, the cached property will keep
        one reference until the reloader finishes it's work.  This should
        make sure that requests that happen during plugin reloading can finish
        without a problem.
        """
        try:
            # we directly import from the zine module space
            return __import__('zine._space.%s.%s' %
                              (self.app.iid, self.name), None, None,
                              ['setup'])
        except:
            if not self.app.cfg['plugin_guard']:
                raise
            exc_type, exc_value, tb = sys.exc_info()
            self.setup_error = exc_type, exc_value, tb.tb_next

    @property
    def display_name(self):
        """The full name from the metadata."""
        return self.metadata.get('name', self.name)

    @property
    def filesystem_name(self):
        """The human readable package name for the filesystem."""
        string = self.metadata.untranslated().get('name', self.name)
        return ''.join(string.split())

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
    def has_author(self):
        """Does the plugin has an author at all?"""
        return 'author' in self.metadata

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
        """A list of depenencies for this plugin.

        Plugins listed here won't be loaded automaticly.
        """
        depends = self.metadata.get('depends', '').strip()
        return filter(None, [x.strip() for x in depends.split(',')])

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


__builtin__.__import__ = zine_import
_global_plugin_space = ModuleType('zine._space')
sys.modules['zine._space'] = _global_plugin_space
