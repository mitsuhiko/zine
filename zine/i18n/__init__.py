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
    :license: GNU GPL.
"""
import os
import cPickle as pickle
from gettext import c2py
from datetime import datetime
from time import strptime
from weakref import WeakKeyDictionary

from babel import Locale, dates, UnknownLocaleError
from babel.support import Translations as TranslationsBase
from pytz import timezone, UTC
from werkzeug.exceptions import NotFound

import zine.application
from zine.environment import LOCALE_PATH
from zine.utils import dump_json


__all__ = ['_', 'gettext', 'ngettext', 'lazy_gettext', 'lazy_ngettext']


DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']


_js_translations = WeakKeyDictionary()


def load_translations(locale):
    """Load the translation for a locale.  If a locale does not exist
    the return value a fake translation object.  If the locale is unknown
    a `UnknownLocaleError` is raised.

    This only loads the translations for Zine itself and not the
    plugins.  Plugins themselves have an attribute translations that is
    the translations object pointing to the active translations of the
    plugin.

    The application code combines them into one translations object.
    """
    return Translations.load(LOCALE_PATH, locale)


class Translations(object):
    """A gettext like API for Zine."""

    def __init__(self, catalog=None, locale=None):
        if locale is not None:
            locale = Locale.parse(locale)
        self.locale = locale
        if catalog is None:
            self.messages = {}
            self.client_keys = set()
            self.plural_func = lambda n: int(n != 1)
            self.plural_expr = '(n != 1)'
        else:
            close = False
            if isinstance(catalog, basestring):
                catalog = file(catalog, 'rb')
                close = True
            try:
                dump = pickle.load(catalog)
                self.messages = dump['messages']
                self.client_keys = dump['client_keys']
                self.plural_func = c2py(dump['plural'])
                self.plural_expr = dump['plural']
            finally:
                if close:
                    catalog.close()
        self._lookup = self.messages.get

    def __nonzero__(self):
        return bool(self.messages)

    def gettext(self, string):
        msg = self._lookup(string)
        if msg is None:
            return unicode(string)
        elif msg.__class__ is tuple:
            return msg[0]
        return msg

    def ngettext(self, singular, plural, n):
        msgs = self._lookup(singular)
        if msgs is None or msgs.__class__ is not tuple:
            if n == 1:
                return unicode(singular)
            return unicode(plural)
        return msgs[self.plural_func(n)]

    # unicode aliases for gettext compatibility.  Jinja for example
    # will try to use those.
    ugettext = gettext
    ungettext = ngettext

    def merge(self, translations):
        """Update the translations with others."""
        self.messages.update(translations.messages)
        self.client_keys.update(translations.client_keys)

    @classmethod
    def load(cls, path, locale, domain='messages'):
        """Looks for .catalog files in the path provided in a gettext
        inspired manner.

        If there are no translations an empty locale is returned.
        """
        locale = Locale.parse(locale)
        catalog = os.path.join(path, str(locale), domain + '.catalog')
        if os.path.isfile(catalog):
            return Translations(catalog, locale)
        return Translations(locale=locale)


def gettext(string):
    """Translate the given string to the language of the application."""
    app = zine.application.get_application()
    if app is None:
        return unicode(string)
    return app.translations.gettext(string)


def ngettext(singular, plural, n):
    """Translate the possible pluralized string to the language of the
    application.
    """
    app = zine.application.get_application()
    if app is None:
        if n == 1:
            return unicode(singular)
        return unicode(plural)
    return app.translations.ngettext(singular, plural, n)


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

    def __getitem__(self, key):
        return self.value[key]

    def __repr__(self):
        try:
            return 'i' + repr(unicode(self.value))
        except:
            return '<%s broken>' % self.__class__.__name__


def lazy_gettext(string):
    """A lazy version of `gettext`."""
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


def list_languages(self_translated=False):
    """Return a list of all languages."""
    if not self_translated:
        locale = get_locale()
    else:
        locale = None

    languages = [('en', Locale('en').get_display_name())]

    for filename in os.listdir(LOCALE_PATH):
        if filename == 'en' or not \
           os.path.isfile(os.path.join(LOCALE_PATH, filename,
                                       'messages.catalog')):
            continue
        try:
            l = Locale.parse(filename)
        except UnknownLocaleError:
            continue
        languages.append((str(l), l.get_display_name()))

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
            messages=dict((k, t.messages[k]) for k in t.client_keys),
            plural_expr=t.plural_expr,
            locale=str(t.locale)
        ))
        _js_translations[request.app] = code
    response = zine.application.Response(code, mimetype='application/javascript')
    response.add_etag()
    response.make_conditional(request)
    return response


_ = gettext
