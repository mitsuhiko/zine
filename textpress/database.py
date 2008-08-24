# -*- coding: utf-8 -*-
"""
    textpress.database
    ~~~~~~~~~~~~~~~~~~

    This module is a rather complex layer on top of SQLAlchemy 0.4.
    Basically you will never use the `textpress.database` module except you
    are a core developer, but always the high level
    :mod:`~textpress.database.db` module which you can import from the
    :mod:`textpress.api` module.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Christopher Grebs,
                             Ali Afshar.
    :license: GNU GPL.
"""
import sys
from os import path
from datetime import datetime, timedelta
from types import ModuleType

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.util import to_list
from sqlalchemy.engine.url import make_url

from textpress.utils import local, local_manager


def mapper(*args, **kwargs):
    """This works like the regular sqlalchemy mapper function but adds our
    own database manager extension.  Models mapped to tables with this mapper
    are automatically saved on the session unless ``_tp_no_save=True`` is
    passed to the constructor of a database model.
    """
    kwargs['extension'] = extensions = to_list(kwargs.get('extension', []))
    extensions.append(ManagerExtension())
    return orm.mapper(*args, **kwargs)


def get_engine():
    """Return the active database engine (the database engine of the active
    application).  If no application is enabled this has an undefined behavior.
    If you are not sure if the application is bound to the active thread, use
    :func:`~textpress.application.get_application` and check it for `None`.
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
    info = make_url(uri)

    # if we have the sqlite driver make the database relative to the
    # instance folder
    if info.drivername == 'sqlite' and relative_to is not None:
        info.database = path.join(relative_to, info.database)

    # if mysql is the database engine and no connection encoding is
    # provided we set it to utf-8
    elif info.drivername == 'mysql':
        info.query.setdefault('charset', 'utf8')

    return sqlalchemy.create_engine(info, convert_unicode=True, echo=echo)


class ManagerExtension(orm.MapperExtension):
    """Use Django-like database managers."""

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
        session = kwargs.pop('_sa_session', None)
        if session is None:
            session = self.get_session()
        if not kwargs.pop('_tp_no_save', False):
            session._save_without_cascade(instance)
        return orm.EXT_CONTINUE

    def init_failed(self, mapper, class_, oldinit, instance, args, kwargs):
        orm.object_session(instance).expunge(instance)
        return orm.EXT_CONTINUE


class DatabaseManager(object):
    """Baseclass for the database manager which you can also subclass to add
    more methods to it and attach to models by hand.  An instance of this
    manager is added to model classes automatically as `objects` unless there
    is at least one model manager specified on the class.

    Example for custom managers::

        class UserManager(DatabaseManager):

            def authors(self):
                return self.filter(User.role >= ROLE_AUTHOR)


        class User(object):
            objects = UserManager()

    :meth:`bind` is called with the reference to the model automatically by
    the mapper extension to bind the manager to the model.
    """

    def __init__(self):
        self.model = None

    def bind(self, model):
        """Called automatically by the manager extension to bind the manager
        to the model.  This sets the :attr:`model` attribute of the manager
        and must not be called by hand.  Subclasses may override this method
        to react to the mapping.
        """
        if self.model is not None:
            raise RuntimeError('manager already bound to model')
        self.model = model

    @property
    def query(self):
        """A fresh queryset.  Subclasses can override this mapper to limit
        the queryset::

            class AuthorManager(DatabaseManager):

                @property
                def query(self):
                    query = DatabaseManager.query.__get__(self)
                    return query.filter(User.role >= ROLE_AUTHOR)
        """
        return session.registry().query(self.model)

    # add proxies to non-deprecated methods on the query object.
    for _name, _obj in orm.Query.__dict__.iteritems():
        if _name[0] != '_' and callable(_obj) and \
           'DEPRECATED' not in (_obj.__doc__ or ''):
            exec '''def %s(self, *args, **kwargs):
                        return self.query.%s(*args, **kwargs)''' % \
                 (_name, _name)
            locals()[_name].__doc__ = _obj.__doc__
    del _name, _obj


#: a new scoped session
session = orm.scoped_session(lambda: orm.create_session(
                             local.application.database_engine,
                             autoflush=True, autocommit=False),
                             local_manager.get_ident)

#: create a new module for all the database related functions and objects
sys.modules['textpress.database.db'] = db = ModuleType('db')
public_names = set(['mapper', 'get_engine', 'session', 'DatabaseManager'])
key = value = mod = None
for mod in sqlalchemy, orm:
    for key, value in mod.__dict__.iteritems():
        if key in mod.__all__:
            setattr(db, key, value)
            public_names.add(key)
del key, mod, value


db.mapper = mapper
db.get_engine = get_engine
db.create_engine = create_engine
for name in 'delete', 'save', 'flush', 'execute', 'begin', \
            'commit', 'rollback', 'clear', 'refresh', 'expire':
    setattr(db, name, getattr(session, name))
    public_names.add(name)
db.session = session
db.DatabaseManager = DatabaseManager

#: these members help documentation tools
db.__all__ = sorted(public_names)
db.__file__ = __file__

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
    db.Column('www', db.String(200)),
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
    db.Column('slug', db.String(150)),
    db.Column('uid', db.String(250)),
    db.Column('title', db.String(150)),
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
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('author', db.String(100)),
    db.Column('email', db.String(250)),
    db.Column('www', db.String(200)),
    db.Column('body', db.Text),
    db.Column('is_pingback', db.Boolean, nullable=False),
    db.Column('parser_data', db.PickleType),
    db.Column('parent_id', db.Integer, db.ForeignKey('comments.comment_id')),
    db.Column('pub_date', db.DateTime),
    db.Column('blocked_msg', db.String(250)),
    db.Column('submitter_ip', db.String(100)),
    db.Column('status', db.Integer, nullable=False)
)

pages = db.Table('pages', metadata,
    db.Column('page_id', db.Integer, primary_key=True),
    db.Column('key', db.String(25), unique=True),
    db.Column('title', db.String(200)),
    db.Column('body', db.Text),
    db.Column('extra', db.PickleType),
    db.Column('navigation_pos', db.Integer),
    db.Column('parent_id', db.Integer, db.ForeignKey('pages.page_id')),
)


def init_database(engine):
    """This is called from the websetup which explains why it takes an engine
    and not a textpress application.
    """
    metadata.create_all(engine)
