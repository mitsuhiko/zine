# -*- coding: utf-8 -*-
"""
    textpress.models
    ~~~~~~~~~~~~~~~~

    The core models and query helper functions.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from math import ceil, log
from datetime import date, datetime, timedelta
from collections import defaultdict

from textpress.database import users, tags, posts, post_tags, comments, db
from textpress.utils import Pagination, gen_pwhash, check_pwhash, gen_slug, \
     markup
from textpress.application import get_application, get_request


#: user rules
ROLE_ADMIN = 4
ROLE_EDITOR = 3
ROLE_AUTHOR = 2
ROLE_SUBSCRIBER = 1
ROLE_NOBODY = 0

#: all kind of states for a post
STATUS_PRIVATE = 0
STATUS_DRAFT = 1
STATUS_PUBLISHED = 2

#: user id of the nobody user
NOBODY_USER_ID = 0


def get_post_list(year=None, month=None, day=None, tag=None, author=None,
                  page=1, ignore_role=False):
    """
    Return a dict with pagination, the current posts, number of pages, total
    posts and all that stuff for further processing.

    If the role is ignored only published items are returned, otherwise the
    items the current user can see.
    """
    role = ROLE_NOBODY
    if not ignore_role:
        req = get_request()
        if req is not None:
            role = req.user.role
    app = get_application()
    per_page = app.cfg['posts_per_page']
    url_args = {}
    if year is not None:
        endpoint = 'blog/archive'
        url_args['year'] = year
    elif tag is not None:
        url_args['slug'] = tag
        endpoint = 'blog/show_tag'
    elif author is not None:
        url_args['username'] = author
        endpoint = 'blog/show_user'
    else:
        endpoint = 'blog/index'
        if month is not None:
            url_args['month'] = month
        if day is not None:
            url_args['day'] = day
        if tag is not None:
            url_args['slug'] = tag

    conditions = []
    p = Post.c

    # subcribers and normal users can just view the page if it was published
    if role <= ROLE_SUBSCRIBER:
        conditions.append((p.status == STATUS_PUBLISHED) |
                          (p.pub_date >= datetime.utcnow()))

    # otherwise check if we are an author, in that case only show
    # the own posts.
    elif role == ROLE_AUTHOR:
        # it's safe to access req here because we only have
        # a non ROLE_NOBODY role if there was a request.
        conditions.append((p.status == STATUS_PUBLISHED) |
                          (p.author_id == req.user.user_id))

    # limit the posts to match the criteria passed to the function
    # if there is at least the year defined.
    if year is not None:
        # show a whole year
        if month is None:
            conditions.append((p.pub_date >= datetime(year, 1, 1)) &
                              (p.pub_date < datetime(year + 1, 1, 1)))
        # show one month
        elif day is None:
            conditions.append((p.pub_date >= datetime(year, month, 1)) &
                              (p.pub_date < (month == 12 and
                                             datetime(year + 1, 1, 1) or
                                             datetime(year, month + 1, 1))))
        # show one day
        else:
            conditions.append((p.pub_date >= datetime(year, month, day)) &
                              (p.pub_date < datetime(year, month, day) +
                                            timedelta(days=1)))
    # all posts for a tag
    elif tag is not None:
        if isinstance(tag, (int, long)):
            tag_join = tags.c.tag_id == tag
        elif isinstance(tag, basestring):
            tag_join = tags.c.slug == tag
        else:
            tag_join = tags.c.tag_id == tag.tag_id
        conditions.append((post_tags.c.post_id == p.post_id) &
                          (post_tags.c.tag_id == tags.c.tag_id) & tag_join)

    # all posts for an author
    elif author is not None:
        if isinstance(author, (int, long)):
            conditions.append(p.author_id == author)
        elif isinstance(author, basestring):
            conditions.append((p.author_id == users.c.user_id) &
                              (users.c.username == author))
        else:
            conditions.append(p.author_id == author.user_id)

    # send the query
    q = db.and_(*conditions)
    postlist = Post.select(q, limit=per_page, offset=per_page * (page - 1))
    pagination = Pagination(endpoint, page, per_page, Post.count(q), url_args)

    return {
        'pagination':       pagination,
        'posts':            postlist,
        'probably_404':     page != 1 and not postlist,
    }


def get_tag_cloud(max=None, ignore_role=False):
    """Get a nifty tag cloud."""
    role = ROLE_NOBODY
    if ignore_role:
        req = get_request()
        if req is not None:
            role = req.user.role

    # get a query
    p = post_tags.c
    p2 = posts.c
    t = tags.c

    q = (p.tag_id == t.tag_id) & (p.post_id == p2.post_id)

    # do the role checking
    if role <= ROLE_SUBSCRIBER:
        q &= ((p2.status == STATUS_PUBLISHED) |
              (p2.pub_date >= datetime.utcnow()))

    elif role == ROLE_AUTHOR:
        # it's safe to access req here because we only have
        # a non ROLE_NOBODY role if there was a request.
        q &= ((p2.status == STATUS_PUBLISHED) |
              (p2.author_id == req.user.user_id))

    s = db.select([t.slug, t.name, db.func.count(p.post_id).label('s_count')],
                  p.tag_id == t.tag_id,
                  group_by=[t.slug, t.name]).alias('post_count_query').c

    options = {'order_by': [db.asc(s.s_count)]}
    if max is not None:
        options['limit'] = max
    q = db.select([s.slug, s.name, s.s_count], **options)

    items = [{
        'slug':     row.slug,
        'name':     row.name,
        'count':    row.s_count,
        'size':     100 + log(row.s_count or 1) * 20
    } for row in get_application().database_engine.execute(q)]

    items.sort(key=lambda x: x['name'].lower())
    return items


def get_post_archive_summary(detail='months', limit=None, ignore_role=False):
    """
    Query function to get the archive of the blog. Usually used directly from
    the templates to add some links to the sidebar.
    """
    role = ROLE_NOBODY
    if not ignore_role:
        req = get_request()
        if req is not None:
            role = req.user.role
        engine = req.app.database_engine
    else:
        engine = get_application().database_engine

    p = posts.c
    now = datetime.utcnow()

    # do the role checking
    if role <= ROLE_SUBSCRIBER:
        q = ((p.status == STATUS_PUBLISHED) |
             (p.pub_date >= now))
    elif role == ROLE_AUTHOR:
        # it's safe to access req here because we only have
        # a non ROLE_NOBODY role if there was a request.
        q = ((p.status == STATUS_PUBLISHED) |
             (p.author_id == req.user.user_id))
    else:
        q = None

    # XXX: currently we also return months without articles in it.
    # other blog systems do not, but because we use sqlalchemy we have
    # to go with the functionality provided. Currently there is no way
    row = engine.execute(db.select([p.pub_date], q,
            order_by=[db.asc(p.pub_date)], limit=1)).fetchone()

    there_are_more = False
    result = []

    if row is not None:
        now = date(now.year, now.month, now.day)
        oldest = date(row.pub_date.year, row.pub_date.month, row.pub_date.day)
        result = [now]

        there_are_more = False
        if detail == 'years':
            now, oldest = [x.replace(month=1, day=1) for x in now, oldest]
            while True:
                now = now.replace(year=now.year - 1)
                if now < oldest:
                    break
                result.append(now)
            else:
                there_are_more = True
        elif detail == 'months':
            now, oldest = [x.replace(day=1) for x in now, oldest]
            while limit is None or len(result) < limit:
                if not now.month - 1:
                    now = now.replace(year=now.year - 1, month=1)
                else:
                    now = now.replace(month=now.month - 1)
                if now < oldest:
                    break
                result.append(now)
            else:
                there_are_more = True
        elif detail == 'days':
            while limit is None or len(result) < limit:
                now = now - timedelta(days=1)
                if now < oldest:
                    break
                result.append(now)
            else:
                there_are_more = True
        else:
            raise ValueError('detail must be years, months, or days')

    return {
        detail:     result,
        'more':     there_are_more,
        'empty':    not result
    }


class User(object):
    """Pepresents an user."""

    def __init__(self, username, password, email, first_name='',
                 last_name='', description='', role=ROLE_SUBSCRIBER):
        self.username = username
        self.set_password(password)
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.description = description
        self.extra = {}
        self.display_name = self.username
        self.role = role

    @staticmethod
    def get_nobody():
        return User.get(NOBODY_USER_ID)

    @staticmethod
    def get_authors():
        return User.select(User.c.role >= ROLE_AUTHOR)

    @staticmethod
    def get_all_but_nobody():
        return User.select(User.c.user_id != NOBODY_USER_ID)

    @property
    def is_somebody(self):
        return self.user_id != NOBODY_USER_ID

    @property
    def is_manager(self):
        return self.role >= ROLE_AUTHOR

    @property
    def role_as_string(self):
        """Human readable version of the role id."""
        from textpress.api import _
        if self.role == ROLE_ADMIN:
            return _('Administrator')
        elif self.role == ROLE_EDITOR:
            return _('Editor')
        elif self.role == ROLE_AUTHOR:
            return _('Author')
        elif self.role == ROLE_SUBSCRIBER:
            return _('Subscriber')
        return _('Nobody')

    def _set_display_name(self, value):
        self._display_name = value

    def _get_display_name(self):
        from string import Template
        return Template(self._display_name).safe_substitute(
            nick=self.username,
            first=self.first_name,
            last=self.last_name
        )

    display_name = property(_get_display_name, _set_display_name)

    def set_password(self, password):
        self.pw_hash = gen_pwhash(password)

    def check_password(self, password):
        return check_pwhash(self.pw_hash, password)

    def get_url_values(self):
        if self.role >= ROLE_AUTHOR:
            return 'blog/show_author', {
                'username': self.username
            }

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.username
        )


class Post(object):
    """Represents one blog post."""

    def __init__(self, title, author, body, intro='', slug=None,
                 pub_date=None, last_update=None, comments_enabled=True,
                 pings_enabled=True, status=STATUS_PUBLISHED):
        self.title = title
        if isinstance(author, (int, long)):
            self.author_id = author
        else:
            self.author = author
        self.cache = {}
        self.raw_intro = intro
        self.raw_body = body
        if slug is None:
            self.auto_slug()
        else:
            self.slug = slug
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        if last_update is None:
            last_update = pub_date
        self.last_update = last_update
        self.comments_enabled = comments_enabled
        self.pings_enabled = pings_enabled
        self.status = status

    @staticmethod
    def by_timestamp_and_slug(year, month, day, slug):
        """Get an item by year, month, day, and the post slug."""
        start = datetime(year, month, day)
        return Post.selectfirst(
            (Post.c.pub_date >= start) &
            (Post.c.pub_date < start + timedelta(days=1)) &
            (Post.c.slug == slug)
        )

    @property
    def root_comments(self):
        """Return only the comments for this post that don't have a parent."""
        return [x for x in self.comments if x.parent is None]

    def _get_raw_intro(self):
        return self._raw_intro

    def _set_raw_intro(self, value):
        from textpress.htmlprocessor import parse, dump_tree
        tree = parse(value)
        self._raw_intro = value
        self._intro_cache = tree
        self.cache['intro'] = dump_tree(tree)

    def _get_intro(self):
        if not hasattr(self, '_intro_cache'):
            from textpress.htmlprocessor import load_tree
            self._intro_cache = load_tree(self.cache['intro'])
        return self._intro_cache

    def _set_intro(self, value):
        from textpress.htmlprocessor import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_intro')
        self._intro_cache = value
        self.cache['intro'] = dump_tree(value)

    raw_intro = property(_get_raw_intro, _set_raw_intro)
    intro = property(_get_intro, _set_intro)

    def _get_raw_body(self):
        return self._raw_body

    def _set_raw_body(self, value):
        from textpress.htmlprocessor import parse, dump_tree
        tree = parse(value)
        self._raw_body = value
        self._body_cache = tree
        self.cache['body'] = dump_tree(tree)

    def _get_body(self):
        if not hasattr(self, '_body_cache'):
            from textpress.htmlprocessor import load_tree
            self._body_cache = load_tree(self.cache['body'])
        return self._body_cache

    def _set_body(self, value):
        from textpress.htmlprocessor import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_body')
        self._body_cache = value
        self.cache['body'] = dump_tree(value)

    raw_body = property(_get_raw_body, _set_raw_body)
    body = property(_get_body, _set_body)

    def auto_slug(self):
        """Generate a slug for this post."""
        self.slug = gen_slug(self.title)

    def refresh_cache(self):
        """Update the cache."""
        self.raw_body = self.raw_body
        self.raw_intro = self.raw_intro

    def can_access(self, user=None):
        """
        Check if the current user or the user provided can access
        this post. If there is no user there must be a request object
        for this thread defined.
        """
        # published posts are always accessible
        if self.status == STATUS_PUBLISHED and \
           self.pub_date <= datetime.utcnow():
            return True

        if user is None:
            user = get_request().user
        elif isinstance(user, (int, long)):
            user = User.get(user)

        # simple rule: admins and editors may always
        if user.role in (ROLE_ADMIN, ROLE_EDITOR):
            return True
        # subscribers and anonymous users may never
        elif user.role in (ROLE_SUBSCRIBER, ROLE_NOBODY):
            return False
        # authors here, they can only view it if they are the
        # author of this post.
        else:
            return self.author == user

    def get_url_values(self):
        return 'blog/show_post', {
            'year':     self.pub_date.year,
            'month':    self.pub_date.month,
            'day':      self.pub_date.day,
            'slug':     self.slug
        }

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.title
        )


