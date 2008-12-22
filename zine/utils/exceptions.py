# -*- coding: utf-8 -*-
"""
    zine.utils.exceptions
    ~~~~~~~~~~~~~~~~~~~~~

    Exception utility module.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from zine.i18n import _


class ZineException(Exception):
    """Baseclass for all Zine exceptions."""
    message = None

    def __init__(self, message=None):
        Exception.__init__(self)
        if message is not None:
            self.message = message

    def __str__(self):
        return self.message or ''

    def __unicode__(self):
        return str(self).decode('utf-8', 'ignore')


class UserException(ZineException):
    """Baseclass for exception with unicode messages."""

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        if self.message is None:
            return u''
        return unicode(self.message)


def summarize_exception(exc_info):
    def _to_unicode(x):
        try:
            return unicode(x)
        except UnicodeError:
            return str(x).encode('utf-8', 'replace')

    exc_type, exc_value, tb = exc_info
    if isinstance(exc_type, basestring):
        prefix = _to_unicode(exc_type)
    else:
        prefix = _to_unicode(exc_type.__name__)
    message = _to_unicode(exc_value)

    location = (None, None)
    filename = tb.tb_frame.f_globals.get('__file__')
    if filename is None:
        filename = _(u'unkown file')
    else:
        filename = _to_unicode(filename)
        if filename.endswith('.pyc'):
            filename = filename[:-1]

    return u'%s: %s' % (prefix, message), (filename, tb.tb_lineno)
