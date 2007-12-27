# -*- coding: utf-8 -*-
"""
    textpress.plugins.pages.database
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Just some database tables for the pages plugin.

    :copyright: Copyright 2007 by Christopher Grebs.
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
    db.Column('raw', db.Unicode),
    db.Column('body', db.Unicode),
    db.Column('extra', db.PickleType),
    db.Column('navigation_pos', db.Integer)
)


def upgrade_database(app):
    metadata.create_all(app.database_engine)



class Page(object):

    def __init__(self, key, title, raw, parser=None, navigation_pos=None):
        self.key = key
        self.title = title
        self.raw = raw
        if parser is None:
            parser = get_application().cfg['default_parser']
        self.body = parse(raw, parser).render()
        self.extra = {'parser': parser}
        if navigation_pos is not None:
            if isinstance(navigation_pos, (float, long, basestring)):
                navigation_pos = int(navigation_pos)
            #XXX: raise exception?
        self.navigation_pos = navigation_pos


    def get_url_values(self):
        return ('pages/show_page',
                {'key': self.key})

db.mapper(Page, pages_table)
