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
from babel import Locale, dates, UnknownLocaleError
from babel.support import Translations
from textpress.application import get_application


__all__ = ['_', 'gettext', 'ngettext']


DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']


def load_translations(locale):
    """Load the translation for a locale."""
    return Translations.load(os.path.dirname(__file__), [locale])


def gettext(string):
    """Translate the given string to the language of the application."""
    app = get_application()
    if app is None:
        return string
    return app.translations.ugettext(string)


def ngettext(singular, plural, n):
    """Translate the possible pluralized string to the language of the
    application.
    """
    app = get_application()
    if app is None:
        if n == 1:
            return singular
        return plrual
    return app.translations.ungettext(singular, plural, n)


def format_datetime(datetime=None, format='medium'):
    """Return a date formatted according to the given pattern."""
    return _date_format(dates.format_datetime, datetime, format)


def format_date(date=None, format='medium'):
    """Return the date formatted according to the pattern."""
    return _date_format(dates.format_date, date, format)


def format_month(date=None):
    """Format month and year of a date."""
    return format_date(date, 'MMMM YY')


def format_time(time=None, format='medium'):
    """Return the time formatted according to the pattern."""
    return _date_format(dates.format_time, time, format)


def list_timezones():
    """Return a list of all timezones."""
    from pytz import common_timezones
    # XXX: translate
    result = [(x, x) for x in common_timezones]
    result.sort(key=lambda x: x[1].lower())
    return result


def list_languages():
    """Return a list of all languages."""
    app = get_application()
    if app:
        locale = app.locale
    else:
        locale = Locale('en')

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
    from pytz import timezone
    try:
        timezone(tz)
    except:
        return False
    return True


def parse_datetime(string):
    """Parses a string into a datetime object."""
    if string.lower() == _('now'):
        return datetime.utcnow()
    convert = lambda fmt: datetime(*strptime(string, fmt)[:7])
    cfg = get_application().cfg

    # first of all try the datetime_format because it's likely that
    # the users inputs the date like chosen in the config
    try:
        return convert(cfg['datetime_format'])
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


def _date_format(formatter, obj, format):
    app = get_application()
    if app is None:
        locale = Locale('en')
    else:
        locale = app.locale
    return formatter(obj, format, locale=locale)


_ = gettext
