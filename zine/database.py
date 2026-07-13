# -*- coding: utf-8 -*-
"""
    zine.database
    ~~~~~~~~~~~~~

    This module is a rather complex layer on top of SQLAlchemy.

    Basically you will never use the `zine.database` module except if you
    are a core developer, but always the high level :mod:`~zine.database.db`
    module which you can import from the :mod:`zine.api` module.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import os
import sys
import time
from os import path
from types import ModuleType
from copy import deepcopy

import sqlalchemy
from sqlalchemy import event, orm
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.types import TypeDecorator
from sqlalchemy.ext.associationproxy import association_proxy

from werkzeug.exceptions import NotFound

from zine._compat import url_decode
from zine.utils import local_manager


if sys.platform == 'win32':
    _timer = time.perf_counter
else:
    _timer = time.time


_sqlite_re = re.compile(r'sqlite:(?:(?://(.*?))|memory)(?:\?(.*))?$')


def get_engine():
    """Return the active database engine (the database engine of the active
    application).  If no application is enabled this has an undefined behavior.
    If you are not sure if the application is bound to the active thread, use
    :func:`~zine.application.get_application` and check it for `None`.
    The database engine is stored on the application object as `database_engine`.
    """
    from zine.application import get_application
    return get_application().database_engine


def create_engine(uri, relative_to=None, debug=False):
    """Create a new engine.  This works a bit like SQLAlchemy's
    `create_engine` with the difference that it automaticaly set's MySQL
    engines to 'utf-8', and paths for SQLite are relative to the path
    provided as `relative_to`.

    The returned engine uses SQLAlchemy's modern transaction semantics.
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
        info = URL.create('sqlite', database=database, query=query)

    else:
        info = make_url(uri)

        # if mysql is the database engine and no connection encoding is
        # provided we set it to utf-8
        if info.get_backend_name() == 'mysql' and 'charset' not in info.query:
            info = info.update_query_dict({'charset': 'utf8'})

    options = {}

    # alternative pool sizes / recycle settings and more.  These are
    # interpreter wide and not from the config for the following reasons:
    #
    # - system administrators can set it independently from the webserver
    #   configuration via SetEnv and friends.
    # - this setting is deployment dependent should not affect a development
    #   server for the same instance or a development shell
    for key in 'pool_size', 'pool_recycle', 'pool_timeout':
        value = os.environ.get('ZINE_DATABASE_' + key.upper())
        if value is None:
            value = os.environ.get('ZINE_' + key.upper())
        if value is not None:
            options[key] = int(value)

    engine = sqlalchemy.create_engine(info, **options)
    if debug:
        ConnectionDebugProxy.install(engine)
    return engine


def secure_database_uri(uri):
    """Returns the database uri with confidental information stripped."""
    obj = make_url(uri)
    if obj.password:
        obj = obj.set(password='***')
    return obj.render_as_string(hide_password=False).replace(
        u':%2A%2A%2A@', u':***@', 1
    )


def attribute_loaded(model, attribute):
    """Returns true if the attribute of the model was already loaded."""
    # XXX: this works but it relys on a specific implementation in
    # SQLAlchemy.  Figure out if SA provides a way to query that information.
    return attribute in model.__dict__


class ConnectionDebugProxy(object):
    """Collect SQL timing information using SQLAlchemy engine events."""

    @staticmethod
    def install(engine):
        event.listen(engine, 'before_cursor_execute',
                     ConnectionDebugProxy.before_cursor_execute)
        event.listen(engine, 'after_cursor_execute',
                     ConnectionDebugProxy.after_cursor_execute)
        event.listen(engine, 'handle_error', ConnectionDebugProxy.handle_error)

    @staticmethod
    def before_cursor_execute(connection, cursor, statement, parameters,
                              context, executemany):
        from zine.utils.debug import find_calling_context
        context._zine_query = (_timer(), find_calling_context())

    @staticmethod
    def _record(context, statement, parameters):
        query = getattr(context, '_zine_query', None)
        if query is None:
            return
        del context._zine_query
        from zine.application import get_request
        request = get_request()
        if request is not None:
            start, calling_context = query
            request.queries.append((statement, parameters, start,
                                    _timer(), calling_context))

    @staticmethod
    def after_cursor_execute(connection, cursor, statement, parameters,
                             context, executemany):
        ConnectionDebugProxy._record(context, statement, parameters)

    @staticmethod
    def handle_error(exception_context):
        context = exception_context.execution_context
        if context is not None:
            ConnectionDebugProxy._record(
                context, exception_context.statement,
                exception_context.parameters
            )


class ZEMLParserData(TypeDecorator):
    """Holds parser data.  The implementation is rather ugly because it does
    not really compare the trees for performance reasons but only the dirty
    flags.  This might change in future versions if there is some sort of
    support for this kind of hackery in SQLAlchemy or if we find a fast way
    to compare the trees.
    """

    impl = sqlalchemy.LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return
        from zine.utils.zeml import dump_parser_data
        return dump_parser_data(value)

    def process_result_value(self, value, dialect):
        from zine.utils.zeml import load_parser_data
        try:
            return load_parser_data(value)
        except ValueError: # Parser data invalid. Database corruption?
            from zine.i18n import _
            from zine.utils import log
            log.exception(_(u'Error when loading parsed data from database. '
                            u'Maybe the database was manually edited and got '
                            u'corrupted? The system returned an empty value.'))
            return {}

    def copy_value(self, value):
        return deepcopy(value)

    def compare_values(self, x, y):
        return x is y

    def is_mutable(self):
        return False


