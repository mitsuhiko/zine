"""Switch to split tables for comments, posts and texts"""
from copy import deepcopy

from sqlalchemy.exceptions import ProgrammingError, OperationalError
from sqlalchemy.types import MutableType, TypeDecorator

from zine.upgrades.versions import *

metadata1 = db.MetaData()
metadata2 = db.MetaData()

# Also define ZEMLParserData here in case it changes. This way it won't break
# the change script
class ZEMLParserData(MutableType, TypeDecorator):
    """Holds parser data."""

    impl = db.Binary

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

users_old = db.Table('users', metadata1,
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

users_new = db.Table('users', metadata2,
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

texts = db.Table('texts', metadata2,
    db.Column('text_id', db.Integer, primary_key=True),
    db.Column('text', db.Text),
    db.Column('parser_data', ZEMLParserData),
    db.Column('extra', db.PickleType)
)

# See http://www.sqlalchemy.org/trac/ticket/1071
posts_new_seq = db.Sequence('posts_post_id_seq_migrate_script_001')
posts_new = db.Table('posts', metadata2,
    db.Column('post_id', db.Integer, posts_new_seq, primary_key=True),
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

posts_old = db.Table('posts', metadata1,
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

comments_old = db.Table('comments', metadata1,
    db.Column('comment_id', db.Integer, primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.post_id')),
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id')),
    db.Column('author', db.String(160)),
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

# See http://www.sqlalchemy.org/trac/ticket/1071
new_comments_seq = db.Sequence('comments_comment_id_seq_migrate_script_001')
comments_new = db.Table('comments', metadata2,
    db.Column('comment_id', db.Integer, new_comments_seq, primary_key=True),
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

class PostOld(object):
    post_id = None
    def __init__(self, pub_date, last_update, slug, uid, title,
                 text, author_id, parser_data, comments_enabled, pings_enabled,
                 content_type, status, extra):
        self.pub_date = pub_date
        self.last_update = last_update
        self.slug = slug
        self.uid = uid
        self.title = title
        self.author_id = author_id
        self.parser_data = parser_data
        self.comments_enabled = comments_enabled
        self.pings_enabled = pings_enabled
        self.content_type = content_type
        self.status = status
        self.extra = extra


class PostNew(object):
    post_id = text_id = None
    def __init__(self, pub_date, last_update, slug, uid, title,
                 author_id, comments_enabled, comment_count, pings_enabled,
                 content_type, status):
        self.pub_date = pub_date
        self.last_update = last_update
        self.slug = slug
        self.uid = uid
        self.title = title
        self.author_id = author_id
        self.comments_enabled = comments_enabled
        self.comment_count = comment_count
        self.pings_enabled = pings_enabled
        self.content_type = content_type
        self.status = status


class Text(object):
    def __init__(self, text, parser_data, extra):
        self.text = text
        self.parser_data = parser_data
        self.extra = extra


class CommentNew(object):
    comment_id = None
    def __init__(self, user_id, author, email, www, is_pingback, pub_date,
                 blocked_msg, submitter_ip, status):
        self.user_id = user_id
        self.author = author
        self.email = email
        self.www = www
        self.is_pingback = is_pingback
        self.pub_date = pub_date
        self.blocked_msg = blocked_msg
        self.submitter_ip = submitter_ip
        self.status = status


class CommentOld(object):
    comment_id = None
    def __init__(self, user_id, author, email, www, text, is_pingback,
                 parser_data, pub_date, blocked_msg, submitter_ip,
                 status):
        self.user_id = user_id
        self.author = author
        self.email = email
        self.www = www
        self.text = text
        self.is_pingback = is_pingback
        self.parser_data = parser_data
        self.pub_date = pub_date
        self.blocked_msg = blocked_msg
        self.submitter_ip = submitter_ip
        self.status = status


class User(object):
    pass


def map_tables(mapper):
    clear_mappers()

    mapper(PostOld, posts_old, properties=dict(
        comments = db.relation(
            CommentOld, backref='post', lazy=False,
            primaryjoin=posts_old.c.post_id == comments_old.c.post_id,
            order_by=[db.asc(comments_old.c.comment_id),
                      db.asc(comments_old.c.parent_id)])
    ), order_by=db.asc(posts_old.c.post_id))

    mapper(PostNew, posts_new, properties=dict(
        t = db.relation(Text, backref="post", uselist=False, lazy=False),
        comments = db.relation(
            CommentNew, backref='post', lazy=False,
            primaryjoin=posts_new.c.post_id == comments_new.c.post_id,
            order_by=[db.asc(comments_new.c.comment_id),
                      db.asc(comments_new.c.parent_id)])
    ), order_by=db.asc(posts_new.c.post_id))

    mapper(Text, texts)

    mapper(User, users_old)

    mapper(CommentOld, comments_old, order_by=db.asc(comments_old.c.comment_id),
        properties=dict(
            children = db.relation(
                CommentOld,
                primaryjoin=comments_old.c.parent_id == comments_old.c.comment_id,
                order_by=[db.asc(comments_old.c.pub_date)],
                backref=db.backref(
                    'parent', remote_side=[comments_old.c.comment_id],
                    primaryjoin=comments_old.c.parent_id == comments_old.c.comment_id
                ), lazy=True)
        )
    )

    mapper(CommentNew, comments_new, properties=dict(
        t = db.relation(Text, backref="comment", uselist=False, lazy=False),
        children = db.relation(CommentNew,
            primaryjoin=comments_new.c.parent_id == comments_new.c.comment_id,
            order_by=[db.asc(comments_new.c.pub_date)],
            backref=db.backref(
                'parent', remote_side=[comments_new.c.comment_id],
                primaryjoin=comments_new.c.parent_id == comments_new.c.comment_id
            ), lazy=True)
        ), order_by=db.asc(comments_new.c.comment_id)
    )


def upgrade(migrate_engine):
    # Upgrade operations go here. Don't create your own engine
    # bind migrate_engine to your metadata

    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(session.mapper)

    # Bind the engine
    metadata1.bind = migrate_engine
    metadata2.bind = migrate_engine

    yield '<div class="message info">'
    yield '<span class="progress">.&nbsp;&nbsp;</span>comment<br/>\n'
    yield '<span class="progress">+&nbsp;&nbsp;</span>comment with parent_id<br/>\n'
    yield '<span class="progress">E&nbsp;&nbsp;</span>error handling comment<br/>\n'
    yield '</div>\n'

    yield '<ul>'
    yield '  <li>Auto-loading needed extra tables</li>\n'
    post_links = db.Table('post_links', metadata2, autoload=True)
    post_categories = db.Table('post_categories', metadata2, autoload=True)
    post_tags = db.Table('post_tags', metadata2, autoload=True)

    yield '  <li>Dropping old posts table indexes</li>\n'
    for index in posts_old.indexes:
        try:
            index.drop(migrate_engine)
        except (ProgrammingError, OperationalError):
            # Index is on table definition but not on the database!? Weird
            pass
    yield '  <li>Dropping existing posts sequence if it exists</li>\n'
    try:
        posts_new_seq.drop(migrate_engine)
    except Exception, err:
        pass


    yield '  <li>Dropping existing comments sequence if it exists</li>\n'
    try:
        new_comments_seq.drop(migrate_engine)
    except Exception, err:
        pass

    yield '  <li>Querying for old posts from database</li>\n'
    yield '  <li>Got %d posts</li>\n' % session.query(PostOld).count()
    session.close()

    yield '  <li>Create texts table</li>\n'
    texts.create(migrate_engine)

    yield '  <li>Renaming old posts table</li>\n'
    posts_old.rename('posts_upgrade')

    yield '  <li>Create new posts table</li>\n'
    posts_new.create(migrate_engine)

    yield '  <li>Renaming old comments table</li>\n'
    comments_old.rename('comments_upgrade')

    yield '  <li>Create new comments table</li>\n'
    comments_new.create(migrate_engine)


    yield '  <li>Migrate old posts into new table:</li>\n'
    yield '<ul>'
    for post in session.query(PostOld).all():
        yield '    <li>%s</li>\n' % post.title
        yield '<ul>'
        new_post = PostNew(post.pub_date,
                           post.last_update,
                           post.slug,
                           post.uid,
                           post.title,
                           post.author_id,
                           post.comments_enabled,
                           len(post.comments),
                           post.pings_enabled,
                           post.content_type,
                           post.status)
        yield '      <li>Create new text entry</li>\n'
        new_post.t = Text(post.text, post.parser_data, post.extra)
        session.add(new_post)
        session.commit()
        comments_count = len(post.comments)
        n = (comments_count >= 100 and comments_count or 0)
        yield '      <li>Migrating %d comments <span class="progress">' % \
                                                                comments_count
        for comment in post.comments:
            if n >= 100:
                n = 0
                yield '<br/>\n      '
            parent_comment_new = None
            if comment.parent_id:
                parent_comment_old = session.query(CommentOld) \
                                                        .get(comment.parent_id)
                parent_comment_new = session.query(CommentNew).filter(db.and_(
                    CommentNew.author==parent_comment_old.author,
                    CommentNew.pub_date==parent_comment_old.pub_date,
                    CommentNew.status==parent_comment_old.status,
                    CommentNew.submitter_ip==parent_comment_old.submitter_ip,
                    CommentNew.user_id==parent_comment_old.user_id,
                    CommentNew.www==parent_comment_old.www
                )).first()
                if not parent_comment_new:
                    yield 'E'
                else:
                    yield '+'
            else:
                yield '.'
            new_comment = CommentNew(
                comment.user_id, comment.author, comment.email, comment.www,
                comment.is_pingback,
                comment.pub_date, comment.blocked_msg, comment.submitter_ip,
                comment.status
            )
            new_comment.t = Text(comment.text, comment.parser_data, None)
            new_comment.parent = parent_comment_new
            new_post.comments.append(new_comment)
            session.commit()    # Need to commit every comment in order to
                                # later retrieve accurate parent_id's
            n += 1
        yield '</span></li>\n'
        yield ('      <li>Update linked tables <tt>post_categories</tt>, '
               '<tt>post_links</tt> and <tt>post_tags</tt> for new '
               '<tt>post_id</tt></li>\n')
        migrate_engine.execute(post_categories.update(
            whereclause=post_categories.c.post_id==post.post_id,
            values={'post_id': new_post.post_id}))
        migrate_engine.execute(post_links.update(
            whereclause=post_links.c.post_id==post.post_id,
            values={'post_id': new_post.post_id}))
        migrate_engine.execute(post_tags.update(
            whereclause=post_tags.c.post_id==post.post_id,
            values={'post_id': new_post.post_id}))
        yield '</ul>'
    session.close()
    yield '</ul>'

    yield '  <li>Drop old comments table</li>\n'
    drop_table(comments_old, migrate_engine)

    yield '  <li>Drop old posts table</li>\n'
    drop_table(posts_old, migrate_engine)

    yield '</ul>'


def downgrade(migrate_engine):
    # Operations to reverse the above upgrade go here.
    session = scoped_session(lambda: create_session(migrate_engine,
                                                    autoflush=True,
                                                    autocommit=False))
    map_tables(session.mapper)

    # Bind the engine
    metadata1.bind = migrate_engine
    metadata2.bind = migrate_engine

    yield '<div class="message info">'
    yield '<span class="progress">.&nbsp;&nbsp;</span>comment<br/>\n'
    yield '<span class="progress">+&nbsp;&nbsp;</span>comment with parent_id<br/>\n'
    yield '<span class="progress">E&nbsp;&nbsp;</span>error handling comment<br/>\n'
    yield '</div>\n'

    yield '<ul>'
    yield '  <li>Auto-loading needed extra tables</li>\n'
    post_links = db.Table('post_links', metadata2, autoload=True)
    post_categories = db.Table('post_categories', metadata2, autoload=True)
    post_tags = db.Table('post_tags', metadata2, autoload=True)

    yield '  <li>Dropping new posts table indexes</li>\n'
    for index in posts_new.indexes:
        try:
            index.drop(migrate_engine)
        except (ProgrammingError, OperationalError):
            # Index is on table definition but not on the database!? Weird
            pass

    yield '  <li>Querying new posts from database</li>\n'
    yield '  <li>Got %d posts</li>\n' % session.query(PostNew).count()
    session.close()

    yield '  <li>Renaming new posts table</li>\n'
    posts_new.rename('posts_downgrade')

    yield '  <li>Create old posts table</li>\n'
    posts_old.create(migrate_engine)

    yield '  <li>Renaming new comments table</li>\n'
    comments_new.rename('comments_downgrade')

    yield '  <li>Create old comments table</li>\n'
    comments_old.create(migrate_engine)

    yield '  <li>Migrate new posts into old table:</li>\n'
    yield '<ul>'
    for post in session.query(PostNew).all():
        yield '    <li>%s</li>\n' % post.title
        yield '<ul>'
        old_post = PostOld(post.pub_date,
                           post.last_update,
                           post.slug,
                           post.uid,
                           post.title,
                           post.t.text,
                           post.author_id,
                           post.t.parser_data,
                           post.comments_enabled,
                           post.pings_enabled,
                           post.content_type,
                           post.status,
                           post.t.extra)
        session.add(old_post)
        session.commit()
        comments_count = len(post.comments)
        n = comments_count >= 100 and comments_count or 0
        yield '      <li>Migrating %d comments <span class="progress">' % \
                                                                comments_count
        for comment in post.comments:
            if n >= 100:
                n = 0
                yield '<br/>\n      '
            parent_comment_old = None
            if comment.parent_id:
                parent_comment_new = session.query(CommentNew) \
                                                        .get(comment.parent_id)
                parent_comment_old = session.query(CommentOld).filter(db.and_(
                    CommentOld.author==parent_comment_new.author,
                    CommentOld.pub_date==parent_comment_new.pub_date,
                    CommentOld.status==parent_comment_new.status,
                    CommentOld.submitter_ip==parent_comment_new.submitter_ip,
                    CommentOld.user_id==parent_comment_new.user_id,
                    CommentOld.www==parent_comment_new.www
                )).first()
                if not parent_comment_old:
                    yield 'E'
                else:
                    yield '+'
            else:
                yield '.'
            old_comment = CommentOld(
                comment.user_id, comment.author, comment.email, comment.www,
                comment.t.text, comment.is_pingback, comment.t.parser_data,
                comment.pub_date, comment.blocked_msg, comment.submitter_ip,
                comment.status
            )
            old_comment.parent = parent_comment_old
            old_post.comments.append(old_comment)
            session.commit()    # Need to commit every comment in order to
                                # later retrieve accurate parent_id's
            n +=1
        yield '</span></li>\n'

        yield ('      <li>Update linked tables <tt>post_categories</tt>, '
               '<tt>post_links</tt> and <tt>post_tags</tt> for old '
               '<tt>post_id</tt></li>\n')
        migrate_engine.execute(post_categories.update(
            whereclause=post_categories.c.post_id==post.post_id,
            values={'post_id': old_post.post_id}))
        migrate_engine.execute(post_links.update(
            whereclause=post_links.c.post_id==post.post_id,
            values={'post_id': old_post.post_id}))
        migrate_engine.execute(post_tags.update(
            whereclause=post_tags.c.post_id==post.post_id,
            values={'post_id': old_post.post_id}))
        session.close()
        yield '</ul>'
    yield '</ul>'
    yield '  <li>Drop new posts table</li>\n'
    drop_table(posts_new, migrate_engine)

    yield '  <li>Drop new comments table</li>\n'
    drop_table(comments_new, migrate_engine)

    yield '  <li>Drop texts table</li>\n'
    drop_table(texts, migrate_engine)

    yield '</ul>'
