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
    db.Column('plugin_id', db.Integer, primary_key=True),
    db.Column('name', db.Unicode(200)),
    db.Column('developer_id', db.Integer,
              db.ForeignKey('textpress_webpage_developers.developer_id'))
)


plugin_versions = db.Table('textpress_webpage_plugin_versions', metadata,
    db.Column('version_id', db.Integer, primary_key=True),
    db.Column('pub_date', db.DateTime),
    db.Column('plugin_id', db.Integer,
              db.ForeignKey('textpress_webpage_plugins.plugin_id')),
    db.Column('display_name', db.Unicode(200)),
    db.Column('license', db.Unicode(100)),
    db.Column('author', db.Unicode(200)),
    db.Column('author_email', db.Unicode(200)),
    db.Column('author_url', db.Unicode(200)),
    db.Column('description', db.Unicode),
    db.Column('version', db.Unicode(50)),
    db.Column('plugin_url', db.Unicode(200))
)


developers = db.Table('textpress_webpage_developers', metadata,
    db.Column('developer_id', db.Integer, primary_key=True),
    db.Column('email', db.Unicode(200)),
    db.Column('pw_hash', db.Unicode(70)),
    db.Column('activation_key', db.Unicode(20))
)


def upgrade_database(app):
    metadata.create_all(app.database_engine)
