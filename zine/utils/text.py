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

_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|}]+')

_tagify_replacement_table = {
    u'\xdf': 'ss',
    u'\xe4': 'ae',
    u'\xe6': 'ae',
    u'\xf0': 'dh',
    u'\xf6': 'oe',
    u'\xfc': 'ue',
    u'\xfe': 'th'
}


def gen_slug(text, delim='-'):
    """remove accents and make text lowercase."""
    result = []
    for word in _punctuation_re.split(text.lower()):
        if word:
            for search, replace in _tagify_replacement_table.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
    return unicode(delim.join(result))


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