class Query(orm.Query):
    """Default query class."""

    def _loader_option(self, name, strategy):
        if not isinstance(name, str):
            return getattr(orm, strategy)(name)
        entity = self.column_descriptions[0].get('entity')
        if entity is None:
            raise TypeError('loader options require a mapped entity')
        parts = name.split('.')
        attribute = getattr(entity, parts.pop(0))
        if not parts:
            return getattr(orm, strategy)(attribute)
        option = orm.defaultload(attribute)
        entity = attribute.property.mapper.class_
        while len(parts) > 1:
            attribute = getattr(entity, parts.pop(0))
            option = option.defaultload(attribute)
            entity = attribute.property.mapper.class_
        return getattr(option, strategy)(getattr(entity, parts[0]))

    def lightweight(self, deferred=None, lazy=None):
        """Send a lightweight query which defers expensive attributes."""
        args = [self._loader_option(name, 'lazyload') for name in lazy or ()]
        args.extend(self._loader_option(name, 'defer')
                    for name in deferred or ())
        return self.options(*args)

    def get(self, ident):
        """Load an object by primary key without the legacy ``Query.get``."""
        entity = self.column_descriptions[0].get('entity')
        if entity is None:
            raise TypeError('get() requires a mapped entity')
        primary_key = sqlalchemy.inspect(entity).primary_key
        if isinstance(ident, dict):
            values = [ident[column.key] for column in primary_key]
        elif len(primary_key) == 1:
            values = [ident]
        else:
            values = list(ident)
        if len(values) != len(primary_key):
            raise ValueError('incorrect number of primary-key values')
        criteria = [column == value
                    for column, value in zip(primary_key, values)]
        return self.filter(*criteria).first()

    def first(self, raise_if_missing=False):
        """Return the first result, optionally raising :class:`NotFound`."""
        rv = super().first()
        if rv is None and raise_if_missing:
            raise NotFound()
        return rv


session = orm.scoped_session(
    lambda: orm.Session(bind=get_engine(), autoflush=True),
    scopefunc=local_manager.get_ident,
)


class _OrderedQueryProperty(object):
    def __init__(self, query_class, order_by):
        self.query_property = session.query_property(query_class)
        self.order_by = order_by

    def __get__(self, instance, owner):
        query = self.query_property.__get__(instance, owner)
        return query.order_by(self.order_by)


def query_property(query_class=Query, order_by=None):
    """Create the legacy model query descriptor used throughout Zine."""
    if order_by is None:
        return session.query_property(query_class)
    return _OrderedQueryProperty(query_class, order_by)


def _model_constructor(self, **kwargs):
    for key, value in kwargs.items():
        if not hasattr(type(self), key):
            raise TypeError('%r is an invalid keyword argument for %s' %
                            (key, type(self).__name__))
        setattr(self, key, value)
    session.add(self)


_mapper_registry = orm.registry(constructor=_model_constructor)


def mapper(cls, table, *args, **kwargs):
    """Map a class imperatively and auto-register new instances."""
    if 'query' not in cls.__dict__:
        cls.query = query_property(Query)
    old_init = cls.__dict__.get('__init__')

    def register_init(self, *args, **kwargs):
        if old_init is not None:
            old_init(self, *args, **kwargs)
        elif args or kwargs:
            raise TypeError('%s() takes no arguments' % cls.__name__)
        session.add(self)

    cls.__init__ = register_init
    return _mapper_registry.map_imperatively(cls, table, *args, **kwargs)


# Configure a declarative base for plugins.
class ModelBase(object):
    """Internal baseclass for `Model`."""


Model = _mapper_registry.generate_base(name='Model', cls=ModelBase)
ModelBase.query = query_property(Query)


#: create a new module for all the database related functions and objects
sys.modules['zine.database.db'] = db = ModuleType('db')
key = value = mod = None
for mod in sqlalchemy, orm:
    for key, value in mod.__dict__.items():
        if not key.startswith('_'):
            setattr(db, key, value)
del key, mod, value

#: forward some session methods to the module as well
for name in 'add', 'delete', 'flush', 'execute', 'begin', 'commit', \
            'rollback', 'refresh', 'expire', 'get':
    setattr(db, name, getattr(session, name))

# Some things changed names with SQLAlchemy 0.6.0
db.save = session.add
db.clear = session.expunge_all

#: and finally hook our own implementations of various objects in
db.Model = Model
db.Query = Query
db.get_engine = get_engine
db.create_engine = create_engine
db.session = session
db.ZEMLParserData = ZEMLParserData
db.mapper = mapper
db.basic_mapper = _mapper_registry.map_imperatively
db.query_property = query_property
db.association_proxy = association_proxy
db.attribute_loaded = attribute_loaded

