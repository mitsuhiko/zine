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
    create them) and bind some tables to it.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime, timedelta

from types import ModuleType
from thread import get_ident

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.orm.scoping import ScopedSession
from sqlalchemy.util import to_list



def session_factory():
    """Function used by the session context to get a new session."""
    from textpress.application import get_application
    return db.create_session(get_application().database_engine)


def get_engine():
    """Return the database engine."""
    from textpress.application import get_application
    return get_application().database_engine


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
    Baseclass for the database manager. One can extend that one.
    """

    def __init__(self):
        self.model = None

    def bind(self, model):
        """Called automatically by the `ManagerExtension`."""
        if self.model is not None:
            raise RuntimeError('manager already bound to model')
        self.model = model

    def get(self, ident, **kw):
        """
        Return an instance of the object based on the given identifier
        (primary key), or `None` if not found.

        If you have more than one primary_key you can pass it a tuple
        with the column values in the order of the table primary key
        definitions.
        """
        return session.registry().query(self.model).get(ident, **kw)

    def all(self):
        """
        Return an SQLAlchemy query object and return it.
        """
        return session.registry().query(self.model)

    def select_first(self, *args, **kw):
        """
        Select the first and return a `Query` object.
        """
        return self.all().filter(*args, **kw).first()

    def select(self, *args, **kw):
        """
        Select multiple objects and return a `Query` object.
        """
        return self.all().filter(*args, **kw)

    def count(self, *args, **kw):
        """
        Count all objects matching an expression.
        """
        return self.all().count(*args, **kw)


session = ScopedSession(session_factory, scopefunc=get_ident)
db = ModuleType('db')
key = value = mod = None
for mod in sqlalchemy, orm:
    for key, value in mod.__dict__.iteritems():
        if key in mod.__all__:
            setattr(db, key, value)
del key, mod, value

db.__doc__ = __doc__
db.mapper = mapper
db.save = session.save
db.flush = session.flush
db.get_engine = get_engine
db.DatabaseManager = DatabaseManager


#: metadata for the core tables and the core table definitions
metadata = db.MetaData()


configuration = db.Table('configuration', metadata,
    db.Column('key', db.Unicode(100), primary_key=True),
    db.Column('value', db.Unicode)
)


plugins = db.Table('plugins', metadata,
    db.Column('name', db.Unicode(200), primary_key=True),
    db.Column('active', db.Boolean)
)


users = db.Table('users', metadata,
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('username', db.Unicode(30)),
    db.Column('first_name', db.Unicode(40)),
    db.Column('last_name', db.Unicode(80)),
    db.Column('display_name', db.Unicode(130)),
    db.Column('description', db.Unicode),
    db.Column('extra', db.PickleType),
    db.Column('pw_hash', db.String(70)),
    db.Column('email', db.Unicode(250)),
    db.Column('role', db.Integer)
)


sessions = db.Table('sessions', metadata,
    db.Column('sid', db.Unicode(32), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('data', db.PickleType),
    db.Column('last_change', db.DateTime)
)


tags = db.Table('tags', metadata,
    db.Column('tag_id', db.Integer, primary_key=True),
    db.Column('slug', db.Unicode(50)),
    db.Column('name', db.Unicode(50)),
    db.Column('description', db.Unicode)
)


posts = db.Table('posts', metadata,
    db.Column('post_id', db.Integer, primary_key=True),
    db.Column('pub_date', db.DateTime),
    db.Column('last_update', db.DateTime),
    db.Column('slug', db.Unicode(50)),
    db.Column('title', db.Unicode(50)),
    db.Column('intro', db.Unicode),
    db.Column('body', db.Unicode),
    db.Column('author_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('comments_enabled', db.Boolean),
    db.Column('pings_enabled', db.Boolean),
    db.Column('cache', db.PickleType),
    db.Column('status', db.Integer)
)


post_tags = db.Table('post_tags', metadata,
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.tag_id'))
)


comments = db.Table('comments', metadata,
    db.Column('comment_id', db.Integer, primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('author', db.Unicode(100)),
    db.Column('email', db.Unicode(250)),
    db.Column('www', db.Unicode(200)),
    db.Column('body', db.Unicode),
    db.Column('parent_id', db.Integer, db.ForeignKey('comments.comment_id')),
    db.Column('pub_date', db.DateTime),
    db.Column('blocked', db.Boolean),
    db.Column('blocked_msg', db.Unicode(250)),
    db.Column('submitter_ip', db.Unicode(100))
)


def init_database(engine):
    """
    This is also called form the upgrade database function but especially from
    the websetup. That's also why it takes an engine and not a textpress
    application.
    """
    metadata.create_all(engine)

    # create the nobody user if it's missing
    from textpress.models import NOBODY_USER_ID, ROLE_NOBODY
    nobody = engine.execute(db.select([users.c.user_id], users.c.user_id
                                      == NOBODY_USER_ID)).fetchone()
    if nobody is None:
        engine.execute(users.insert(),
            username='Nobody',
            user_id=NOBODY_USER_ID,
            role=ROLE_NOBODY
        )


def upgrade_database(app):
    """
    Check if the tables are up to date and perform an upgrade.
    Currently creating is enough. Once there are release verisons
    this function will upgrade the database structure too.
    """
    init_database(app.database_engine)
