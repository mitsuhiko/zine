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


def format_datetime(datetime=None, format='medium', rebase=True):
    """Return a date formatted according to the given pattern."""
    return _date_format(dates.format_datetime, datetime, format, rebase)


def format_system_datetime(datetime=None, rebase=True):
    """Formats a system datetime.  This is the format the admin
    panel uses by default.  (Format: YYYY-MM-DD hh:mm and in the
    user timezone unless rebase is disabled)
    """
    if rebase:
        if datetime.tzinfo is None:
            datetime = datetime.replace(tzinfo=UTC)
        datetime = datetime.astimezone(get_timezone())
    return u'%d-%02d-%02d %02d:%02d' % (
        datetime.year,
        datetime.month,
        datetime.day,
        datetime.hour,
        datetime.minute
    )


def format_date(date=None, format='medium', rebase=True):
    """Return the date formatted according to the pattern."""
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
    result = [(x, x) for x in common_timezones]
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
    """
    if string.lower() == _('now'):
        return datetime.utcnow()

    def convert(format):
        rv = datetime(*strptime(string, format)[:7])
        if not rebase:
            return rv
        return rv.replace(tzinfo=UTC).astimezone(get_timezone()) \
                 .replace(tzinfo=None)
    cfg = textpress.application.get_application().cfg

    # first of all try the following format because this is the format
    # Texpress will output by default for any date time string in the
    # administration panel.
    try:
        return convert(u'%Y-%m-%d %H:%M')
    except ValueError:
        pass

    # no go with time only, and current day
    base = datetime.utcnow()
    for fmt in TIME_FORMATS:
        try:
            val = convert(fmt)
        except ValueError:
            continue
        return base.replace(hour=val.hour, minute=val.minute,
                            second=val.second)

    # no try date + time
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
    # a limitation in babel doesn't allow dates being formatted
    # with a timezone information.
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
