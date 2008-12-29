# -*- coding: utf-8 -*-
"""
    zine.utils.text
    ~~~~~~~~~~~~~~~

    This module provides various text utility functions.

    :copyright: 2008 by Armin Ronacher, Georg Brandl, Jason Kirtland.
    :license: BSD, see LICENSE for more details.
"""
import re
import string
import unicodedata
from urlparse import urlparse

from werkzeug import url_quote

from zine._dynamic.translit_tab import LONG_TABLE, SHORT_TABLE, SINGLE_TABLE


_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')
_string_inc_re = re.compile(r'(\d+)$')


def gen_slug(text, delim=u'-'):
    """Generates a proper slug for the given text.  It calls either
    `gen_ascii_slug` or `gen_unicode_slug` depending on the application
    configuration.
    """
    from zine.application import get_application
    if get_application().cfg['ascii_slugs']:
        return gen_ascii_slug(text, delim)
    return gen_unicode_slug(text, delim)


def gen_ascii_slug(text, delim=u'-'):
    """Generates an ASCII-only slug."""
    result = []
    for word in _punctuation_re.split(text.lower()):
        word = _punctuation_re.sub(u'', transliterate(word))
        if word:
            result.append(word)
    return unicode(delim.join(result))


def gen_unicode_slug(text, delim=u'-'):
    """Generate an unicode slug."""
    return unicode(delim.join(_punctuation_re.split(text.lower())))


def increment_string(string):
    """Increment a string by one:

    >>> increment_string(u'test')
    u'test2'
    >>> increment_string(u'test2')
    u'test3'
    """
    match = _string_inc_re.search(string)
    if match is None:
        return string + u'2'
    return string[:match.start()] + unicode(int(match.group(1)) + 1)


def transliterate(string, table='long'):
    """Transliterate to 8 bit using one of the tables given.  The table
    must either be ``'long'``, ``'short'`` or ``'single'``.
    """
    table = {
        'long':     LONG_TABLE,
        'short':    SHORT_TABLE,
        'single':   SINGLE_TABLE
    }[table]
    return unicodedata.normalize('NFKC', unicode(string)).translate(table)


def build_tag_uri(app, date, resource, identifier):
    """Build a unique tag URI for this blog."""
    host, path = urlparse(app.cfg['blog_url'])[1:3]
    if ':' in host:
        host = host.split(':', 1)[0]
    path = path.strip('/')
    if path:
        path = ',' + path
    if not isinstance(identifier, basestring):
        identifier = str(identifier)
    return 'tag:%s,%s%s/%s:%s' % (host, date.strftime('%Y-%m-%d'), path,
                                  url_quote(resource), url_quote(identifier))
