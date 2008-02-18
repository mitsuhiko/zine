# -*- coding: utf-8 -*-
"""
    textpress.database
    ~~~~~~~~~~~~~~~~~~

    This module is a rather complex layer on top of SQLAlchemy 0.4 or higher.
    Basically you will never use the `textpress.database` module except you
    are a core developer, but always use the high level `db` module which you
    can import from the `textpress.api` module.

    The following examples all assume that you have imported the db module.

    Foreword
    --------

    One important thing is that this module does some things in the background
    you don't have to care about in the modules.  For example it fetches a
    database connection and session automatically.  There are also some
    wrappers around the normal sqlalchemy module functions.

    What you have to know is that the `textpress.api.db` module contains all
    the public objects from `sqlalchemy` and `sqlalchemy.orm`.  Additionally
    there are the following functions:

    `db.get_engine`
        return the engine object for the current application. This is
        equivalent with `get_application().database_engine`.

    `flush`
        flush all outstanding database changes in the current session.

    `mapper`
        replacement for the normal SQLAlchemy mapper function. Works the
        same but users our `ManagerExtension`.  See the notes below.

    `save`
        bind an unbound object to the session and mark it for saving.
        Normally models you create by hand are automatically saved, unless
        you create it with ``_tp_no_save=True``

    `DatabaseManager`
        baseclass for all the database managers.  If you don't set at least
        one database manager to your model TextPress will create one for
        you called `objects`.


    Definiting Tables
    -----------------

    So let's get started quickly.  To defin tables all you have to do is to
    create a metadata instances for your table collection (so that you can
    create them) and bind some tables to it::

        metadata = db.MetaData()

        my_table = db.Table('my_plugin_my_table', metadata,
            db.Column('my_table_id', db.Integer, primary_key=True),
            ...
        )


    Creating a Upgrade Function
    ---------------------------

    If you want to use those tables in a TextPress plugin you have to create
    them.  You have to register a database upgrade function (see the
    docstrings on the application object regarding taht) which looks like
    this::

        def upgrade_database(app):
            metadata.create_all(app.database_engine)


    Writing Models
    --------------

    If you want to map your tables to classes you have to write some tables.
    This works exactly like mentioned in the excellent SQLAlchemy
    documentation, except that all the functions and objects you want to use
    are stored in the `db` module.

    For some example models have a look at the `textpress.models` module.

    One difference to plain SQLAlchemy is that we don't use a normal session
    context that sets a query object to models, but we use a technique similar
    to django's models, which they call `DatabaseManagers`.

    Basically what happens is that after the `mapper()` call, TextPress checks
    your models and looks for `DatabaseManager` instances.  If it cannot find
    at least one it will create a standard database managed on the attribute
    called `objects`.  If that attribute is already in used it will complain
    and raise an exception.

    You can of course bind multiple database managers to one model.  But now
    what are `DatabaseManagers`?

    Say you have a model but the queries in the views are quite complex.  So
    you can write functions that fire that requests somewhere else.  But where
    to put those queries?  Per default all query methods are stored an a
    database manager and it's a good idea to keep them there.  If you want to
    add some more methods to a manager just subclass `db.DatabaseManager` and
    instanciate them on your model::

        class UserManager(db.DatabaseManager):

            def get_authors(self):
                return self.select(User.role >= ROLE_AUTHOR)

        class User(object):
            objects = UserManager()
            ...

    Now you can get all the authors by calling `User.objects.get_authors()`.
    The object returned is a normal SQLAlchemy queryset so you can easily
    filter that using the normal query methods.


    Querying
    --------

    How to query? Just use the database manager attached to an object.  If
    you haven't attached on yourself the default `DatabaseManager` is mounted
    on the model as `objects`.  See the `DatabaseManager` docstring for more
    details.

    If you have to fire up some more raw and complex queries that don't use
    the mapper, get yourself a engine object using `get_engine` and start
    playing with it :-)  For normal execution you however don't have to do
    this, you can use `db.execute`, `db.begin` etc. which is also the
    preferred way since it takes place in the current session.


    Deleting Objects
    ----------------

    To delete objects you have to call `db.delete(obj)` and flush the session.


    Final Words
    -----------

    If you're lost, check out existing modules. Especially the views and
    the `models` modules of the core and existing plugins.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime, timedelta

from types import ModuleType

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.util import to_list

from textpress.utils import local, local_manager


def mapper(*args, **kwargs):
    """
    Add our own database mapper, not the new sqlalchemy 0.4
    session aware mapper.
    """
    kwargs['extension'] = extensions = to_list(kwargs.get('extension', []))
    extensions.append(ManagerExtension())
    return orm.mapper(*args, **kwargs)


class ManagerExtension(orm.MapperExtension):
    """
    Use django like database managers.
    """

    def get_session(self):
        return session.registry()

    def instrument_class(self, mapper, class_):
        managers = []
        for key, value in class_.__dict__.iteritems():
            if isinstance(value, DatabaseManager):
                managers.append(value)
        if not managers:
            if hasattr(class_, 'objects'):
                raise RuntimeError('The model %r already has an attribute '
                                   'called "objects".  You have to either '
                                   'rename this attribute or defined a '
                                   'mapper yourself with a different name')
            class_.objects = mgr = DatabaseManager()
            managers.append(mgr)
        class_._tp_managers = managers
        for manager in managers:
            manager.bind(class_)

    def init_instance(self, mapper, class_, oldinit, instance, args, kwargs):
        session = kwargs.pop('_sa_session', self.get_session())
        if not kwargs.pop('_tp_no_save', False):
            entity = kwargs.pop('_sa_entity_name', None)
            session._save_impl(instance, entity_name=entity)
        return orm.EXT_CONTINUE

    def init_failed(self, mapper, class_, oldinit, instance, args, kwargs):
        orm.object_session(instance).expugne(instance)
        return orm.EXT_CONTINUE


class DatabaseManager(object):
    """
    Baseclass for the database manager which you can also subclass to add
    more methods to it and attach to models by hand.

    A database manager works like a limited queryset.
    """

    def __init__(self):
        self.model = None

    def bind(self, model):
        """Called automatically by the `ManagerExtension`."""
        if self.model is not None:
            raise RuntimeError('manager already bound to model')
        self.model = model

    def __getitem__(self, arg):
        return self.query[arg]

    @property
    def query(self):
        """Return a new queryset."""
        return session.registry().query(self.model)

    def all(self):
        """Return all objects."""
        return self.query.all()

    def first(self):
        """Return the first object."""
        return self.query.first()

    def one(self):
        """
        Return the first result of all objects, raising an exception if
        more than one row exists.
        """
        return self.query.one()

    def get(self, *args, **kwargs):
        """Look up an object by primary key."""
        return self.query.get(*args, **kwargs)

    def filter(self, arg):
        """Filter all objects by the criteron provided and return a query."""
        return self.query.filter(arg)

    def filter_by(self, **kwargs):
        """Filter by keyword arguments."""
        return self.query.filter_by(**kwargs)

    def order_by(self, arg):
        """Order by something."""
        return self.query.order_by(arg)

    def limit(self, limit):
        """Limit all objects."""
        return self.query.limit(limit)

    def offset(self, offset):
        """Return a query with an offset."""
        return self.query.offset(offset)


#: a new scoped session
session = orm.scoped_session(lambda: orm.create_session(
                             local.application.database_engine,
                             autoflush=True, transactional=True),
                             local_manager.get_ident)

#: create a new module for all the database related functions and objects
db = ModuleType('db')
key = value = mod = None
for mod in sqlalchemy, orm:
    for key, value in mod.__dict__.iteritems():
        if key in mod.__all__:
            setattr(db, key, value)
del key, mod, value

db.__doc__ = __doc__
db.mapper = mapper
db.get_engine = lambda: local.application.database_engine
for name in 'delete', 'save', 'flush', 'execute', 'begin', \
            'commit', 'rollback', 'clear', 'refresh', 'expire':
    setattr(db, name, getattr(session, name))
db.session = session
db.DatabaseManager = DatabaseManager

#: support for SQLAlchemy's 0.4.2 Text type, in older versions it's
#: just Text.  This patch will go away once SQLAlchemy 0.5 is out
#: or something like that.
if not hasattr(db, 'Text'):
    db.Text = db.String

#: called at the end of a request
cleanup_session = session.remove

#: metadata for the core tables and the core table definitions
metadata = db.MetaData()


users = db.Table('users', metadata,
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('username', db.String(30)),
    db.Column('first_name', db.String(40)),
    db.Column('last_name', db.String(80)),
    db.Column('display_name', db.String(130)),
    db.Column('description', db.Text),
    db.Column('extra', db.PickleType),
    db.Column('pw_hash', db.String(70)),
    db.Column('email', db.String(250)),
    db.Column('role', db.Integer)
)

tags = db.Table('tags', metadata,
    db.Column('tag_id', db.Integer, primary_key=True),
    db.Column('slug', db.String(50)),
    db.Column('name', db.String(50)),
    db.Column('description', db.Text)
)

posts = db.Table('posts', metadata,
    db.Column('post_id', db.Integer, primary_key=True),
    db.Column('pub_date', db.DateTime),
    db.Column('last_update', db.DateTime),
    db.Column('slug', db.String(50)),
    db.Column('uid', db.String(250)),
    db.Column('title', db.String(50)),
    db.Column('intro', db.Text),
    db.Column('body', db.Text),
    db.Column('author_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('comments_enabled', db.Boolean, nullable=False),
    db.Column('pings_enabled', db.Boolean, nullable=False),
    db.Column('parser_data', db.PickleType),
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

post_tags = db.Table('post_tags', metadata,
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.tag_id'))
)

comments = db.Table('comments', metadata,
    db.Column('comment_id', db.Integer, primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('author', db.String(100)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('body', db.Text),
    db.Column('is_pingback', db.Boolean, nullable=False),
    db.Column('parser_data', db.PickleType),
    db.Column('parent_id', db.Integer, db.ForeignKey('comments.comment_id')),
    db.Column('pub_date', db.DateTime),
    db.Column('blocked', db.Boolean, nullable=False),
    db.Column('blocked_msg', db.String(250)),
    db.Column('submitter_ip', db.String(100))
)


def init_database(engine):
    """
    This is also called form the upgrade database function but especially from
    the websetup. That's also why it takes an engine and not a textpress
    application.
    """
    metadata.create_all(engine)


def upgrade_database(app):
    """
    Check if the tables are up to date and perform an upgrade.
    Currently creating is enough. Once there are release verisons
    this function will upgrade the database structure too.
    """
    init_database(app.database_engine)
