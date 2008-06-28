# -*- coding: utf-8 -*-
"""
    textpress.models
    ~~~~~~~~~~~~~~~~

    The core models and query helper functions.

    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: GNU GPL.
"""
from math import ceil, log
from datetime import date, datetime, timedelta

from textpress.database import users, tags, posts, post_links, post_tags, \
     comments, db
from textpress.utils import Pagination, gen_pwhash, check_pwhash, gen_slug, \
     build_tag_uri
from textpress.application import get_application, get_request, url_for


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

#: Comment Status
COMMENT_MODERATED = 0
COMMENT_UNMODERATED = 1
COMMENT_BLOCKED_USER = 2
COMMENT_BLOCKED_SPAM = 3
COMMENT_BLOCKED_SYSTEM = 4


class UserManager(db.DatabaseManager):
    """Add some extra query methods to the user object."""

    def get_nobody(self):
        return AnonymousUser()

    def authors(self):
        return self.filter(User.role >= ROLE_AUTHOR)


class User(object):
    """Represents an user.

    If you change something on this model, even default values, keep in mind
    that the websetup does not use this model to create the admin account
    because at that time the TextPress system is not yet ready. Also update
    the code in `textpress.websetup.WebSetup.start_setup`.
    """

    objects = UserManager()
    is_somebody = True

    def __init__(self, username, password, email, first_name=u'',
                 last_name=u'', description=u'', role=ROLE_SUBSCRIBER):
        self.username = username
        if password is not None:
            self.set_password(password)
        else:
            self.disable()
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.description = description
        self.extra = {}
        self.display_name = u'$nick'
        self.role = role

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
        if self.pw_hash == '!':
            return False
        return check_pwhash(self.pw_hash, password)

    def disable(self):
        self.pw_hash = '!'

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


class AnonymousUser(User):
    """Fake model for anonymous users."""
    is_somebody = False
    display_name = 'Nobody'
    first_name = last_name = description = username = ''
    role = ROLE_NOBODY
    objects = UserManager()

    def __init__(self):
        pass

    def __nonzero__(self):
        return False

    def check_password(self, password):
        return False


