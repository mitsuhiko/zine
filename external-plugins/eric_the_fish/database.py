# -*- coding: utf-8 -*-
"""
    zine.plugins.eric_the_fish.databse
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Database tables and objects for the "Annoying fish for the admin panel".

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from zine.database import db, metadata

fortunes = db.Table('eric_the_fish_fortunes', metadata,
    db.Column('id', db.Integer, primary_key=True),
    db.Column('text', db.Text, nullable=False)
)

class Fortune(object):
    query = db.query_property(db.Query)
    def __init__(self, text):
        self.text = text

db.mapper(Fortune, fortunes)


def initialize(engine):
    """Create and seed Eric's table for a fresh-instance installation."""
    from zine.plugins.eric_the_fish.fortunes import FORTUNES

    fortunes.create(engine, checkfirst=True)
    with engine.begin() as connection:
        count = connection.scalar(
            db.select(db.func.count()).select_from(fortunes)
        )
        if not count:
            connection.execute(
                fortunes.insert(),
                [{'text': fortune} for fortune in FORTUNES],
            )
