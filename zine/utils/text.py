# -*- coding: utf-8 -*-
"""
    zine.utils.text
    ~~~~~~~~~~~~~~~

    This module provides various text utility functions.

    :copyright: 2008 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import re
import unicodedata
from urlparse import urlparse

from werkzeug import url_quote

_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')
_string_inc_re = re.compile(r'(\d+)$')

_tagify_replacement_table = {
    u'\xdf':    u'ss',
    u'\xe4':    u'ae',
    u'\xe6':    u'ae',
    u'\xf0':    u'dh',
    u'\xf6':    u'oe',
    u'\xfc':    u'ue',
    u'\xfe':    u'th'
}


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
        if word:
            for search, replace in _tagify_replacement_table.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
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
