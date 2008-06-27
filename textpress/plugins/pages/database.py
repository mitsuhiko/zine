# -*- coding: utf-8 -*-
"""
    textpress.plugins.pages.database
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Just some database tables for the pages plugin.

    :copyright: Copyright 2007-2008 by Christopher Grebs and Ali Afshar.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.parsers import parse
from textpress.utils import cached_property


metadata = db.MetaData()


pages_table = db.Table('pages', metadata,
    db.Column('page_id', db.Integer, primary_key=True),
    db.Column('key', db.Unicode(25)),
    db.Column('title', db.Unicode(200)),
    db.Column('body', db.Unicode),
    db.Column('extra', db.PickleType),
    db.Column('navigation_pos', db.Integer),
    db.Column('parent_id', db.Integer, db.ForeignKey('pages.page_id')),
)


def upgrade_database(app):
    metadata.create_all(app.database_engine)


class Page(object):

    def __init__(self, key, title, body, parser=None, navigation_pos=None,
                 parent_id=None):
        self.key = key
        self.title = title
        if parser is None:
            parser = get_application().cfg['default_parser']
        # the extra attribute holds various data for fragment processing
        self.extra = {'parser': parser}
        if navigation_pos is not None:
            if isinstance(navigation_pos, (float, long, basestring)):
                navigation_pos = int(navigation_pos)
        self.navigation_pos = navigation_pos
        self.raw_body = body
        self.parent_id = parent_id

    def _get_parser(self):
        return self.extra['parser']

    def _set_parser(self, value):
        self.extra['parser'] = value
    parser = property(_get_parser, _set_parser)
    del _get_parser, _set_parser

    def _get_raw_body(self):
        return self._raw_body

    def _set_raw_body(self, value):
        from textpress.parsers import parse
        from textpress.fragment import dump_tree
        tree = parse(value, self.extra['parser'], 'page-body')
        self._raw_body = value
        self._body_cache = tree
        self.extra['body'] = dump_tree(tree)
    raw_body = property(_get_raw_body, _set_raw_body)

    def _get_body(self):
        if not hasattr(self, '_body_cache'):
            from textpress.fragment import load_tree
            self._body_cache = load_tree(self.extra['body'])
        return self._body_cache

    def _set_body(self, value):
        from textpress.fragment import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_body')
        self._body_cache = value
        self.extra['body'] = dump_tree(value)
    body = property(_get_body, _set_body)
    del _get_raw_body, _set_raw_body, _get_body, _set_body

    def get_url_values(self):
        return ('pages/show_page',
                {'key': self.key})

    @property
    def ancestors(self):
        anc = [self]
        p = self.parent
        while p:
            anc.append(p)
            p = p.parent
        return reversed(anc)

    @property
    def siblings(self):
        if self.parent:
            return self.parent.children
        else:
            return [self]


db.mapper(Page, pages_table, properties={
    '_raw_body':    pages_table.c.body,
    'parent':       db.relation(Page,
        remote_side=[pages_table.c.page_id], backref='children'),
})
