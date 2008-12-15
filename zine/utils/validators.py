"""
    zine.utils.validators
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements various functions for validation of miscellaneous
    things, e.g. urls.

    TODO: convert most of the functions in this module into functions that
          raise `forms.ValidationError`\s.  They are used in hand validated
          forms currently which should be replaced by real forms soon.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import re
from urlparse import urlparse

from zine.i18n import lazy_gettext, _


_mail_re = re.compile(r'''(?xi)
    (?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+
        (?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|
        "(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|
          \\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@.
''')


class ValidationError(ValueError):
    """Exception raised when invalid data is encountered."""

    def __init__(self, message):
        if not isinstance(message, (list, tuple)):
            messages = [message]
        # make all items in the list unicode (this also evaluates
        # lazy translations in there)
        messages = map(unicode, messages)
        Exception.__init__(self, messages[0])

        from zine.utils.forms import ErrorList
        self.messages = ErrorList(messages)

    def unpack(self, key=None):
        return {key: self.messages}


def check(validator, value, *args, **kwargs):
    """Call a validator and return True if it's valid, False otherwise.
    The first argument is the validator, the second a value.  All other
    arguments are forwarded to the validator function.

    >>> check(is_valid_email, 'foo@bar.com')
    True
    """
    try:
        validator(*args, **kwargs)(None, value)
    except ValidationError:
        return False
    return True


def is_valid_email(message=None):
    """Check if the string passed is a valid mail address.

    >>> check(is_valid_email, 'somebody@example.com')
    True
    >>> check(is_valid_email, 'somebody AT example DOT com')
    False
    >>> check(is_valid_email, 'some random string')
    False

    Because e-mail validation is painfully complex we just check the first
    part of the email if it looks okay (comments are not handled!) and ignore
    the second.
    """
    if message is None:
        message = lazy_gettext(u'You have to enter a valid e-mail address.')
    def validator(form, value):
        if len(value) > 250 or _mail_re.match(value) is None:
            raise ValidationError(message)
    return validator


def is_valid_url(message=None):
    """Check if the string passed is a valid URL.  We also blacklist some
    url schemes like javascript for security reasons.

    >>> check(is_valid_url, 'http://pocoo.org/')
    True
    >>> check(is_valid_url, 'http://zine.pocoo.org/archive')
    True
    >>> check(is_valid_url, 'zine.pocoo.org/archive')
    False
    >>> check(is_valid_url, 'javascript:alert("Zine rocks!");')
    False
    """
    if message is None:
        message = lazy_gettext(u'You have to enter a valid URL.')
    def validator(form, value):
        protocol = urlparse(value)[0]
        if not protocol or protocol == 'javascript':
            raise ValidationError(message)
    return validator


def is_valid_slug(allow_slash=True):
    """Check if the value given is a valid slug:

    >>> check(is_valid_slug, '/foo')
    False
    >>> check(is_valid_slug, 'foo/bar')
    True
    >>> check(is_valid_slug, '<foo>')
    False
    """
    def validator(form, value):
        if len(value) > 200:
            raise ValidationError(_(u'The slug is too long'))
        elif value.startswith('/'):
            raise ValidationError(_(u'The slug must not start with a slash'))
    return validator


def is_netaddr():
    """Checks if the string given is a net address.  Either an IP or a
    hostname.  This currently does not support ipv6 (XXX!!)

    >>> check(is_netattr, 'localhost')
    True
    >>> check(is_netaddr, 'localhost:443')
    True
    >>> check(is_netaddr, 'just something else')
    False
    """
    def validator(form, value):
        items = value.split()
        if len(items) > 1:
            raise ValidationError(_(u'You have to enter a valid net address.'))
        items = items[0].split(':')
        if len(items) != 2:
            raise ValidationError(_(u'You have to enter a valid net address.'))
        elif not items[1].isdigit():
            raise ValidationError(_(u'The port has to be nummeric'))
    return validator


def is_valid_url_prefix():
    """Validates URL parts."""
    def validator(form, value):
        if '<' in value or '>' in value:
            raise ValidationError(_(u'Invalid character, < or > are not allowed.'))
        if value == '/':
            raise ValidationError(_(u'URL prefix must not be a sole slash.'))
        if value:
            if value[:1] != '/':
                raise ValidationError(_(u'URL prefix must start with a slash.'))
            if value[-1:] == '/':
                raise ValidationError(_(u'URL prefix must not end with a slash.'))
    return validator
