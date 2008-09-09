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
from urlparse import urlparse, urljoin, urlsplit

from zine.i18n import _


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


def check_external_url(app, url, check=False):
    """Check if a URL is on the application server."""
    blog_url = app.cfg['blog_url']
    check = urljoin(blog_url, url)

    if check:
        # check if the url is on the same server
        # as configured
        c1 = urlsplit(blog_url)[:2]
        c2 = urlsplit(check)[:2]
        if c1 != c2:
            raise ValueError('The url %s is not on the same server'
                             'as configured. Please notify the administrator'
                             % check)
    return check


def check(validator, value, form=None):
    """Call a validator and return True if it's valid, False otherwise:

    >>> check(is_valid_email, 'foo@bar.com')
    True
    """
    try:
        validator(form, value)
    except ValidationError:
        return False
    return True


def is_valid_email(form, mail):
    """Check if the string passed is a valid mail address.

    >>> is_valid_email('somebody@example.com')
    True
    >>> is_valid_email('somebody AT example DOT com')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid e-mail address.
    >>> is_valid_email('some random string')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid e-mail address.

    Because e-mail validation is painfully complex we just check the first
    part of the email if it looks okay (comments are not handled!) and ignore
    the second.
    """
    if len(email) > 250 or _mail_re.match(email) is None:
        raise ValidationError(_('You have to enter a valid e-mail address.'))


def is_valid_url(form, url):
    """Check if the string passed is a valid URL.  We also blacklist some
    url schemes like javascript for security reasons.

    >>> is_valid_url(None, 'http://pocoo.org/')
    >>> is_valid_url(None, 'http://zine.pocoo.org/archive')
    >>> is_valid_url(None, 'zine.pocoo.org/archive')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid URL.
    >>> is_valid_url(None, 'javascript:alert("Zine rocks!");')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid URL.
    """
    protocol = urlparse(url)[0]
    if not protocol or protocol == 'javascript':
        raise ValidationError(_('You have to enter a valid URL.'))


def is_valid_ip(form, value):
    """Check if the string provided is a valid IP.

    >>> is_valid_ip(None, '192.168.10.99')
    >>> is_valid_ip(None, '255.0.23.1')
    >>> is_valid_ip(None, '255.0.23')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid IP.
    >>> is_valid_ip(None, '255.-0.23.5')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid IP.
    >>> is_valid_ip(None, '256.17.23.5')
    Traceback (most recent call last):
      ...
    ValidationError: You have to enter a valid IP.
    """
    # XXX: ipv6!
    idx = 0
    for idx, bit in enumerate(value.split('.')):
        if not bit.isdigit() or not 0 <= int(bit) <= 255:
            raise ValidationError(_('You have to enter a valid IP.'))
    return idx == 3