#: called at the end of a request
cleanup_session = session.remove

#: metadata for the core tables and the core table definitions
metadata = _mapper_registry.metadata

users = db.Table('users', metadata,
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('username', db.String(30)),
    db.Column('real_name', db.String(180)),
    db.Column('display_name', db.String(180)),
    db.Column('description', db.Text),
    db.Column('extra', db.PickleType),
    db.Column('pw_hash', db.String(70)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('is_author', db.Boolean)
)

groups = db.Table('groups', metadata,
    db.Column('group_id', db.Integer, primary_key=True),
    db.Column('name', db.String(30))
)

group_users = db.Table('group_users', metadata,
    db.Column('group_id', db.Integer, db.ForeignKey('groups.group_id')),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id'))
)

privileges = db.Table('privileges', metadata,
    db.Column('privilege_id', db.Integer, primary_key=True),
    db.Column('name', db.String(50), unique=True)
)

user_privileges = db.Table('user_privileges', metadata,
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('privilege_id', db.Integer,
              db.ForeignKey('privileges.privilege_id'))
)

group_privileges = db.Table('group_privileges', metadata,
    db.Column('group_id', db.Integer, db.ForeignKey('groups.group_id')),
    db.Column('privilege_id', db.Integer,
              db.ForeignKey('privileges.privilege_id'))
)

categories = db.Table('categories', metadata,
    db.Column('category_id', db.Integer, primary_key=True),
    db.Column('slug', db.String(50)),
    db.Column('name', db.String(50)),
    db.Column('description', db.Text)
)

texts = db.Table('texts', metadata,
    db.Column('text_id', db.Integer, primary_key=True),
    db.Column('text', db.Text),
    db.Column('parser_data', db.ZEMLParserData),
    db.Column('extra', db.PickleType)
)

posts = db.Table('posts', metadata,
    db.Column('post_id', db.Integer, primary_key=True),
    db.Column('pub_date', db.DateTime),
    db.Column('last_update', db.DateTime),
    db.Column('slug', db.String(200), index=True, nullable=False),
    db.Column('uid', db.String(250)),
    db.Column('title', db.String(150)),
    db.Column('text_id', db.Integer, db.ForeignKey('texts.text_id')),
    db.Column('author_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('comments_enabled', db.Boolean),
    db.Column('comment_count', db.Integer, nullable=False, default=0),
    db.Column('pings_enabled', db.Boolean),
    db.Column('content_type', db.String(40), index=True),
    db.Column('status', db.Integer),
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
    db.Column('name', db.String(100), unique=True, nullable=False)
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
    db.Column('author', db.String(160)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('text_id', db.Integer, db.ForeignKey('texts.text_id')),
    db.Column('is_pingback', db.Boolean, nullable=False),
    db.Column('parent_id', db.Integer, db.ForeignKey('comments.comment_id')),
    db.Column('pub_date', db.DateTime),
    db.Column('blocked_msg', db.String(250)),
    db.Column('submitter_ip', db.String(100)),
    db.Column('status', db.Integer, nullable=False)
)

redirects = db.Table('redirects', metadata,
    db.Column('redirect_id', db.Integer, primary_key=True),
    db.Column('original', db.String(200), unique=True),
    db.Column('new', db.String(200))
)

notification_subscriptions = db.Table('notification_subscriptions', metadata,
    db.Column('subscription_id', db.Integer, primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('notification_system', db.String(50)),
    db.Column('notification_id', db.String(100)),
    db.UniqueConstraint('user_id', 'notification_system', 'notification_id')
)


CORE_TABLES = (
    users,
    groups,
    group_users,
    privileges,
    user_privileges,
    group_privileges,
    categories,
    texts,
    posts,
    post_links,
    tags,
    post_categories,
    post_tags,
    comments,
    redirects,
    notification_subscriptions,
)


class DatabaseSchemaError(RuntimeError):
    """Raised when a configured database is not a current Zine database."""


def validate_database(engine):
    """Ensure that all core tables and columns match the current schema."""
    inspector = sqlalchemy.inspect(engine)
    actual_tables = set(inspector.get_table_names())
    expected_tables = {table.name for table in CORE_TABLES}
    problems = []

    missing_tables = sorted(expected_tables - actual_tables)
    if missing_tables:
        problems.append('missing tables: %s' % ', '.join(missing_tables))

    for table in CORE_TABLES:
        if table.name not in actual_tables:
            continue
        actual_columns = {
            column['name'] for column in inspector.get_columns(table.name)
        }
        expected_columns = {column.name for column in table.columns}
        if actual_columns != expected_columns:
            problems.append(
                '%s columns differ (expected %s; found %s)' % (
                    table.name,
                    ', '.join(sorted(expected_columns)),
                    ', '.join(sorted(actual_columns)),
                )
            )

    if problems:
        raise DatabaseSchemaError(
            'database schema is not supported by this Zine port; create a '
            'fresh instance (%s)' % '; '.join(problems)
        )


def init_database(engine):
    """Create the current core schema for a fresh Zine instance."""
    metadata.create_all(engine, tables=CORE_TABLES)
