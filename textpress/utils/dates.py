"""
    textpress.utils.dates
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements date formatting and parsing functions.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import re
from datetime import datetime, timedelta


# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules is crap)
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)


def parse_iso8601(value):
    """Parse an iso8601 date into a datetime object.
    The timezone is normalized to UTC, we always use UTC objects
    internally.
    """
    m = _iso8601_re.match(value)
    if m is None:
        raise ValueError('not a valid iso8601 date value')

    groups = m.groups()
    args = []
    for group in groups[:-2]:
        if group is not None:
            group = int(group)
        args.append(group)
    seconds = groups[-2]
    if seconds is not None:
        if '.' in seconds:
            args.extend(map(int, seconds.split('.')))
        else:
            args.append(int(seconds))

    rv = datetime(*args)
    tz = groups[-1]
    if tz and tz != 'Z':
        args = map(int, tz[1:].split(':'))
        delta = timedelta(hours=args[0], minutes=args[1])
        if tz[0] == '+':
            rv += delta
        else:
            rv -= delta

    return rv


def format_iso8601(obj):
    """Format a datetime object for iso8601"""
    return obj.strftime('%Y-%m-%dT%H:%M:%SZ')
