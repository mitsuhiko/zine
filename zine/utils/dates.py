"""
    zine.utils.dates
    ~~~~~~~~~~~~~~~~

    This module implements date formatting and parsing functions.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
from calendar import timegm
from datetime import datetime, timedelta, timezone


# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules is crap)
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)


def utcnow():
    """Return the current UTC time in Zine's naive internal format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcfromtimestamp(timestamp):
    """Convert a timestamp to Zine's naive internal UTC format."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)


def to_timestamp(value):
    """Converts a datetime to an unix timestamp."""
    return timegm(value.timetuple())


def parse_iso8601(value):
    """Parse an iso8601 date into a datetime object.
    The timezone is normalized to UTC, we always use UTC objects
    internally.
    """
    m = _iso8601_re.match(value)
    if m is None:
        raise ValueError('not a valid iso8601 date value')

    year, month, day, hour, minute, seconds, tz = m.groups()
    second = microsecond = 0
    if seconds is not None:
        whole, dot, fraction = seconds.partition('.')
        second = int(whole)
        if dot:
            microsecond = int((fraction + '000000')[:6])
    rv = datetime(
        int(year), int(month or 1), int(day or 1),
        int(hour or 0), int(minute or 0), second, microsecond,
    )
    if tz and tz != 'Z':
        args = list(map(int, tz[1:].split(':')))
        delta = timedelta(hours=args[0], minutes=args[1])
        if tz[0] == '+':
            rv -= delta
        else:
            rv += delta

    return rv


def format_iso8601(obj):
    """Format a datetime object for ISO 8601 in UTC."""
    if obj.tzinfo is not None:
        obj = obj.astimezone(timezone.utc).replace(tzinfo=None)
    if obj.microsecond:
        return obj.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    return obj.strftime('%Y-%m-%dT%H:%M:%SZ')
