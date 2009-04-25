# -*- coding: utf-8 -*-
"""
    zine.utils.text
    ~~~~~~~~~~~~~~~

    This module provides various text utility functions.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
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


def gen_timestamped_slug(slug, content_type, pub_date):
    """Generate a timestamped slug, suitable for use as final URL path."""
    from zine.application import get_application
    from zine.i18n import to_blog_timezone
    cfg = get_application().cfg
    pub_date = to_blog_timezone(pub_date)

    prefix = cfg['blog_url_prefix'].lstrip('/')
    if prefix:
        prefix += '/'

    if content_type == 'entry':
        if cfg['fixed_url_date_digits']:
            year = '%04d' % pub_date.year
            month = '%02d' % pub_date.month
            day = '%02d' % pub_date.day
            hour = '%02d' % pub_date.hour
            minute = '%02d' % pub_date.minute
            second = '%02d' % pub_date.second
        else:
            year = '%d' % pub_date.year
            month = '%d' % pub_date.month
            day = '%d' % pub_date.day
            hour = '%d' % pub_date.hour
            minute = '%d' % pub_date.minute
            second = '%d' % pub_date.second

        full_slug = u'%s%s%s' % (
            prefix,
            cfg['post_url_format'].replace(
                '%year%', year).replace(
                '%month%', month).replace(
                '%day%', day).replace(
                '%hour%', hour).replace(
                '%minute%', minute).replace(
                '%second%', second),
            slug
            )
    else:
        full_slug = u'%s%s' % (prefix, slug)
    return full_slug


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
    """Build a unique tag URI.
       The tag URI must obey the ABNF defined in
       http://www.faqs.org/rfcs/rfc4151.html """

    host, path = urlparse(app.cfg['blog_url'])[1:3]
    if ':' in host:
        host = host.split(':', 1)[0]
    path = path.strip('/')
    if path:
        path = ',' + path
    if not isinstance(identifier, basestring):
        identifier = str(identifier)
    return 'tag:%s,%s:%s/%s;%s' % (host, date.strftime('%Y-%m-%d'), path,
                                   url_quote(resource), url_quote(identifier))
