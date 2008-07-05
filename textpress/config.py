# -*- coding: utf-8 -*-
"""
    textpress.config
    ~~~~~~~~~~~~~~~~

    This module implements the configuration.  The configuration is a more or
    less flat thing saved as ini in the instance folder.  If the configuration
    changes the application is reloaded automatically.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Lukas Meuser.
    :license: GNU GPL.
"""
import os
from os import path


#: variables the textpress core uses
DEFAULT_VARS = {
    # general settings
    'database_uri':             (unicode, u''),
    'blog_title':               (unicode, u'My TextPress Blog'),
    'blog_tagline':             (unicode, u'just another textpress blog'),
    'blog_url':                 (unicode, u''),
    'blog_email':               (unicode, u''),
    'timezone':                 (unicode, u'UTC'),
    'maintenance_mode':         (bool, False),
    'session_cookie_name':      (unicode, u'textpress_session'),
    'theme':                    (unicode, u'default'),
    'secret_key':               (unicode, u''),
    'language':                 (unicode, u'en'),

    # url settings
    'blog_url_prefix':          (unicode, u''),
    'admin_url_prefix':         (unicode, u'/admin'),
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
    # for future TextPress versions that code must be altered first.
    'default_parser':           (unicode, u'default'),
    'comment_parser':           (unicode, u'comment'),

    # comments and pingback
    'comments_enabled':         (bool, True),
    'moderate_comments':        (int, 1),       # aka MODERATE_ALL
    'pings_enabled':            (bool, True),

    # post view
    'posts_per_page':           (int, 10),
    'use_flat_comments':        (bool, False),

    # pages
    'show_page_title':          (bool, True),
    'show_page_children':       (bool, True),

    # file uploads
    'upload_folder':            (unicode, u'uploads'),
    'upload_mimetypes':       (unicode, u'*.plugin:application/x-textpress-plugin'),
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

#: header for the config file
CONFIG_HEADER = '''\
# TextPress configuration file
# This file is also updated by the TextPress admin interface which will strip
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


class Configuration(object):
    """Helper class that manages configuration values in a INI configuration
    file.
    """

    def __init__(self, filename):
        self.filename = filename

        self.config_vars = DEFAULT_VARS.copy()
        self._values = {}
        self._converted_values = {}

        # if the path does not exist yet set the existing flag to none and
        # set the time timetamp for the filename to something in the past
        if not path.exists(self.filename):
            self.exists = False
            self._load_time = 0
            return

        # otherwise parse the file and copy all values into the internal
        # values dict.  Do that also for values not covered by the current
        # `config_vars` dict to preserve variables of disabled plugins
        self.exists = True
        self._load_time = path.getmtime(self.filename)
        section = 'textpress'
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
                    if section != 'textpress':
                        key = section + '/' + key
                    self._values[key] = unquote_value(value.strip())
        finally:
            f.close()

    def __getitem__(self, key):
        """Return the value for a key."""
        if key.startswith('textpress/'):
            key = key[10:]
        if key in self._converted_values:
            return self._converted_values[key]
        conv, default = self.config_vars[key]
        if key in self._values:
            value = from_string(self._values[key], conv, default)
        else:
            value = default
        self._converted_values[key] = value
        return value

    def change_single(self, key, value):
        """Create and commit a transaction for a single key-value-pair. Return
        True on success, otherwise False.
        """
        t = self.edit()
        t[key] = value
        try:
            t.commit()
            return True
        except IOError:
            return False

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
        if key.startswith('textpress/'):
            key = key[10:]
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
                category = 'textpress'
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
            move the implicit "textpress" to the index.
            """
            if item[0] == 'textpress':
                return 1
            return item[0].lower().lstrip('_')

        return [{
            'items':    sorted(children, key=lambda x: x['name']),
            'name':     key
        } for key, children in sorted(categories.items(), key=sort_func)]

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
        self._committed = False

    def __setitem__(self, key, value):
        """Set the value for a key by a python value."""
        if self._committed:
            raise ValueError('This transaction was already committed.')
        if key.startswith('textpress/'):
            key = key[10:]
        if key not in self.cfg.config_vars:
            raise KeyError(key)
        self._values[key] = unicode(value)
        self._converted_values[key] = value

    def set_from_string(self, key, value, override=False):
        """Set the value for a key from a string."""
        if self._committed:
            raise ValueError('This transaction was already committed.')
        if key.startswith('textpress/'):
            key = key[10:]
        conv, default = self.cfg.config_vars[key]
        new = from_string(value, conv, default)
        old = self._converted_values.get(key, None) or self.cfg[key]
        if override or unicode(old) != unicode(new):
            self._values[key] = unicode(new)
            self._converted_values[key] = new

    def revert_to_default(self, key):
        """Revert a key to the default value."""
        if self._committed:
            raise ValueError('This transaction was already committed.')
        if key.startswith('textpress'):
            key = key[10:]
        self._values.pop(key, None)
        self._converted_values.pop(self, key)

    def update(self, *args, **kwargs):
        """Update multiple items at once."""
        for key, value in dict(*args, **kwargs).iteritems():
            self[key] = value

    def commit(self):
        """Commit the transactions. This first tries to save the changes to the
        configuration file and only updates the config in memory when that is
        successful.
        """
        if self._committed:
            raise ValueError('This transaction was already committed.')
        if not self._values:
            self._committed = True
            return
        all = self.cfg._values.copy()
        all.update(self._values)

        sections = {}
        for key, value in all.iteritems():
            if '/' in key:
                section, key = key.split('/', 1)
            else:
                section = 'textpress'
            sections.setdefault(section, []).append((key, value))
        sections = sorted(sections.items())
        for section in sections:
            section[1].sort()

        f = file(self.cfg.filename, 'w')
        f.write(CONFIG_HEADER)
        try:
            for idx, (section, items) in enumerate(sections):
                if idx:
                    f.write('\n')
                f.write('[%s]\n' % section.encode('utf-8'))
                for key, value in items:
                    f.write('%s = %s\n' % (key, quote_value(value)))
            self.cfg._load_time = path.getmtime(self.cfg.filename)
        finally:
            f.close()
        self.cfg._values.update(self._values)
        self.cfg._converted_values.update(self._converted_values)
        self._committed = True
