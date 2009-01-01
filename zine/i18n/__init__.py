# -*- coding: utf-8 -*-
"""
    zine.i18n
    ~~~~~~~~~

    i18n tools for Zine.  This module provides various helpers for
    internationalization.  That is a translation system (with an API,
    compatible to standard gettext), timezone helpers as well as date
    parsing and formatting functions.

    General Architecture
    --------------------

    The i18n system is based on a few general principles.  Internally all
    times are stored in UTC as naive datetime objects (that means no tzinfo
    is present).  The internal language is American English and all text
    information is stored as unicode strings.

    For display strings are translated to the language of the blog and all
    dates as converted to the blog timezone.

    Translations are handled in a gettext inspired way via babel.  The
    translatable strings are stored in POT and PO files but the files
    Zine loads afterwards are stored in pickles rather than MO files.

    The reason for that is that we have to put additional information into
    these files.  Currently that is the information if strings are used on
    the client too.

    As a matter of fact we are using nearly nothing from the original gettext
    library that comes with Python.  Differences in the API are outlined in
    the `Translations` class docstring.

    Translation Workflow
    --------------------

    The extracting of strings (either for Zine core or plugins) is done
    with the `extract-messages` script.  If called without arguments it will
    extract the strings of the core, otherwise the strings of the plugin which
    is specified.  The messages collected are stored in the `messages.pot`
    file in the i18n folder of the core or plugin.

    The actual translations have to be updated by hand with those strings.
    The `update-translations` script will automatically add new strings to
    the po files and try to do fuzzy matching.

    To compile the translations into the pickled catalog files just use
    `compile-translations`.

    New languages are added with `add-translation`.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import os
import cPickle as pickle
import struct
from gettext import NullTranslations
from datetime import datetime
from time import strptime
from weakref import WeakKeyDictionary

from babel import Locale, dates, UnknownLocaleError
from babel.support import Translations as TranslationsBase
from pytz import timezone, UTC
from werkzeug.exceptions import NotFound

import zine
from zine.environment import LOCALE_PATH, LOCALE_DOMAIN, \
     USE_GETTEXT_LOOKUP
from zine.utils import dump_json


__all__ = ['_', 'gettext', 'ngettext', 'lazy_gettext', 'lazy_ngettext']


DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']


_js_translations = WeakKeyDictionary()


def load_core_translations(locale):
    """Load the translation for a locale.  If a locale does not exist
    the return value a fake translation object.  If the locale is unknown
    a `UnknownLocaleError` is raised.

    This only loads the translations for Zine itself and not the
    plugins.  Plugins themselves have an attribute translations that is
    the translations object pointing to the active translations of the
    plugin.

    The application code combines them into one translations object.
    """
    return ZineTranslations.load(LOCALE_PATH, locale, LOCALE_DOMAIN,
                                 USE_GETTEXT_LOOKUP)


class _CustomAttrsTranslations(object):
    _info = None
    _plural_expr = None

    def _get_plural_expr(self):
        if not self._plural_expr:
            self._plural_expr = self._info.get(
                'plural-forms', 'nplurals=2; plural=(n != 1)'
            ).split(';')[1].strip()[len('plural='):]
        return self._plural_expr

    def _set_plural_expr(self, plural_expr):
        self._plural_expr = plural_expr

    plural_expr = property(_get_plural_expr, _set_plural_expr)
    del _get_plural_expr, _set_plural_expr


class ZineTranslations(TranslationsBase, _CustomAttrsTranslations):

    def __init__(self, fileobj=None, locale=None):
        self.client_keys = set()
        self.locale = locale
        TranslationsBase.__init__(self, fileobj=fileobj)

    def _parse(self, fileobj):
        TranslationsBase._parse(self, fileobj)
        try:
            # Got the end of file minus 4 bytes 
            fileobj.seek(-4, 2)
            # Read stored pickled data file pointer position
            pickled_data_pointer_pos = struct.unpack('i', fileobj.read())
            fileobj.seek(pickled_data_pointer_pos[0])
            # Load pickled data
            self.client_keys.update(pickle.load(fileobj))
        except EOFError:
            # Catalog does not contain any pickled data at the end of it
            pass

    @classmethod
    def load(cls, path, locale=None, domain='messages',
             gettext_lookup=False):
        """Load the translations from the given path."""
        locale = Locale.parse(locale)
        catalog = find_catalog(path, domain, locale, gettext_lookup)
        if catalog:
            return ZineTranslations(fileobj=open(catalog), locale=locale)
        return ZineNullTranslations(locale=locale)

    # Always use the unicode versions, we don't support byte strings
    gettext = TranslationsBase.ugettext
    ngettext = TranslationsBase.ungettext

    def __nonzero__(self):
        return bool(self._catalog)


class ZineNullTranslations(NullTranslations, _CustomAttrsTranslations):

    def __init__(self, fileobj=None, locale=None):
        NullTranslations.__init__(self, fileobj)
        self.locale = locale
        self.client_keys = set()

    def merge(self, translations):
        """Update the translations with others."""
        self.add_fallback(translations)
        self.client_keys.update(translations.client_keys)

    def __nonzero__(self):
        return bool(self._fallback)


def get_translations():
    """Get the active translations or `None` if there are none."""
    try:
        return zine.application.get_application().translations
    except AttributeError:
        return None


def find_catalog(path, domain, locale, gettext_lookup=False):
    """Finds the catalog for the given locale on the path.  Return sthe
    filename of the .mo file if found, otherwise `None` is returned.
    """
    args = [path, str(Locale.parse(locale)), domain + '.mo']
    if gettext_lookup:
        args.insert(-1, 'LC_MESSAGES')
    catalog = os.path.join(*args)
    if os.path.isfile(catalog):
        return catalog


def gettext(string):
    """Translate a given string to the language of the application."""
    translations = get_translations()
    if translations is None:
        return unicode(string)
    return translations.gettext(string)


def ngettext(singular, plural, n):
    """Translate the possible pluralized string to the language of the
    application.
    """
    translations = get_translations()
    if translations is None:
        if n == 1:
            return unicode(singular)
        return unicode(plural)
    return translations.ngettext(singular, plural, n)


class _TranslationProxy(object):
    """Class for proxy strings from gettext translations.  This is a helper
    for the lazy_* functions from this module.

    The proxy implementation attempts to be as complete as possible, so that
    the lazy objects should mostly work as expected, for example for sorting.
    """
    __slots__ = ('_func', '_args')

    def __init__(self, func, *args):
        self._func = func
        self._args = args

    value = property(lambda x: x._func(*x._args))

    def __contains__(self, key):
        return key in self.value

    def __nonzero__(self):
        return bool(self.value)

    def __dir__(self):
        return dir(unicode)

    def __iter__(self):
        return iter(self.value)

    def __len__(self):
        return len(self.value)

    def __str__(self):
        return str(self.value)

    def __unicode__(self):
        return unicode(self.value)

    def __add__(self, other):
        return self.value + other

    def __radd__(self, other):
        return other + self.value

    def __mod__(self, other):
        return self.value % other

    def __rmod__(self, other):
        return other % self.value

    def __mul__(self, other):
        return self.value * other

    def __rmul__(self, other):
        return other * self.value

    def __lt__(self, other):
        return self.value < other

    def __le__(self, other):
        return self.value <= other

    def __eq__(self, other):
        return self.value == other

    def __ne__(self, other):
        return self.value != other

    def __gt__(self, other):
        return self.value > other

    def __ge__(self, other):
        return self.value >= other

    def __getattr__(self, name):
        if name == '__members__':
            return self.__dir__()
        return getattr(self.value, name)

    def __getstate__(self):
        return self._func, self._args

    def __setstate__(self, tup):
        self._func, self._args = tup

    def __getitem__(self, key):
        return self.value[key]

    def __copy__(self):
        return self

    def __repr__(self):
        try:
            return 'i' + repr(unicode(self.value))
        except:
            return '<%s broken>' % self.__class__.__name__


def lazy_gettext(string):
    """A lazy version of `gettext`."""
    if isinstance(string, _TranslationProxy):
        return string
    return _TranslationProxy(gettext, string)


def lazy_ngettext(singular, plural, n):
    """A lazy version of `ngettext`"""
    return _TranslationProxy(ngettext, singular, plural, n)


def per_language_string(en, **languages):
    """Returns a lazy string that returns the string for the current language
    of the application without looking up in the translations but the strings
    provided as keyword arguments.  The default language (english) can be
    specified as first argument.

    Here an example:

    >>> per_language_string('yes', de='ja', it='si')
    iu'yes'

    This should not be used for arbitrary translations but language depending
    strings such as configuration variables that do not represent text.

    An example could be quotes for different languages:

    >>> per_language_string(u'\u201c', de=u'\u201e')
    iu'\u201c'
    """
    def lookup():
        app = zine.application.get_application()
        lang = app and app.cfg['language'] or 'en'
        if lang in languages:
            return languages[lang]
        return languages['en']
    languages['en'] = en
    return _TranslationProxy(lookup)


def to_blog_timezone(datetime):
    """Convert a datetime object to the blog timezone."""
    if datetime.tzinfo is None:
        datetime = datetime.replace(tzinfo=UTC)
    tzinfo = get_timezone()
    return tzinfo.normalize(datetime.astimezone(tzinfo))


def to_utc(datetime):
    """Convert a datetime object to UTC and drop tzinfo."""
    if datetime.tzinfo is None:
        datetime = get_timezone().localize(datetime)
    return datetime.astimezone(UTC).replace(tzinfo=None)


def format_datetime(datetime=None, format='medium', rebase=True):
    """Return a date formatted according to the given pattern."""
    return _date_format(dates.format_datetime, datetime, format, rebase)


def format_system_datetime(datetime=None, rebase=True):
    """Formats a system datetime.  This is the format the admin
    panel uses by default.  (Format: YYYY-MM-DD hh:mm and in the
    user timezone unless rebase is disabled)
    """
    if rebase:
        datetime = to_blog_timezone(datetime)
    return u'%d-%02d-%02d %02d:%02d' % (
        datetime.year,
        datetime.month,
        datetime.day,
        datetime.hour,
        datetime.minute
    )


def format_date(date=None, format='medium', rebase=True):
    """Return the date formatted according to the pattern.  Rebasing only
    works for datetime objects passed to this function obviously.
    """
    if rebase and isinstance(date, datetime):
        date = to_blog_timezone(date)
    return _date_format(dates.format_date, date, format, rebase)


def format_month(date=None):
    """Format month and year of a date."""
    return format_date(date, 'MMMM YYYY')


def format_time(time=None, format='medium', rebase=True):
    """Return the time formatted according to the pattern."""
    return _date_format(dates.format_time, time, format, rebase)


def format_timedelta(datetime_or_timedelta, granularity='second'):
    """Format the elapsed time from the given date to now of the given
    timedelta.
    """
    if isinstance(datetime_or_timedelta, datetime):
        datetime_or_timedelta = datetime.utcnow() - datetime_or_timedelta
    return dates.format_timedelta(datetime_or_timedelta, granularity,
                                  locale=get_locale())


def list_timezones():
    """Return a list of all timezones."""
    from pytz import common_timezones
    # XXX: translate
    result = [(x, x.replace('_', ' ')) for x in common_timezones]
    result.sort(key=lambda x: x[1].lower())
    return result


def list_languages(self_translated=True):
    """Return a list of all languages."""
    if self_translated:
        locale = get_locale()
    else:
        locale = None

    found = set(['en'])
    languages = [('en', Locale('en').get_display_name())]

    for locale in os.listdir(LOCALE_PATH):
        try:
            l = Locale.parse(locale)
        except (ValueError, UnknownLocaleError):
            continue
        if str(l) not in found and \
           find_catalog(LOCALE_PATH, LOCALE_DOMAIN, l,
                        USE_GETTEXT_LOOKUP) is not None:
            languages.append((str(l), l.get_display_name()))
            found.add(str(l))

    languages.sort(key=lambda x: x[1].lower())
    return languages


def has_language(language):
    """Check if a language exists."""
    return language in dict(list_languages())


def has_timezone(tz):
    """When pased a timezone as string this function checks if
    the timezone is know.
    """
    try:
        timezone(tz)
    except:
        return False
    return True


def parse_datetime(string, rebase=True):
    """Parses a string into a datetime object.  Per default a conversion
    from the blog timezone to UTC is performed but returned as naive
    datetime object (that is tzinfo being None).  If rebasing is disabled
    the string is expected in UTC.

    The return value is **always** a naive datetime object in UTC.  This
    function should be considered of a lenient counterpart of
    `format_system_datetime`.
    """
    # shortcut: string as None or "now" or the current locale's
    # equivalent returns the current timestamp.
    if string is None or string.lower() in ('now', _('now')):
        return datetime.utcnow().replace(microsecond=0)

    def convert(format):
        """Helper that parses the string and convers the timezone."""
        rv = datetime(*strptime(string, format)[:7])
        if rebase:
            rv = to_utc(rv)
        return rv.replace(microsecond=0)
    cfg = zine.application.get_application().cfg

    # first of all try the following format because this is the format
    # Texpress will output by default for any date time string in the
    # administration panel.
    try:
        return convert(u'%Y-%m-%d %H:%M')
    except ValueError:
        pass

    # no go with time only, and current day
    for fmt in TIME_FORMATS:
        try:
            val = convert(fmt)
        except ValueError:
            continue
        return to_utc(datetime.utcnow().replace(hour=val.hour,
                      minute=val.minute, second=val.second, microsecond=0))

    # no try various types of date + time strings
    def combined():
        for t_fmt in TIME_FORMATS:
            for d_fmt in DATE_FORMATS:
                yield t_fmt + ' ' + d_fmt
                yield d_fmt + ' ' + t_fmt

    for fmt in combined():
        try:
            return convert(fmt)
        except ValueError:
            pass

    raise ValueError('invalid date format')


def _date_format(formatter, obj, format, rebase, **extra):
    """Internal helper that formats the date."""
    locale = get_locale()
    extra = {}
    if formatter is not dates.format_date and rebase:
        extra['tzinfo'] = get_timezone()
    return formatter(obj, format, locale=locale, **extra)


def get_timezone(name=None):
    """Return the timezone for the given identifier or the timezone
    of the application based on the configuration.
    """
    if name is None:
        name = zine.application.get_application().cfg['timezone']
    return timezone(name)


def get_locale():
    """Return the current locale."""
    app = zine.application.get_application()
    if app is None:
        return Locale('en')
    return app.locale


def serve_javascript(request):
    """Serves the JavaScript translations."""
    code = _js_translations.get(request.app)
    if code is None:
        t = request.app.translations
        code = 'Zine.addTranslations(%s)' % dump_json(dict(
            messages=dict((k.id, k.string) for k in t.client_keys),
            plural_expr=t.plural_expr,
            locale=str(t.locale)
        ))
        _js_translations[request.app] = code
    response = zine.application.Response(code, mimetype='application/javascript')
    response.add_etag()
    response.make_conditional(request)
    return response


_ = gettext
