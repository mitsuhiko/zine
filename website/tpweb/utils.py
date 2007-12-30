# -*- coding: utf-8 -*-
"""
    tpweb.utils
    ~~~~~~~~~~~

    Various utilities.

    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re


from htmlentitydefs import name2codepoint
_html_entities = name2codepoint.copy()
_html_entities['apos'] = 39
del name2codepoint

_par_re = re.compile(r'\n{2,}')
_entity_re = re.compile(r'&([^;]+);')
_striptags_re = re.compile(r'(<!--.*-->|<[^>]*>)')


def nl2p(s):
    """Add paragraphs to a text."""
    return u'\n'.join(u'<p>%s</p>' % p for p in _par_re.split(s))


def strip_tags(s):
    """Resolve HTML entities and remove tags from a string."""
    def handle_match(m):
        name = m.group(1)
        if name in html_entities:
            return unichr(html_entities[name])
        if name[:2] in ('#x', '#X'):
            try:
                return unichr(int(name[2:], 16))
            except ValueError:
                return u''
        elif name.startswith('#'):
            try:
                return unichr(int(name[1:]))
            except ValueError:
                return u''
        return u''
    return _entity_re.sub(handle_match, _striptags_re.sub('', s))


class Pagination(object):
    """
    Paginate a SQLAlchemy query object.
    """

    def __init__(self, request, query, per_page, page, endpoint):
        self.url_adapter = request.url_adapter
        self.query = query
        self.per_page = per_page
        self.page = page
        self.endpoint = endpoint
        self.entries = self.query.offset((self.page - 1) * self.per_page) \
                           .limit(self.per_page).all()
        self.count = self.query.count()

    has_previous = property(lambda x: x.page > 1)
    has_next = property(lambda x: x.page < x.pages)
    previous = property(lambda x: x.url_adapter.build(x.endpoint,
                        {'page': x.page - 1}))
    next = property(lambda x: x.url_adapter.build(x.endpoint,
                    {'page': x.page + 1}))
    pages = property(lambda x: max(0, x.count - 1) // x.per_page + 1)
