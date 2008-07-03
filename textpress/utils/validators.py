"""
    textpress.utils
    ~~~~~~~~~~~~~~~

    This module implements various functions for validation of miscellaneous
    things, e.g. urls.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import md5
import sha
from urlparse import urlparse, urljoin, urlsplit


def check_external_url(app, url, check=False):
    """Check if a URl is on the application server."""
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


def check_pwhash(pwhash, password):
    """Check a password against a given hash value. Since
    many forums save md5 passwords with no salt and it's
    technically impossible to convert this to an sha hash
    with a salt we use this to be able to check for
    plain passwords::

        plain$$default

    md5 passwords without salt::

        md5$$c21f969b5f03d33d43e04f8f136e7682

    md5 passwords with salt::

        md5$123456$7faa731e3365037d264ae6c2e3c7697e

    sha passwords::

        sha$123456$118083bd04c79ab51944a9ef863efcd9c048dd9a

    Note that the integral passwd column in the table is
    only 60 chars long. If you have a very large salt
    or the plaintext password is too long it will be
    truncated.
    """
    if isinstance(password, unicode):
        password = password.encode('utf-8')
    if pwhash.count('$') < 2:
        return False
    method, salt, hashval = pwhash.split('$', 2)
    if method == 'plain':
        return hashval == password
    elif method == 'md5':
        h = md5.new()
    elif method == 'sha':
        h = sha.new()
    else:
        return False
    h.update(salt)
    h.update(password)
    return h.hexdigest() == hashval


def is_valid_email(mail):
    """Check if the string passed is a valid mail address."""
    return '@' in mail


def is_valid_url(url):
    """Check if the string passed is a valid url."""
    protocol = urlparse(url)[0]
    return protocol and protocol != 'javascript'


def is_valid_ip(value):
    """Check if the string provided is a valid IP."""
    # XXX: ipv6!
    idx = 0
    for idx, bit in enumerate(value.split('.')):
        if not bit.isdigit() or not 0 <= int(value) <= 255:
            return False
    return idx == 3
