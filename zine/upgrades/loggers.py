"""
    zine.upgrades.loggers
    ~~~~~~~~~~~~~~~~~~~~~

    This package implements the required loggers for cli and web migrations.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import os
import types
import logging
from logging.handlers import BufferingHandler

def getTerminalSize():
    # From http://stackoverflow.com/questions/566746/how-to-get-console-window-width-in-python
    def ioctl_GWINSZ(fd):
        try:
            import fcntl, termios, struct
            cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ,
        '1234'))
        except:
            return None
        return cr
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except:
            pass
    if not cr:
        try:
            cr = (os.environ['LINES'], os.environ['COLUMNS'])
        except:
            cr = (25, 80)
    return int(cr[1]), int(cr[0])


class LogFormatter(logging.Formatter):
    def format(self, record):
        """
        Format the specified record as text.

        The record's attribute dictionary is used as the operand to a
        string formatting operation which yields the returned string.
        Before formatting the dictionary, a couple of preparatory steps
        are carried out. The message attribute of the record is computed
        using LogRecord.getMessage(). If the formatting string contains
        "%(asctime)", formatTime() is called to format the event time.
        If there is exception information, it is formatted using
        formatException() and appended to the message.
        """
        record.message = record.getMessage()
#        if string.find(self._fmt,"%(asctime)") >= 0:
#            record.asctime = self.formatTime(record, self.datefmt)
        s = self._fmt % record.__dict__
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            s = s + record.exc_text
        from zine.utils.zeml import parse_html
        trailing_new_line = s and s.endswith('\n') or False
        s = parse_html(s).to_text(simple=True, max_width=getTerminalSize()[0])
        if s and s.endswith('\n\n') and trailing_new_line:
            s = s[:-1]
        elif s and s.endswith('\n') and not trailing_new_line:
            s = s.rstrip('\n')
        return s

class CliLogHandler(logging.StreamHandler):
    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        The record is then written to the stream with a trailing newline
        [N.B. this may be removed depending on feedback]. If exception
        information is present, it is formatted using
        traceback.print_exception and appended to the stream.
        """
        try:
            msg = self.format(record)
#            fs = "%s\n"
            fs = '%s'
            if not hasattr(types, "UnicodeType"): #if no unicode support...
                self.stream.write(fs % msg)
            else:
                try:
                    self.stream.write(fs % msg)
                except UnicodeError:
                    self.stream.write(fs % msg.encode("UTF-8"))
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

class WebLogHandler(BufferingHandler):
    def __init__(self):
        BufferingHandler.__init__(self, -1)

    def shouldFlush(self, record):
        # We force it to never flush. We'll explicitly do the flushing
        return (len(self.buffer) < self.capacity)
