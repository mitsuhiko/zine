# -*- coding: utf-8 -*-
"""
    zine.config
    ~~~~~~~~~~~

    This module implements the configuration.  The configuration is a more or
    less flat thing saved as ini in the instance folder.  If the configuration
    changes the application is reloaded automatically.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Lukas Meuser.
    :license: GNU GPL.
"""
import os
from os import path
from threading import Lock

from zine.i18n import lazy_gettext, _
from zine.utils import log
from zine.application import InternalError


#: variables the zine core uses
DEFAULT_VARS = {
    # general settings
    'database_uri':             (unicode, u''),
    'blog_title':               (unicode, lazy_gettext(u'My Zine Blog')),
    'blog_tagline':             (unicode, lazy_gettext(u'just another Zine blog')),
    'blog_url':                 (unicode, u''),
    'blog_email':               (unicode, u''),
    'timezone':                 (unicode, u'UTC'),
    'maintenance_mode':         (bool, False),
    'session_cookie_name':      (unicode, u'zine_session'),
    'theme':                    (unicode, u'default'),
    'secret_key':               (unicode, u''),
    'language':                 (unicode, u'en'),
    'plugin_searchpath':        (unicode, u''),

    # the iid is an internal unique id for the instance.  The setup creates a
    # uuid5 in hex format if possible (eg: uuid module is present), otherwise
    # it takes the current timestamp and hexifies it.  Changing this value later
    # will most likely break plugins with persistent data (pickles)
    'iid':                      (unicode, u''),

    # logger settings
    'log_file':                 (unicode, u'zine.log'),
    'log_level':                (unicode, u'warning'),

    # if set to true, internal errors are not catched.  This is useful for
    # debugging tools such as werkzeug.debug
    'passthrough_errors':       (bool, False),

    # url settings
    'blog_url_prefix':          (unicode, u''),
    'admin_url_prefix':         (unicode, u'/admin'),
    'category_url_prefix':      (unicode, u'/categories'),
    'tags_url_prefix':          (unicode, u'/tags'),
    'profiles_url_prefix':      (unicode, u'/authors'),

    # cache settings
    'enable_eager_caching':     (bool, False),
    'cache_timeout':            (int, 300),
    'cache_system':             (unicode, u'null'),
    'memcached_servers':        (unicode, u''),
    'filesystem_cache_path':    (unicode, u'cache'),

    # the default markup parser. Don't ever change this value! The
    # htmlprocessor module bypasses this test when falling back to
    # the default parser. If there plans to change the default parser
    # for future Zine versions that code must be altered first.
    'default_parser':           (unicode, u'zeml'),
    'comment_parser':           (unicode, u'text'),

    # comments and pingback
    'comments_enabled':         (bool, True),
    'moderate_comments':        (int, 1),       # aka MODERATE_ALL
    'pings_enabled':            (bool, True),

    # post view
    'posts_per_page':           (int, 10),
    'use_flat_comments':        (bool, False),
    'index_content_types':      (unicode, 'entry'),

    # pages
    'show_page_title':          (bool, True),
    'show_page_children':       (bool, True),

    # file uploads
    'upload_folder':            (unicode, u'uploads'),
    'upload_mimetypes':         (unicode, u'*.plugin:application/'
                                          u'x-zine-plugin'),
    'im_path':                  (unicode, u''),

    # email settings
    'smtp_host':                (unicode, u'localhost'),
    'smtp_port':                (int, 25),
    'smtp_user':                (unicode, u''),
    'smtp_password':            (unicode, u''),
    'smtp_use_tls':             (bool, False),

    # plugin settings
    'plugin_guard':             (bool, True),
    'plugins':                  (unicode, u''),

    # importer settings
    'blogger_auth_token':       (unicode, u'')
}

HIDDEN_KEYS = set(('iid', 'secret_key', 'blogger_auth_token',
                   'smtp_password'))

#: header for the config file
CONFIG_HEADER = '''\
# Zine configuration file
# This file is also updated by the Zine admin interface which will strip
# all comments due to a limitation in the current implementation.  If you
# want to maintain the file with your text editor be warned that comments
# may disappear.  The charset of this file must be utf-8!

'''


def unquote_value(value):
    """Unquote a configuration value."""
    if not value:
        return ''
    if value[0] in '"\'' and value[0] == value[-1]:
        value = value[1:-1].decode('string-escape')
    return value.decode('utf-8')


def quote_value(value):
    """Quote a configuration value."""
    if not value:
        return ''
    if value.strip() == value and value[0] not in '"\'' and \
       value[-1] not in '"\'' and len(value.splitlines()) == 1:
        return value.encode('utf-8')
    return '"%s"' % value.replace('\\', '\\\\') \
                         .replace('\n', '\\n') \
                         .replace('\r', '\\r') \
                         .replace('\t', '\\t') \
                         .replace('"', '\\"').encode('utf-8')


