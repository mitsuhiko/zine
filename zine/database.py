# -*- coding: utf-8 -*-
"""
    zine.database
    ~~~~~~~~~~~~~

    This module is a rather complex layer on top of SQLAlchemy 0.4.
    Basically you will never use the `zine.database` module except you
    are a core developer, but always the high level
    :mod:`~zine.database.db` module which you can import from the
    :mod:`zine.api` module.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Christopher Grebs,
                             Ali Afshar.
    :license: GNU GPL.
"""
import re
import sys
import urlparse
from os import path
from datetime import datetime, timedelta
from types import ModuleType

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.util import to_list
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.types import MutableType, TypeDecorator
from werkzeug import url_decode

from zine.utils import local, local_manager


_sqlite_re = re.compile(r'sqlite:(?:(?://(.*?))|memory)(?:\?(.*))?$')


def get_engine():
    """Return the active database engine (the database engine of the active
    application).  If no application is enabled this has an undefined behavior.
    If you are not sure if the application is bound to the active thread, use
    :func:`~zine.application.get_application` and check it for `None`.
    The database engine is stored on the application object as `database_engine`.
    """
    return local.application.database_engine


def create_engine(uri, relative_to=None, echo=False):
    """Create a new engine.  This works a bit like SQLAlchemy's
    `create_engine` with the difference that it automaticaly set's MySQL
    engines to 'utf-8', and paths for SQLite are relative to the path
    provided as `relative_to`.

    Furthermore the engine is created with `convert_unicode` by default.
    """
    # special case sqlite.  We want nicer urls for that one.
    if uri.startswith('sqlite:'):
        match = _sqlite_re.match(uri)
        if match is None:
            raise ArgumentError('Could not parse rfc1738 URL')
        database, query = match.groups()
        if database is None:
            database = ':memory:'
        elif relative_to is not None:
            database = path.join(relative_to, database)
        if query:
            query = url_decode(query).to_dict()
        else:
            query = {}
        info = URL('sqlite', database=database, query=query)

    else:
        info = make_url(uri)

        # if mysql is the database engine and no connection encoding is
        # provided we set it to utf-8
        if info.drivername == 'mysql':
            info.query.setdefault('charset', 'utf8')

    return sqlalchemy.create_engine(info, convert_unicode=True, echo=echo)


def secure_database_uri(uri):
    """Returns the database uri with confidental information stripped."""
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(uri)
    netloc = re.sub('([^:]*):([^@]*)@(.*)', r'\1:***@\3', netloc)
    return urlparse.urlunparse((scheme, netloc, path, params, query, fragment))


class ZEMLParserData(MutableType, TypeDecorator):
    """Holds parser data."""

    impl = sqlalchemy.Binary

    def process_bind_param(self, value, dialect):
        if value is None:
            return
        from zine.utils.zeml import dump_parser_data
        return dump_parser_data(value)

    def process_result_value(self, value, dialect):
        from zine.utils.zeml import load_parser_data
        return load_parser_data(value)

    def copy_value(self, value):
        from copy import deepcopy
        return deepcopy(value)


class Query(orm.Query):
    """Default query class."""


session = orm.scoped_session(lambda: orm.create_session(
                             local.application.database_engine,
                             autoflush=True, autocommit=False),
                             local_manager.get_ident)


# configure a declarative base.  This is unused in the code but makes it easier
# for plugins to work with the database.
class ModelBase(object):
    """Internal baseclass for `Model`."""
Model = declarative_base(name='Model', cls=ModelBase, mapper=session.mapper)
ModelBase.query = session.query_property(Query)


#: create a new module for all the database related functions and objects
sys.modules['zine.database.db'] = db = ModuleType('db')
key = value = mod = None
for mod in sqlalchemy, orm:
    for key, value in mod.__dict__.iteritems():
        if key in mod.__all__:
            setattr(db, key, value)
del key, mod, value

#: forward some session methods to the module as well
for name in 'delete', 'save', 'flush', 'execute', 'begin', 'mapper', \
            'commit', 'rollback', 'clear', 'refresh', 'expire', \
            'query_property':
    setattr(db, name, getattr(session, name))

#: and finally hook our own implementations of various objects in
db.Model = Model
db.Query = Query
db.get_engine = get_engine
db.create_engine = create_engine
db.session = session
db.ZEMLParserData = ZEMLParserData
db.mapper = session.mapper

#: called at the end of a request
cleanup_session = session.remove

#: metadata for the core tables and the core table definitions
metadata = db.MetaData()


users = db.Table('users', metadata,
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('username', db.String(30)),
    db.Column('real_name', db.String(180)),
    db.Column('display_name', db.String(130)),
    db.Column('description', db.Text),
    db.Column('extra', db.PickleType),
    db.Column('pw_hash', db.String(70)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('role', db.Integer)
)

categories = db.Table('categories', metadata,
    db.Column('category_id', db.Integer, primary_key=True),
    db.Column('slug', db.String(50)),
    db.Column('name', db.String(50)),
    db.Column('description', db.Text)
)

posts = db.Table('posts', metadata,
    db.Column('post_id', db.Integer, primary_key=True),
    db.Column('pub_date', db.DateTime),
    db.Column('last_update', db.DateTime),
    db.Column('slug', db.String(200), index=True, nullable=False),
    db.Column('uid', db.String(250)),
    db.Column('title', db.String(150)),
    db.Column('text', db.Text),
    db.Column('author_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('parser_data', db.ZEMLParserData),
    db.Column('comments_enabled', db.Boolean),
    db.Column('pings_enabled', db.Boolean),
    db.Column('content_type', db.String(40), index=True),
    db.Column('extra', db.PickleType),
    db.Column('status', db.Integer)
)

post_links = db.Table('post_links', metadata,
    db.Column('link_id', db.Integer, primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('href', db.String(250), nullable=False),
    db.Column('rel', db.String(250)),
    db.Column('type', db.String(100)),
    db.Column('hreflang', db.String(30)),
    db.Column('title', db.String(200)),
    db.Column('length', db.Integer)
)

tags = db.Table('tags', metadata,
    db.Column('tag_id', db.Integer, primary_key=True),
    db.Column('slug', db.String(150), unique=True, nullable=False),
    db.Column('name', db.String(100), index=True, nullable=False)
)

post_categories = db.Table('post_categories', metadata,
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.category_id'))
)

post_tags = db.Table('post_tags', metadata,
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.tag_id'))
)

comments = db.Table('comments', metadata,
    db.Column('comment_id', db.Integer, primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('author', db.String(100)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('text', db.Text),
    db.Column('is_pingback', db.Boolean, nullable=False),
    db.Column('parser_data', db.ZEMLParserData),
    db.Column('parent_id', db.Integer, db.ForeignKey('comments.comment_id')),
    db.Column('pub_date', db.DateTime),
    db.Column('blocked_msg', db.String(250)),
    db.Column('submitter_ip', db.String(100)),
    db.Column('status', db.Integer, nullable=False)
)


def init_database(engine):
    """This is called from the websetup which explains why it takes an engine
    and not a zine application.
    """
    metadata.create_all(engine)