class Tag(object):
    """Represents a tag."""

    def __init__(self, name, description='', slug=None):
        self.name = name
        if slug is None:
            self.auto_slug()
        else:
            self.slug = slug
        self.description = description

    @staticmethod
    def get_or_create(slug, name=None):
        """Get the tag for this slug or create it if it does not exist."""
        tag = Tag.get_by(slug=slug)
        if tag is None:
            if name is None:
                name = slug
            tag = Tag(name, slug=slug)
        return tag

    def auto_slug(self):
        """Generate a slug for this tag."""
        self.slug = gen_slug(self.name)

    def get_url_values(self):
        return 'blog/show_tag', {
            'slug':     self.slug
        }

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.slug
        )


class Comment(object):
    """Represent one comment."""

    def __init__(self, post, author, email, www, body, parent=None, pub_date=None,
                 submitter_ip='0.0.0.0'):
        if isinstance(post, (int, long)):
            self.post_id = post
        else:
            self.post = post
        self.author = author
        self.email = email
        self.www = www
        self.body = markup(body)
        if isinstance(parent, (int, long)):
            self.parent_id = parent
        else:
            self.parent = parent
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        self.blocked = False
        self.blocked_msg = None
        self.submitter_ip = submitter_ip

    @staticmethod
    def get_blocked(self):
        """Get all blocked comments."""
        return Comment.select(Comment.c.blocked == True)

    def can_see(self, user=None):
        """Check if the current user or the user given can see this comment"""
        if not self.blocked:
            return True
        if user is None:
            user = get_request().user
        elif isinstance(user, (int, long)):
            user = User.get(user)
        return user.role >= ROLE_EDITOR

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


# connect the tables.
db.mapper(User, users, properties={
    '_display_name':    users.c.display_name,
    'posts':            db.relation(Post, backref='author')
})
db.mapper(Tag, tags)
db.mapper(Comment, comments, properties={
    'children': db.relation(Comment,
        primaryjoin=comments.c.parent_id == comments.c.comment_id,
        cascade='all', order_by=[db.asc(comments.c.pub_date)],
        backref=db.backref('parent', remote_side=[comments.c.comment_id]),
        lazy=True
    )
}, order_by=[db.desc(comments.c.pub_date)])
db.mapper(Post, posts, properties={
    '_raw_body':    posts.c.body,
    '_raw_intro':   posts.c.intro,
    'comments':     db.relation(Comment, backref='post',
                                order_by=[db.asc(comments.c.pub_date)]),
    'tags':         db.relation(Tag, secondary=post_tags, lazy=False,
                                order_by=[db.asc(tags.c.name)],
                                cascade='all, expunge', backref='posts')
}, order_by=[db.desc(posts.c.pub_date)])
