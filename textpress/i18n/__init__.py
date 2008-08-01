# -*- coding: utf-8 -*-
"""
    textpress.i18n
    ~~~~~~~~~~~~~~

    i18n tools for TextPress.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
from datetime import datetime
from time import strptime
from babel import Locale, dates, UnknownLocaleError
from babel.support import Translations
from pytz import timezone, UTC
from werkzeug.exceptions import NotFound
import textpress.application


__all__ = ['_', 'gettext', 'ngettext']


DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']


#: loaded javascript catalogs
_js_catalogs = {}


def load_translations(locale):
    """Load the translation for a locale."""
    return Translations.load(os.path.dirname(__file__), [locale])


def gettext(string):
    """Translate the given string to the language of the application."""
    app = textpress.application.get_application()
    if app is None:
        return string
    return app.translations.ugettext(string)


def ngettext(singular, plural, n):
    """Translate the possible pluralized string to the language of the
    application.
    """
    app = textpress.application.get_application()
    if app is None:
        if n == 1:
            return singular
        return plrual
    return app.translations.ungettext(singular, plural, n)


def to_user_timezone(datetime):
    """Convert a datetime object to the user timezone."""
    if datetime.tzinfo is None:
        datetime = datetime.replace(tzinfo=UTC)
    tzinfo = get_timezone()
    return tzinfo.normalize(datetime.astimezone(tzinfo))


def to_utc(datetime, tzinfo=None):
    """Convert a datetime object to UTC and drop tzinfo."""
    if tzinfo is not None:
        datetime = tzinfo.localize(datetime)
    elif datetime.tzinfo is None:
        return datetime
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
        datetime = to_user_timezone(datetime)
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
        date = to_user_timezone(date)
    return _date_format(dates.format_date, date, format, rebase)


def format_month(date=None):
    """Format month and year of a date."""
    return format_date(date, 'MMMM YY')


def format_time(time=None, format='medium', rebase=True):
    """Return the time formatted according to the pattern."""
    return _date_format(dates.format_time, time, format, rebase)


def list_timezones():
    """Return a list of all timezones."""
    from pytz import common_timezones
    # XXX: translate
    result = [(x, x.replace('_', ' ')) for x in common_timezones]
    result.sort(key=lambda x: x[1].lower())
    return result


def list_languages(locale=None):
    """Return a list of all languages."""
    if locale is None:
        app = textpress.application.get_application()
        if app:
            locale = app.locale
        else:
            locale = Locale('en')
    else:
        locale = Locale.parse(locale)

    languages = [('en', Locale('en').get_display_name(locale))]
    folder = os.path.dirname(__file__)

    for filename in os.listdir(folder):
        if filename == 'en' or not \
           os.path.isdir(os.path.join(folder, filename)):
            continue
        try:
            l = Locale.parse(filename)
        except UnknownLocaleError:
            continue
        languages.append((str(l), l.get_display_name(locale)))

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
            return to_utc(rv, get_timezone())
        return rv
    cfg = textpress.application.get_application().cfg

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
                      minute=val.minute, second=val.second, microsecond=0),
                      get_timezone())

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
    app = textpress.application.get_application()
    if app is None:
        locale = Locale('en')
    else:
        locale = app.locale
    extra = {}
    if formatter is not dates.format_date and rebase:
        extra['tzinfo'] = get_timezone()
    return formatter(obj, format, locale=locale, **extra)


def get_timezone(name=None):
    """Return the timezone for the given identifier or the timezone
    of the application based on the configuration.
    """
    if name is None:
        name = textpress.application.get_application().cfg['timezone']
    return timezone(name)


def serve_javascript_translation(request, locale):
    """Serves the JavaScript translation file for a locale."""
    if locale in _js_catalogs:
        data = _js_catalogs[locale]
    else:
        try:
            l = Locale.parse(locale)
        except UnknownLocaleError:
            raise NotFound()
        filename = os.path.join(os.path.dirname(__file__), str(l),
                                'LC_MESSAGES', 'messages.js')
        if not os.path.isfile(filename):
            data = ''
        else:
            f = file(filename)
            try:
                data = _js_catalogs[locale] = f.read().decode('utf-8')
            finally:
                f.close()
    response = textpress.application.Response(data, mimetype='application/javascript')
    response.add_etag()
    response.make_conditional(request)
    return response


_ = gettext
