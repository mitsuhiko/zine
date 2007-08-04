# -*- coding: utf-8 -*-
"""
    textpress.database
    ~~~~~~~~~~~~~~~~~~

    This module implements the database helper functions and defines
    the tables used in the core system.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime, timedelta
from thread import get_ident

import sqlalchemy
from sqlalchemy.ext.sessioncontext import SessionContext
from sqlalchemy.ext.assignmapper import assign_mapper


def session_factory():
    """Function used by the session context to get a new session."""
    from textpress.application import get_application
    return db.create_session(get_application().database_engine)


def mapper(cls, table, *args, **kwargs):
    """Like the sqlalchemy mapper but it registers with the context."""
    return assign_mapper(ctx, cls, table, *args, **kwargs)


def flush():
    """Flush the current session."""
    ctx.current.flush()


ctx = SessionContext(session_factory, get_ident)

# assemble the public database module. Just copy sqlalchemy
# and inject custom stuff.
db = type(sqlalchemy)('db')
db.__dict__.update(sqlalchemy.__dict__)
db.__dict__.update({
    'ctx':              ctx,
    'mapper':           mapper,
    'flush':            flush
})
del db.__file__

#: metadata for the core tables
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


def upgrade_database(app):
    """
    Check if the tables are up to date and perform an upgrade.
    Currently creating is enough. Once there are release verisons
    this function will upgrade the database structure too.
    """
    engine = app.database_engine
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
