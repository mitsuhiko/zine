# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.database
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Database tables for the TextPress webpage.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from textpress.api import db


metadata = db.MetaData()


plugins = db.Table('textpress_webpage_plugins', metadata,
    db.Column('name', db.Unicode(200), primary_key=True),
    db.Column('plugin_url', db.Unicode(200)),
    db.Column('author', db.Unicode(160)),
    db.Column('author_email', db.Unicode(200)),
    db.Column('author_url', db.Unicode(200)),
    db.Column('license', db.Unicode(50)),
    db.Column('version', db.Unicode(50)),
    db.Column('description', db.Unicode)
)


def upgrade_database(app):
    metadata.create_all(app.database_engine)
