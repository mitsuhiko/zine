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


    :copyright: 2006-2008 by Armin Ronacher, Christopher Grebs, Georg Brandl.
    :license: BSD
"""
import __builtin__
import re
import sys
import imp
import inspect
from os import path, listdir, walk, makedirs
from types import ModuleType
from shutil import rmtree
from time import localtime, time
from cStringIO import StringIO
from base64 import b64encode

from urllib import quote
from werkzeug import cached_property, escape, find_modules, import_string

from zine.application import get_application
from zine.utils import log
from zine.utils.mail import split_email, is_valid_email, check
from zine.utils.exceptions import UnicodeException, summarize_exception
from zine.i18n import Translations, lazy_gettext, _


_py_import = __builtin__.__import__
_i18n_key_re = re.compile(r'^(.*?)\[([^\]]+)\]$')

#: a dict of all managed applications by iid.
#: every application in this dict has a plugin space this module
#: controls.  This is only used internally
_managed_applications = {}

PACKAGE_VERSION = 1


def get_object_name(obj):
    """Return a human readable name for the object."""
    if inspect.isclass(obj) or inspect.isfunction(obj):
        cls = obj
    else:
        cls = obj.__class__
    if cls.__module__.startswith('zine.plugins.'):
        prefix = cls.__module__.split('.', 2)[-1]
    elif cls.__module__.startswith('zine.'):
        prefix = cls.__module__
    else:
        prefix = 'external.' + cls.__module__
    return prefix + '.' + cls.__name__


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


class InstallationError(UnicodeException):
    """Raised during plugin installation."""

    MESSAGES = {
        'invalid':  lazy_gettext('Could not install the plugin because the '
                                 'uploaded file is not a valid plugin file.'),
        'version':  lazy_gettext('The plugin uploaded has a newer package '
                                 'version than this Zine installation '
                                 'can handle.'),
        'exists':   lazy_gettext('A plugin with the same UID is already '
                                 'installed. Aborted.'),
        'ioerror':  lazy_gettext('Could not install the package because the '
                                 'installer wasn\'t able to write the package '
                                 'information. Wrong permissions?')
    }

    def __init__(self, code):
        UnicodeException.__init__(self, self.MESSAGES[code])
        self.code = code


class SetupError(UnicodeException):
    """Raised by plugins if they want to stop their setup.  If a plugin raises
    a `SetupError` during the init, it will be disabled automatically.
    """


def make_setup_error(exc_info=None):
    """Create a new SetupError for the last exception and log it."""
    if exc_info is None:
        exc_info = sys.exc_info()

    # log the exception
    log.exception(_(u'Plugin setup error'), 'pluginsystem', exc_info)
    exc_type, exc_value, tb = exc_info

    # if the exception is already a SetupError we only
    # have to return it unchanged.
    if isinstance(exc_value, SetupError):
        return exc_value

    # otherwise create an error message for it and return a new
    # exception.
    error, (filename, line) = summarize_exception(exc_info)
    return SetupError(_(u'Exception happend on setup: '
                        u'%(error)s (%(file)s, line %(line)d)') % {
        'error':    escape(error),
        'file':     filename,
        'line':     line
    })


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
        """The module of the plugin. The first access imports it."""
        try:
            # we directly import from the zine module space
            return __import__('zine.plugins.%s' % self.name, None, None,
                              ['setup'])
        except:
            if not self.app.cfg['plugin_guard']:
                raise
            self.setup_error = make_setup_error()

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
                    escape(check(is_valid_email, contact) and
                           'mailto:' + contact or contact),
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
                self.setup_error = make_setup_error()
            if not self.app.cfg['plugin_guard']:
                raise

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


def set_plugin_searchpath(searchpath):
    """Set the plugin searchpath for the plugin pseudo package."""
    _plugins.__path__ = searchpath


# the application imports this on setup and modifies it
sys.modules['zine.plugins'] = _plugins = ModuleType('zine.plugins')