def from_string(value, conv, default):
    """Try to convert a value from string or fall back to the default."""
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


class ConfigurationTransactionError(InternalError):
    """An exception that is raised if the transaction was unable to
    write the changes to the config file.
    """

    help_text = lazy_gettext(u'''
    <p>
      This error can happen if the configuration file is not writeable.
      Make sure the folder of the configuration file is writeable and
      that the file itself is writeable as well.
    ''')

    def __init__(self, message_or_exception):
        if isinstance(message_or_exception, basestring):
            message = message_or_exception
            error = None
        else:
            message = _(u'Could not save configuration file: %s') % \
                      str(message_or_exception).decode('utf-8', 'ignore')
            error = message_or_exception
        InternalError.__init__(self, message)
        self.original_exception = error


class Configuration(object):
    """Helper class that manages configuration values in a INI configuration
    file.

    >>> app.cfg['blog_title']
    iu'My Zine Blog'
    >>> app.cfg.change_single('blog_title', 'Test Blog')
    >>> app.cfg['blog_title']
    u'Test Blog'
    >>> t = app.cfg.edit(); t.revert_to_default('blog_title'); t.commit()
    """

    def __init__(self, filename):
        self.filename = filename

        self.config_vars = DEFAULT_VARS.copy()
        self._values = {}
        self._converted_values = {}
        self._lock = Lock()

        # if the path does not exist yet set the existing flag to none and
        # set the time timetamp for the filename to something in the past
        if not path.exists(self.filename):
            self.exists = False
            self._load_time = 0
            return

        # otherwise parse the file and copy all values into the internal
        # values dict.  Do that also for values not covered by the current
        # `config_vars` dict to preserve variables of disabled plugins
        self._load_time = path.getmtime(self.filename)
        self.exists = True
        section = 'zine'
        f = file(self.filename)
        try:
            for line in f:
                line = line.strip()
                if not line or line[0] in '#;':
                    continue
                elif line[0] == '[' and line[-1] == ']':
                    section = line[1:-1].strip()
                elif '=' not in line:
                    key = line.strip()
                    value = ''
                else:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    if section != 'zine':
                        key = section + '/' + key
                    self._values[key] = unquote_value(value.strip())
        finally:
            f.close()

    def __getitem__(self, key):
        """Return the value for a key."""
        if key.startswith('zine/'):
            key = key[5:]
        try:
            return self._converted_values[key]
        except KeyError:
            conv, default = self.config_vars[key]
        try:
            value = from_string(self._values[key], conv, default)
        except KeyError:
            value = default
        self._converted_values[key] = value
        return value

    def change_single(self, key, value):
        """Create and commit a transaction for a single key-value-pair."""
        t = self.edit()
        t[key] = value
        t.commit()

    def edit(self):
        """Return a new transaction object."""
        return ConfigTransaction(self)

    def touch(self):
        """Touch the file to trigger a reload."""
        os.utime(self.filename, None)

    @property
    def changed_external(self):
        """True if there are changes on the file system."""
        if not path.isfile(self.filename):
            return False
        return path.getmtime(self.filename) > self._load_time

    def __iter__(self):
        """Iterate over all keys"""
        return iter(self.config_vars)

    iterkeys = __iter__

    def __contains__(self, key):
        """Check if a given key exists."""
        if key.startswith('zine/'):
            key = key[5:]
        return key in self.config_vars

    def itervalues(self):
        """Iterate over all values."""
        for key in self:
            yield self[key]

    def iteritems(self):
        """Iterate over all keys and values."""
        for key in self:
            yield key, self[key]

    def values(self):
        """Return a list of values."""
        return list(self.itervalues())

    def keys(self):
        """Return a list of keys."""
        return list(self)

    def items(self):
        """Return a list of all key, value tuples."""
        return list(self.iteritems())

    def get_detail_list(self):
        """Return a list of categories with keys and some more
        details for the advanced configuration editor.
        """
        categories = {}

        for key, (conv, default) in self.config_vars.iteritems():
            if key in self._values:
                use_default = False
                value = unicode(from_string(self._values[key], conv, default))
            else:
                use_default = True
                value = unicode(default)
            if '/' in key:
                category, name = key.split('/', 1)
            else:
                category = 'zine'
                name = key
            categories.setdefault(category, []).append({
                'name':         name,
                'key':          key,
                'type':         get_converter_name(conv),
                'value':        value,
                'use_default':  use_default,
                'default':      default
            })

        def sort_func(item):
            """Sort by key, case insensitive, ignore leading underscores and
            move the implicit "zine" to the index.
            """
            if item[0] == 'zine':
                return 1
            return item[0].lower().lstrip('_')

        return [{
            'items':    sorted(children, key=lambda x: x['name']),
            'name':     key
        } for key, children in sorted(categories.items(), key=sort_func)]

    def get_public_list(self, hide_insecure=False):
        """Return a list of publicly available information about the
        configuration.  This list is save to share because dangerous keys
        are either hidden or cloaked.
        """
        from zine.application import emit_event
        from zine.database import secure_database_uri
        result = []
        for key, (_, default) in self.config_vars.iteritems():
            value = self[key]
            if hide_insecure:
                if key in HIDDEN_KEYS:
                    value = '****'
                elif key == 'database_uri':
                    value = repr(secure_database_uri(value))
                else:
                    #! this event is emitted if the application wants to
                    #! display a configuration value in a publicly.  The
                    #! return value of the listener is used as new value.
                    #! A listener should return None if the return value
                    #! is not used.
                    for rv in emit_event('cloak-insecure-configuration-var',
                                         key, value):
                        if rv is not None:
                            value = rv
                            break
                    else:
                        value = repr(value)
            else:
                value = repr(value)
            result.append({
                'key':          key,
                'default':      repr(default),
                'value':        value
            })
        result.sort(key=lambda x: x['key'].lower())
        return result

    def __len__(self):
        return len(self.config_vars)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, dict(self.items()))


