# -*- coding: utf-8 -*-
"""
    zine.utils.log
    ~~~~~~~~~~~~~~

    This module implements application depending logging.  This logging system
    is optimized for performance and always logs into a special file in the
    instance folder.

    We are not using the python logging system because it registers the loggers
    in a central spot and it's pretty slow.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import re
import sys
from os import path
from datetime import datetime
from inspect import currentframe
from warnings import warn
from traceback import print_exception, format_exception

from werkzeug.exceptions import NotFound

from zine.i18n import gettext
from zine.application import get_application
from zine.utils.io import tail
from zine.utils.dates import format_iso8601, parse_iso8601


_ = lambda x: x
LEVELS = {
    _('critical'):  5,
    _('error'):     4,
    _('warning'):   3,
    _('notice'):    2,
    _('info'):      1,
    _('debug'):     0
}


_log_line_re = re.compile(r'''(?xm)
    ^
        (?P<prefix>
            \[
                (?P<timestamp>.*?)
              - (?P<level>%(level)s)
              - (?P<location>(?:\?|.*?:\d+))
            \] \s*
            (?P<module>.+?):[ ]
        )
        (?P<message>.*)
    $
''' % {
    'level':    '|'.join(LEVELS)
})


class Logger(object):
    """The central logger class that is attached to the application."""

    def __init__(self, logfile, level='warning'):
        self.logfile = logfile
        self._file = None
        self.level = LEVELS.get(level)

        # whoops. wrong level.  fall back to error and log that
        if self.level is None:
            self.level = LEVELS['warning']
            self.log('error', u'Logger configuration got invalid level "%s", '
                     u'fallen back to "warning' % level, 'logger')

    def view(self, per_page=200):
        """Returns a logfile view for the log."""
        return LogfileView(self.logfile, per_page)

    def __del__(self):
        if self._file is not None:
            self._file.close()
            self._file = None

    @property
    def file(self):
        """An open file descriptor for appending.  On reopening the property
        makes sure that file ends with a newline.
        """
        if self._file is None or self._file.closed:
            try:
                self._file = file(self.logfile, 'a+')
            except IOError:
                # grml.  log file not writable.  return a dummy
                return file(os.nulldev, 'w')
            if self._file.tell() > 0:
                self._file.seek(-1, 2)
                char = self._file.read()
                if char != '\n':
                    self._file.write('\n')
        return self._file

    def get_location(self, frame):
        """Returns the location for the frame.  If the location is unknown a
        placeholder string is returned
        """
        if frame is None:
            return u'?'
        return ('%s:%d' % (
            frame.f_globals.get('__name__', frame.f_code.co_name),
            frame.f_lineno
        )).encode('utf-8', 'replace')

    def log(self, level, message, module=None, frame=None):
        """Writes a single log entry to the stream."""
        prefix = (u'[%s-%s-%s] %s: ' % (
            format_iso8601(datetime.utcnow()),
            level,
            self.get_location(frame),
            module or 'unknown'
        )).encode('utf-8')
        for line in message.splitlines():
            self.file.write(prefix + (line + u'\n').encode('utf-8'))
        self.file.flush()


class NoSuchPage(NotFound):
    """That page just does not exist."""


class LogfileItem(object):
    """A single item in the logfile."""

    def __init__(self, timestamp, level, location, module, message=None):
        self.timestamp = parse_iso8601(timestamp)
        self.level = gettext(level)
        self.internal_level = level
        self.location = location
        self.module = module
        self.lines = []
        if message is not None:
            self.lines.append(message)

    @property
    def text(self):
        return u'\n'.join(self.lines)

    @property
    def numeric_level(self):
        return LEVELS.get(self.internal_level, -1)


class LogfilePage(object):
    """A single page in the logfile."""

    def __init__(self, lines, has_next, number):
        self.has_prev = number > 1
        self.number = number
        self.has_next = has_next
        self.items = []

        last_prefix = None
        item = None

        _parse_line = _log_line_re.match
        for line in lines:
            match = _parse_line(line.decode('utf-8', 'replace'))
            # trash in the logfile :-/
            if match is None:
                continue
            d = match.groupdict()

            # continuation of the same item
            if d['prefix'] == last_prefix:
                item.lines.append(d['message'])
            # whoosh. a new item
            else:
                last_prefix = d.pop('prefix')
                item = LogfileItem(**d)
                self.items.append(item)


class LogfileView(object):
    """A read only view to the logfile."""

    def __init__(self, filename, per_page=100):
        self.filename = filename
        self.per_page = per_page

    def get_page(self, number):
        """Return a single page from the log."""
        if not path.exists(self.filename):
            lines = []
            has_more = False
        else:
            f = file(self.filename)
            try:
                lines, has_more = tail(f, self.per_page,
                                       self.per_page * (number - 1))
            finally:
                f.close()
        if not lines and number != 1:
            raise NoSuchPage()
        return LogfilePage(lines, has_more, number)


class UnboundLogging(Warning):
    """Warning for unbound logging."""


def _logging_func(name):
    level = LEVELS[name]
    def log(message, module=None):
        try:
            logger = get_application().log
        except AttributeError:
            warn(UnboundLogging('Tried to log %r but no application '
                                'was bound to the calling thread'
                                % message), stacklevel=2)
            return
        if level >= logger.level:
            logger.log(name, message, module, currentframe(1))
    log.__name__ = name
    return log


def exception(message=None, module=None, exc_info=None):
    """Logs an error plus the current or given exc info."""
    if exc_info is None:
        exc_info = sys.exc_info()
    try:
        logger = get_application().log
    except AttributeError:
        # no application, write the exception to stderr
        return print_exception(*exc_info)

    if LEVELS['error'] >= logger.level:
        message = (message and message + '\n' or '') + \
                  ''.join(format_exception(*exc_info)) \
                    .decode('utf-8', 'ignore')
        logger.log('error', message, module, currentframe(1))


# make a bunch of loggers
__all__ = list(LEVELS)
globals().update((k, _logging_func(k)) for k in LEVELS)
del _logging_func
