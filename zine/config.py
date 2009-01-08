# -*- coding: utf-8 -*-
"""
    zine.config
    ~~~~~~~~~~~

    This module implements the configuration.  The configuration is a more or
    less flat thing saved as ini in the instance folder.  If the configuration
    changes the application is reloaded automatically.


    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import os
from os import path
from threading import Lock

from zine import environment
from zine.i18n import lazy_gettext, _, list_timezones, list_languages
from zine.utils import log
from zine.utils.forms import TextField, IntegerField, BooleanField, \
    ChoiceField, CommaSeparated
from zine.utils.validators import ValidationError, is_valid_url_prefix, \
    is_netaddr
from zine.application import InternalError


_dev_mode = environment.MODE == 'development'

#: variables the zine core uses
DEFAULT_VARS = {
    # general settings
    'database_uri':             TextField(default=u''),
    'blog_title':               TextField(default=lazy_gettext(u'My Zine Blog')),
    'blog_tagline':             TextField(default=lazy_gettext(u'just another Zine blog')),
    'blog_url':                 TextField(default=u''),
    'blog_email':               TextField(default=u''),
    'timezone':                 ChoiceField(choices=sorted(list_timezones()),
                                            default=u'UTC'),
    'maintenance_mode':         BooleanField(default=False),
    'session_cookie_name':      TextField(default=u'zine_session'),
    'theme':                    TextField(default=u'default'),
    'secret_key':               TextField(default=u''),
    'language':                 ChoiceField(choices=list_languages(False),
                                            default=u'en'),
    'plugin_searchpath':        CommaSeparated(TextField(), default=list),

    # the iid is an internal unique id for the instance.  The setup creates a
    # uuid5 in hex format if possible (eg: uuid module is present), otherwise
    # it takes the current timestamp and hexifies it.  Changing this value later
    # will most likely break plugins with persistent data (pickles)
    'iid':                      TextField(default=u''),

    # logger settings
    'log_file':                 TextField(default=u'zine.log'),
    'log_level':                ChoiceField(choices=[(k, lazy_gettext(k)) for k, v
                                                in sorted(log.LEVELS.items(),
                                                          key=lambda x: x[1])],
                                            default=u'warning'),

    # if set to true, internal errors are not caught.  This is useful for
    # debugging tools such as werkzeug.debug
    'passthrough_errors':       BooleanField(default=_dev_mode),

    # url settings
    'blog_url_prefix':          TextField(default=u'',
                                          validators=[is_valid_url_prefix()]),
    'admin_url_prefix':         TextField(default=u'/admin',
                                          validators=[is_valid_url_prefix()]),
    'category_url_prefix':      TextField(default=u'/categories',
                                          validators=[is_valid_url_prefix()]),
    'tags_url_prefix':          TextField(default=u'/tags',
                                          validators=[is_valid_url_prefix()]),
    'profiles_url_prefix':      TextField(default=u'/authors',
                                          validators=[is_valid_url_prefix()]),
    'ascii_slugs':              BooleanField(default=True),

    # cache settings
    'enable_eager_caching':     BooleanField(default=False),
    'cache_timeout':            IntegerField(default=300, min_value=10),
    'cache_system':             ChoiceField(choices=[
        (u'null', lazy_gettext(u'No Cache')),
        (u'simple', lazy_gettext(u'Simple Cache')),
        (u'memcached', lazy_gettext(u'memcached')),
        (u'filesystem', lazy_gettext(u'Filesystem'))
                                            ], default=u'null'),
    'memcached_servers':        CommaSeparated(TextField(
                                                    validators=[is_netaddr()]),
                                               default=list),
    'filesystem_cache_path':    TextField(default=u'cache'),

    # the default markup parser. Don't ever change this value! The
    # htmlprocessor module bypasses this test when falling back to
    # the default parser. If there plans to change the default parser
    # for future Zine versions that code must be altered first.
    'default_parser':           ChoiceField(default=u'zeml'),
    'comment_parser':           ChoiceField(default=u'text'),

    # comments and pingback
    'comments_enabled':         BooleanField(default=True),
    'moderate_comments':        ChoiceField(choices=[
        (0, lazy_gettext(u'Automatically approve all comments')),
        (1, lazy_gettext(u'An administrator must always approve the comment')),
        (2, lazy_gettext(u'Automatically approve comments by known comment authors'))
                                            ], default=1),
    'pings_enabled':            BooleanField(default=True),

    # post view
    'posts_per_page':           IntegerField(default=10),
    'use_flat_comments':        BooleanField(default=False),
    'index_content_types':      CommaSeparated(TextField(),
                                               default=lambda: ['entry']),

    # pages
    'show_page_title':          BooleanField(default=True),
    'show_page_children':       BooleanField(default=True),

    # email settings
    'smtp_host':                TextField(default=u'localhost'),
    'smtp_port':                IntegerField(default=25),
    'smtp_user':                TextField(default=u''),
    'smtp_password':            TextField(default=u''),
    'smtp_use_tls':             BooleanField(default=False),

    # plugin settings
    'plugin_guard':             BooleanField(default=True),
    'plugins':                  CommaSeparated(TextField(), default=list),

    # importer settings
    'blogger_auth_token':       TextField(default=u''),

    #admin settings
    'dashboard_reddit':         BooleanField(default=True)
}

HIDDEN_KEYS = set(('iid', 'secret_key', 'blogger_auth_token',
                   'smtp_password'))


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


def from_string(value, field):
    """Try to convert a value from string or fall back to the default."""
    try:
        return field(value)
    except ValidationError, e:
        return field.get_default()


# XXX: this function should probably go away, currently it only exists because
# the config editor is not yet updated to use form fields for config vars
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
        self._comments = {}
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
        current_comment = ''
        f = file(self.filename)
        try:
            for line in f:
                line = line.strip()
                if not line or line[0] in '#;':
                    current_comment += line + '\n'
                    continue
                elif line[0] == '[' and line[-1] == ']':
                    section = line[1:-1].strip()
                    if current_comment.strip():
                        self._comments['[%s]' % section] = current_comment
                    current_comment = ''
                elif '=' not in line:
                    key = line.strip()
                    value = ''
                    if current_comment.strip():
                        self._comments[key] = current_comment
                    current_comment = ''
                else:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    if section != 'zine':
                        key = section + '/' + key
                    self._values[key] = unquote_value(value.strip())
                    if current_comment.strip():
                        self._comments[key] = current_comment
                    current_comment = ''
            # comments at the end of the file
            if current_comment.strip():
                self._comments[' end '] = current_comment
        finally:
            f.close()

    def __getitem__(self, key):
        """Return the value for a key."""
        if key.startswith('zine/'):
            key = key[5:]
        try:
            return self._converted_values[key]
        except KeyError:
            field = self.config_vars[key]
        try:
            value = from_string(self._values[key], field)
        except KeyError:
            value = field.get_default()
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

    def export(self):
        """Like iteritems but with the raw values."""
        for key, value in self.iteritems():
            value = self.config_vars[key].to_primitive(value)
            if isinstance(value, basestring):
                yield key, value

    def get_detail_list(self):
        """Return a list of categories with keys and some more
        details for the advanced configuration editor.
        """
        categories = {}

        for key, field in self.config_vars.iteritems():
            if key in self._values:
                use_default = False
                value = field.to_primitive(from_string(self._values[key], field))
            else:
                use_default = True
                value = field.to_primitive(field.get_default())
            if '/' in key:
                category, name = key.split('/', 1)
            else:
                category = 'zine'
                name = key
            categories.setdefault(category, []).append({
                'name':         name,
                'field':        field,
                'value':        value,
                'use_default':  use_default
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
        configuration.  This list is safe to share because dangerous keys
        are either hidden or cloaked.
        """
        from zine.application import emit_event
        from zine.database import secure_database_uri
        result = []
        for key, field in self.config_vars.iteritems():
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
                'default':      repr(field.get_default()),
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

        # do not change if we already have the same value.  Otherwise this
        # would override defaulted values.
        if value == self[key]:
            return

        if key.startswith('zine/'):
            key = key[5:]
        if key not in self.cfg.config_vars:
            raise KeyError(key)
        if isinstance(value, str):
            value = value.decode('utf-8')
        field = self.cfg.config_vars[key]
        self._values[key] = field.to_primitive(value)
        self._converted_values[key] = value

    def _assert_uncommitted(self):
        if self._committed:
            raise ValueError('This transaction was already committed.')

    def set_from_string(self, key, value, override=False):
        """Set the value for a key from a string."""
        self._assert_uncommitted()
        if key.startswith('zine/'):
            key = key[5:]
        field = self.cfg.config_vars[key]
        new = from_string(value, field)
        old = self._converted_values.get(key, None) or self.cfg[key]
        if override or field.to_primitive(old) != field.to_primitive(new):
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
            zine_section = sections.pop('zine')
            sections = [('zine', zine_section)] + sorted(sections.items())
            for section in sections:
                section[1].sort()

            try:
                f = file(self.cfg.filename, 'w')
                try:
                    for idx, (section, items) in enumerate(sections):
                        if '[%s]' % section in self.cfg._comments:
                            f.write(self.cfg._comments['[%s]' % section])
                        elif idx:
                            f.write('\n')
                        f.write('[%s]\n' % section.encode('utf-8'))
                        for key, value in items:
                            if section != 'zine':
                                ckey = '%s/%s' % (section, key)
                            else:
                                ckey = key
                            if ckey in self.cfg._comments:
                                f.write(self.cfg._comments[ckey])
                            f.write('%s = %s\n' % (key, quote_value(value)))
                    if ' end ' in self.cfg._comments:
                        f.write(self.cfg._comments[' end '])
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