class ConfigTransaction(object):
    """A configuration transaction class. Instances of this class are returned
    by Config.edit(). Changes can then be added to the transaction and
    eventually be committed and saved to the file system using the commit()
    method.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self._values = {}
        self._converted_values = {}
        self._remove = []
        self._committed = False

    def __getitem__(self, key):
        """Get an item from the transaction or the underlaying config."""
        if key in self._converted_values:
            return self._converted_values[key]
        elif key in self._remove:
            return self.cfg.config_vars[key][1]
        return self.cfg[key]

    def __setitem__(self, key, value):
        """Set the value for a key by a python value."""
        self._assert_uncommitted()
        if key.startswith('zine/'):
            key = key[5:]
        if key not in self.cfg.config_vars:
            raise KeyError(key)
        if isinstance(value, str):
            value = value.decode('utf-8')
        self._values[key] = unicode(value)
        self._converted_values[key] = value

    def _assert_uncommitted(self):
        if self._committed:
            raise ValueError('This transaction was already committed.')

    def set_from_string(self, key, value, override=False):
        """Set the value for a key from a string."""
        self._assert_uncommitted()
        if key.startswith('zine/'):
            key = key[5:]
        conv, default = self.cfg.config_vars[key]
        new = from_string(value, conv, default)
        old = self._converted_values.get(key, None) or self.cfg[key]
        if override or unicode(old) != unicode(new):
            self[key] = new

    def revert_to_default(self, key):
        """Revert a key to the default value."""
        self._assert_uncommitted()
        if key.startswith('zine'):
            key = key[5:]
        self._remove.append(key)

    def update(self, *args, **kwargs):
        """Update multiple items at once."""
        for key, value in dict(*args, **kwargs).iteritems():
            self[key] = value

    def commit(self):
        """Commit the transactions. This first tries to save the changes to the
        configuration file and only updates the config in memory when that is
        successful.
        """
        self._assert_uncommitted()
        if not self._values and not self._remove:
            self._committed = True
            return
        self.cfg._lock.acquire()
        try:
            all = self.cfg._values.copy()
            all.update(self._values)
            for key in self._remove:
                all.pop(key, None)

            sections = {}
            for key, value in all.iteritems():
                if '/' in key:
                    section, key = key.split('/', 1)
                else:
                    section = 'zine'
                sections.setdefault(section, []).append((key, value))
            sections = sorted(sections.items())
            for section in sections:
                section[1].sort()

            try:
                f = file(self.cfg.filename, 'w')
                f.write(CONFIG_HEADER)
                try:
                    for idx, (section, items) in enumerate(sections):
                        if idx:
                            f.write('\n')
                        f.write('[%s]\n' % section.encode('utf-8'))
                        for key, value in items:
                            f.write('%s = %s\n' % (key, quote_value(value)))
                finally:
                    f.close()
            except IOError, e:
                log.error('Could not write configuration: %s' % e, 'config')
                raise ConfigurationTransactionError(e)
            self.cfg._values.update(self._values)
            self.cfg._converted_values.update(self._converted_values)
            for key in self._remove:
                self.cfg._values.pop(key, None)
                self.cfg._converted_values.pop(key, None)
        finally:
            self.cfg._lock.release()
        self._committed = True