class PostManager(db.DatabaseManager):
    """Add some extra methods to the post model."""

    def published(self, query=None, ignore_role=None):
        """Return a queryset for only published posts."""
        role = ROLE_NOBODY
        if query is None:
            query = self.query
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role
        p = posts.c

        if query is None:
            query = self.query

        if role <= ROLE_SUBSCRIBER:
            return query.filter(
                (p.status == STATUS_PUBLISHED) |
                (p.pub_date >= datetime.utcnow())
            )
        elif role == ROLE_AUTHOR:
            # it's safe to access req here because we only have
            # a non ROLE_NOBODY role if there was a request.
            return query.filter(
                (p.status == STATUS_PUBLISHED) |
                (p.author_id == req.user.user_id)
            )
        else:
            return query

    def filter_by_timestamp_and_slug(self, year, month, day, slug):
        """Filter by year, month, day, and the post slug."""
        start = datetime(year, month, day)
        return self.filter(
            (Post.pub_date >= start) &
            (Post.pub_date < start + timedelta(days=1)) &
            (Post.slug == slug)
        )

    def get_by_timestamp_and_slug(self, year, month, day, slug):
        """Get an item by year, month, day, and the post slug."""
        return self.filter_by_timestamp_and_slug(year, month, day, slug).first()

    def drafts(self, query=None, exclude=None, ignore_user=False,
               user=None):
        """Return a query that returns all drafts for the current user.
        or the user provided or no user at all if `ignore_user` is set.
        """
        if user is None and not ignore_user:
            req = get_request()
            if req and req.user:
                user = req.user
        if query is None:
            query = self.query
        query = query.filter(Post.status == STATUS_DRAFT)
        if user is not None:
            query = query.filter(Post.author_id == user.user_id)
        if exclude is not None:
            if isinstance(exclude, Post):
                exclude = Post.post_id
            query = query.filter(Post.post_id != exclude)
        return query

    def get_list(self, year=None, month=None, day=None, tag=None, author=None,
                 page=1, per_page=None, ignore_role=False, as_list=False):
        """Return a dict with pagination, the current posts, number of pages,
        total posts and all that stuff for further processing.

        If the role is ignored only published items are returned, otherwise the
        items the current user can see.
        """
        role = ROLE_NOBODY
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role
        app = get_application()
        if per_page is None:
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
            endpoint = 'blog/show_author'
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
        offset = per_page * (page - 1)
        postlist = Post.objects.filter(q).order_by(Post.pub_date.desc()) \
                               .offset(offset).limit(per_page)

        if as_list:
            return postlist.all()

        pagination = Pagination(endpoint, page, per_page,
                                Post.objects.filter(q).count(), url_args)

        return {
            'pagination':       pagination,
            'posts':            postlist.all(),
            'probably_404':     page != 1 and not postlist,
        }

    def get_archive_summary(self, detail='months', limit=None,
                            ignore_role=False):
        """Query function to get the archive of the blog. Usually used
        directly from the templates to add some links to the sidebar.
        """
        role = ROLE_NOBODY
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role

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
        # to go with the functionality provided.  Currently there is no way
        # to do date truncating in a database agnostic way.
        row = db.execute(db.select([p.pub_date], q,
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
                        now = now.replace(year=now.year - 1, month=12)
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

    def latest(self, limit=None, ignore_role=False):
        """Filter for the latest n posts."""
        query = self.published(ignore_role=ignore_role)
        if limit is not None:
            query = query[:limit]
        return query

    def search(self, query):
        """Search for posts by a query."""
        # XXX: use a sophisticated search
        q = self.query
        for word in query.split():
            q = q.filter(
                posts.c.body.like('%%%s%%' % word) |
                posts.c.intro.like('%%%s%%' % word) |
                posts.c.title.like('%%%s%%' % word)
            )
        return q.all()


class Post(object):
    """Represents one blog post."""

    objects = PostManager()

    def __init__(self, title, author, body, intro=None, slug=None,
                 pub_date=None, last_update=None, comments_enabled=True,
                 pings_enabled=True, status=STATUS_PUBLISHED,
                 parser=None, uid=None):
        app = get_application()
        self.title = title
        if isinstance(author, (int, long)):
            self.author_id = author
        else:
            self.author = author
        if parser is None:
            parser = app.cfg['default_parser']

        #: this holds the parsing cache and the name of the parser in use.
        #: in fact the intro and body cached data is not assigned right here
        #: but by the `raw_intro` and `raw_body` property callback a few lines
        #: below.
        self.parser_data = {'parser': parser}
        self.raw_intro = intro or ''
        self.raw_body = body or ''
        self.extra = {}

        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        if last_update is None:
            last_update = pub_date
        self.last_update = last_update
        self.comments_enabled = comments_enabled
        self.pings_enabled = pings_enabled
        self.status = status

        # always assign the slug at the very bottom because if it cannot
        # calculate a slug it will fall back to the time of the post, and
        # this requires pub_date to be assigned.
        if not slug:
            self.auto_slug()
        else:
            self.slug = slug

        # generate a UID if none is given
        if uid is None:
            uid = build_tag_uri(app, self.pub_date, 'post', self.slug)
        self.uid = uid

    @property
    def root_comments(self):
        """Return only the comments for this post that don't have a parent."""
        return [x for x in self.comments if x.parent is None]

    @property
    def comment_count(self):
        """The number of visible comments."""
        req = get_request()
        if req.user.role >= ROLE_AUTHOR:
            return len(self.comments)
        return len([x for x in self.comments if not x.blocked])

    @property
    def comment_feed_url(self):
        """The link to the comment feed."""
        return url_for('blog/atom_feed',
            year=self.pub_date.year,
            month=self.pub_date.month,
            day=self.pub_date.day,
            post_slug=self.slug
        )

    @property
    def is_draft(self):
        """True if this post is unpublished."""
        return self.status == STATUS_DRAFT

    @property
    def parser_missing(self):
        """If the parser for this post is not available this property will
        be `True`.  If such as post is edited the text area is grayed out
        and tells the user to reinstall the plugin that provides that
        parser.  Because it doesn't know the name of the plugin, the
        preferred was is telling it the parser which is available using
        the `parser` property.
        """
        app = get_application()
        return self.parser not in app.parsers

    def _get_parser(self):
        return self.parser_data['parser']

    def _set_parser(self, value):
        self.parser_data['parser'] = value

    parser = property(_get_parser, _set_parser)
    del _get_parser, _set_parser

    def _get_raw_intro(self):
        return self._raw_intro

    def _set_raw_intro(self, value):
        from textpress.parsers import parse
        from textpress.fragment import dump_tree
        tree = parse(value, self.parser, 'post-intro')
        self._raw_intro = value
        self._intro_cache = tree
        self.parser_data['intro'] = dump_tree(tree)

    def _get_intro(self):
        if not hasattr(self, '_intro_cache'):
            from textpress.fragment import load_tree
            self._intro_cache = load_tree(self.parser_data['intro'])
        return self._intro_cache

    def _set_intro(self, value):
        from textpress.fragment import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_intro')
        self._intro_cache = value
        self.parser_data['intro'] = dump_tree(value)

    raw_intro = property(_get_raw_intro, _set_raw_intro)
    intro = property(_get_intro, _set_intro)
    del _get_raw_intro, _set_raw_intro, _get_intro, _set_intro

    def _get_raw_body(self):
        return self._raw_body

    def _set_raw_body(self, value):
        from textpress.parsers import parse
        from textpress.fragment import dump_tree
        tree = parse(value, self.parser, 'post-body')
        self._raw_body = value
        self._body_cache = tree
        self.parser_data['body'] = dump_tree(tree)

    def _get_body(self):
        if not hasattr(self, '_body_cache'):
            from textpress.fragment import load_tree
            self._body_cache = load_tree(self.parser_data['body'])
        return self._body_cache

    def _set_body(self, value):
        from textpress.fragment import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_body')
        self._body_cache = value
        self.parser_data['body'] = dump_tree(value)

    raw_body = property(_get_raw_body, _set_raw_body)
    body = property(_get_body, _set_body)
    del _get_raw_body, _set_raw_body, _get_body, _set_body

    def find_urls(self):
        """Iterate over all urls in the text.  This will only work if the
        parser for this post is available.  If it's not the behavior is
        undefined.
        """
        from textpress.parsers import parse
        found = set()
        for text in self.raw_intro, self.raw_body:
            tree = parse(text, self.parser, 'linksearch', False)
            for node in tree.query('a[@href]'):
                href = node.attributes['href']
                if href not in found:
                    found.add(href)
                    yield href

    def auto_slug(self):
        """Generate a slug for this post."""
        self.slug = gen_slug(self.title)
        if not self.slug:
            self.slug = self.pub_date.strftime('%H:%M')

    def refresh_cache(self):
        """Update the cache."""
        self.raw_body = self.raw_body
        self.raw_intro = self.raw_intro

    def can_access(self, user=None):
        """Check if the current user or the user provided can access
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
            user = User.objects.get(user)

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

    @property
    def is_published(self):
        """`True` if the post is visible for everyone."""
        return self.can_access(AnonymousUser())

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


class PostLink(object):
    """Represents a link in a post.  This can be used for podcasts or other
    resources that require ``<link>`` tags.
    """

    def __init__(self, post, href, rel='alternate', type=None, hreflang=None,
                 title=None, length=None):
        if isinstance(post, (int, long)):
            self.post_id = post
        else:
            self.post = post
        self.href = href
        self.rel = rel
        self.type = type
        self.hreflang = hreflang
        self.title = title
        self.length = length

    def as_dict(self):
        """Return the values as dict.  Useful for feed building."""
        result = {'href': href}
        for key in 'rel', 'type', 'hreflang', 'title', 'length':
            value = getattr(self, key, None)
            if value is not None:
                result[key] = value
        return result

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.href
        )


class TagManager(db.DatabaseManager):
    """Also tags have their own manager."""

    def get_or_create(self, slug, name=None):
        """Get the tag for this slug or create it if it does not exist."""
        tag = self.filter_by(slug=slug).first()
        if tag is None:
            if name is None:
                name = slug
            tag = Tag(name, slug=slug)
        return tag

    def get_cloud(self, max=None, ignore_role=False):
        """Get a tagcloud."""
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
        } for row in db.execute(q)]

        items.sort(key=lambda x: x['name'].lower())
        return items


class Tag(object):
    """Represents a tag."""

    objects = TagManager()

    def __init__(self, name, description='', slug=None):
        self.name = name
        if slug is None:
            self.auto_slug()
        else:
            self.slug = slug
        self.description = description

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


class CommentManager(db.DatabaseManager):
    """The manager for comments"""

    def blocked(self, query=None):
        """Filter all blocked comments.  Blocked comments are all comments but
        unmoderated and moderated comments.
        """
        if query is None:
            query = self.query
        return query.filter(Comment.status.in_([COMMENT_BLOCKED_USER,
                                                COMMENT_BLOCKED_SPAM,
                                                COMMENT_BLOCKED_SYSTEM]))

    def unmoderated(self, query=None):
        """Filter all the unmoderated comments and comments blocked by a user
        or system.
        """
        if query is None:
            query = self.query
        return query.filter(Comment.status.in_([COMMENT_UNMODERATED,
                                                COMMENT_BLOCKED_USER,
                                                COMMENT_BLOCKED_SYSTEM]))

    def spam(self, query=None):
        """Filter all the spam comments."""
        if query is None:
            query = self.query
        return query.filter(Comment.status == COMMENT_BLOCKED_SPAM)

    def latest(self, limit=None, ignore_role=False, ignore_blocked=True):
        """Filter the list of non blocked comments for anonymous users or
        all comments for admin users.
        """
        role = ROLE_NOBODY
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role

        query = self.query
        if role <= ROLE_SUBSCRIBER or ignore_blocked:
            query = self.blocked(query)

        if limit is not None:
            query = query[:limit]
        return query

    def unmoderated(self):
        """Return all drafts."""
        return self.query.filter(Comment.status > COMMENT_MODERATED)


class Comment(object):
    """Represent one comment."""

    objects = CommentManager()

    def __init__(self, post, author, email, www, body, parent=None,
                 pub_date=None, submitter_ip='0.0.0.0', parser=None,
                 is_pingback=False, status=COMMENT_MODERATED):
        if isinstance(post, (int, long)):
            self.post_id = post
        else:
            self.post = post
        self.author = author
        self.email = email
        self.www = www

        if parser is None:
            parser = get_application().cfg['comment_parser']
        self.parser_data = {'parser': parser}
        self.raw_body = body or ''
        if isinstance(parent, (int, long)):
            self.parent_id = parent
        else:
            self.parent = parent
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        self.blocked_msg = None
        self.submitter_ip = submitter_ip
        self.is_pingback = is_pingback
        self.status = status

    def make_visible_for_request(self, request=None):
        """Make the comment visible for the current request."""
        if request is None:
            request = get_request()
        comments = request.session.setdefault('visible_comments', set())
        comments.add(self.comment_id)

    def visible_for_user(self, user=None):
        """Check if the current user or the user given can see this comment"""
        if not self.blocked:
            return True
        if user is None:
            user = get_request().user
        elif isinstance(user, (int, long)):
            user = User.objects.get(user)
        return user.role >= ROLE_AUTHOR

    @property
    def visible(self):
        """Check the current session it can see the comment or check against the
        current user.  To display a comment for a request you can use the
        `make_visible_for_request` function.  This is useful to show a comment
        to a user that submited a comment which is not yet moderated.
        """
        request = get_request()
        comments = request.session.get('visible_comments', ())
        if self.comment_id in comments:
            return True
        return self.visible_for_user(request.user)

    @property
    def blocked(self):
        """This is true if the status is anything but moderated."""
        return self.status != COMMENT_MODERATED

    @property
    def is_spam(self):
        """This is true if the comment is currently flagges as spam."""
        return self.status == COMMENT_BLOCKED_SPAM

    @property
    def parser_missing(self):
        app = get_application()
        return self.parser not in app.parsers

    def _get_parser(self):
        return self.parser_data['parser']

    def _set_parser(self, value):
        self.parser_data['parser'] = value

    parser = property(_get_parser, _set_parser)
    del _get_parser, _set_parser

    def _get_raw_body(self):
        return self._raw_body

    def _set_raw_body(self, value):
        from textpress.parsers import parse
        from textpress.fragment import dump_tree
        tree = parse(value, self.parser, 'comment')
        self._raw_body = value
        self._body_cache = tree
        self.parser_data['body'] = dump_tree(tree)

    def _get_body(self):
        if not hasattr(self, '_body_cache'):
            from textpress.fragment import load_tree
            self._body_cache = load_tree(self.parser_data['body'])
        return self._body_cache

    def _set_body(self, value):
        from textpress.fragment import Fragment, dump_tree
        if not isinstance(value, Fragment):
            raise TypeError('fragment required, otherwise use raw_body')
        self._body_cache = value
        self.parser_data['body'] = dump_tree(value)

    raw_body = property(_get_raw_body, _set_raw_body)
    body = property(_get_body, _set_body)
    del _get_raw_body, _set_raw_body, _get_body, _set_body

    def get_url_values(self):
        endpoint, args = self.post.get_url_values()
        args['_anchor'] = 'comment-%d' % self.comment_id
        return endpoint, args

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


# connect the tables.
db.mapper(User, users, properties={
    '_display_name':    users.c.display_name,
    'posts':            db.dynamic_loader(Post, backref='author')
})
db.mapper(Tag, tags, properties={
    'posts':            db.dynamic_loader(Post, secondary=post_tags)
})
db.mapper(Comment, comments, properties={
    '_raw_body':    comments.c.body,
    'children':     db.relation(Comment,
        primaryjoin=comments.c.parent_id == comments.c.comment_id,
        order_by=[db.asc(comments.c.pub_date)],
        backref=db.backref('parent', remote_side=[comments.c.comment_id],
                           primaryjoin=comments.c.parent_id == comments.c.comment_id),
        lazy=True
    )
}, order_by=comments.c.pub_date.desc())
db.mapper(PostLink, post_links)
db.mapper(Post, posts, properties={
    '_raw_body':    posts.c.body,
    '_raw_intro':   posts.c.intro,
    'comments':     db.relation(Comment, backref='post',
                                primaryjoin=posts.c.post_id == comments.c.post_id,
                                order_by=[db.asc(comments.c.pub_date)]),
    'links':        db.relation(PostLink, backref='post'),
    'tags':         db.relation(Tag, secondary=post_tags, lazy=False,
                                order_by=[db.asc(tags.c.name)])
}, order_by=posts.c.pub_date.desc())
