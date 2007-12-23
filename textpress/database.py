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

    We use the SQLAlchemy querysets to query the database. To get a raw
    queryset, all you have to do is to access `Model.objects.query` and you
    can fire up selects.  The default approach is this::

        Model.objects.query.filter(Model.something == "blub").all()

    You can chain as many calls as you want to further filter the objects
    before sending the request to the database.  The following methods on
    the queryset cause a select:

    `all`
        get all objects from the list.

    `first`
        get the first matching object.

    `count`
        just count all objects that would match.

    Because you can end up with quite a lot of chained methodcalls which can
    result in insanely long lines there are some methods that are useful
    shortcuts:

        Model.objects.all()
            equivalent to Model.objects.query.all()

        Model.objects.all(condition)
            equivalent to Model.objects.query.filter(condition).all()

        Model.objects.first()
            equivalent to Model.object.query.first()

        Model.objects.first(condition)
            equivalent to Model.objects.query.filter(condition).first()

        Model.objects.count()
            equivalent to Model.objects.query.count()

        Model.objects.count(condition)
            equivalent to Model.objects.query.filter(condition).all()

        Model.objects.get_by(condition)
            equivalent to Model.objects.query.filter_by(condition).first()

        Model.objects.get(ident)
            equivalent to Model.objects.query.get(int(ident))
            just that it eats up exceptions that can occour during integer
            conversion and just return None.

    If you want to add your own methods to the database manager keep in mind
    that they should always return a list!  If they don't because you want
    to further filter them in the view you have to prefix them with `filter_`
    and document their behaviour.

    Some of the methods of this class are aliases.
    """

    def __init__(self):
        self.model = None

    def bind(self, model):
        """Called automatically by the `ManagerExtension`."""
        if self.model is not None:
            raise RuntimeError('manager already bound to model')
        self.model = model

    @property
    def query(self):
        """Return a new queryset."""
        return session.registry().query(self.model)

    def get(self, ident, **kw):
        """
        Return an instance of the object based on the given identifier
        (primary key), or `None` if not found.

        If you have more than one primary_key you can pass it a tuple
        with the column values in the order of the table primary key
        definitions.
        """
        if not isinstance(ident, tuple):
            try:
                ident = int(ident)
            except (TypeError, ValueError):
                return
        return self.query.get(ident, **kw)

    def get_by(self, **kw):
        """
        Get a query set by some rules.
        """
        return self.query.filter_by(**kw).first()

    def all(self, *args, **kw):
        """
        Return a list of all objects. not queryable any further.
        """
        if not args and not kw:
            return self.query.all()
        return self.query.filter(*args, **kw).all()

    def first(self, *args, **kw):
        """
        Return the first object that matches the query.
        """
        if not args and not kw:
            return self.query.first()
        return self.query.filter(*args, **kw).first()

    def count(self, *args, **kw):
        """
        Count all objects matching an expression.
        """
        return self.query.count(*args, **kw)



session = orm.scoped_session(lambda: orm.create_session(
                             local.application.database_engine,
                             autoflush=True, transactional=True),
                             local_manager.get_ident)
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

#: called at the end of a request
cleanup_session = session.remove

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
    db.Column('parser_data', db.PickleType),
    db.Column('extra', db.PickleType),
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
    db.Column('parser_data', db.PickleType),
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
