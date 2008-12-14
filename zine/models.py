# -*- coding: utf-8 -*-
"""
    zine.models
    ~~~~~~~~~~~

    The core models and query helper functions.

    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Christopher Grebs,
                             Ali Afshar.
    :license: GNU GPL.
"""
from math import ceil, log
from datetime import date, datetime, timedelta
from urlparse import urljoin

from werkzeug.exceptions import NotFound

from zine.database import users, categories, posts, post_links, \
     post_categories, post_tags, tags, comments, db
from zine.utils import build_tag_uri, zeml
from zine.utils.admin import gen_slug
from zine.utils.pagination import Pagination
from zine.utils.crypto import gen_pwhash, check_pwhash
from zine.utils.http import make_external_url
from zine.application import get_application, get_request, url_for


#: user rules
ROLE_ADMIN = 4
ROLE_EDITOR = 3
ROLE_AUTHOR = 2
ROLE_SUBSCRIBER = 1
ROLE_NOBODY = 0

#: all kind of states for a post
STATUS_DRAFT = 1
STATUS_PUBLISHED = 2

#: Comment Status
COMMENT_MODERATED = 0
COMMENT_UNMODERATED = 1
COMMENT_BLOCKED_USER = 2
COMMENT_BLOCKED_SPAM = 3
COMMENT_BLOCKED_SYSTEM = 4

#: moderation modes
MODERATE_NONE = 0
MODERATE_ALL = 1
MODERATE_UNKNOWN = 2


class _ZEMLContainer(object):
    """A mixin for objects that have ZEML markup stored."""

    parser_reason = None

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
        if self.parser_data is not None:
            return self.parser_data.get('parser')

    def _set_parser(self, value):
        if self.parser_data is None:
            self.parser_data = {}
        self.parser_data['parser'] = value

    parser = property(_get_parser, _set_parser, doc="The name of the parser.")
    del _get_parser, _set_parser

    @property
    def body(self):
        """The body as ZEML element."""
        if self.parser_data is not None:
            return self.parser_data.get('body')

    def _parse_text(self, text):
        from zine.parsers import parse
        self.parser_data['body'] = parse(text, self.parser, 'post')

    def _get_text(self):
        return self._text

    def _set_text(self, value):
        if self.parser_data is None:
            self.parser_data = {}
        self._text = value
        self._parse_text(value)

    text = property(_get_text, _set_text, doc="The raw text.")
    del _get_text, _set_text

    def find_urls(self):
        """Iterate over all urls in the text.  This will only work if the
        parser for this post is available.  If it's not the behavior is
        undefined.  The urls returned are absolute urls.
        """
        from zine.parsers import parse
        found = set()
        this_url = url_for(self, _external=True)
        tree = parse(self.text, self.parser, 'linksearch')
        for node in tree.query('a[href]'):
            href = urljoin(this_url, node.attributes['href'])
            if href not in found:
                found.add(href)
                yield href


class _ZEMLDualContainer(_ZEMLContainer):
    """Like the ZEML mixin but with intro and body sections."""

    def _parse_text(self, text):
        from zine.parsers import parse
        self.parser_data['intro'], self.parser_data['body'] = \
            zeml.split_intro(parse(text, self.parser, self.parser_reason))

    @property
    def intro(self):
        """The intro as zeml element."""
        if self.parser_data is not None:
            return self.parser_data.get('intro')


class UserQuery(db.Query):
    """Add some extra query methods to the user object."""

    def get_nobody(self):
        return AnonymousUser()

    def authors(self):
        return self.filter(User.role >= ROLE_AUTHOR)


class User(object):
    """Represents an user.

    If you change something on this model, even default values, keep in mind
    that the websetup does not use this model to create the admin account
    because at that time the Zine system is not yet ready. Also update
    the code in `zine.websetup.WebSetup.start_setup`.
    """

    query = db.query_property(UserQuery)
    is_somebody = True

    def __init__(self, username, password, email, real_name=u'',
                 description=u'', www=u'', role=ROLE_SUBSCRIBER):
        self.username = username
        if password is not None:
            self.set_password(password)
        else:
            self.disable()
        self.email = email
        self.www = www
        self.real_name = real_name
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
        from zine.api import _
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
            username=self.username,
            real_name=self.real_name
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
        return self.www or '#'

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.username
        )


class AnonymousUser(User):
    """Fake model for anonymous users."""
    is_somebody = False
    display_name = 'Nobody'
    real_name = description = username = ''
    role = ROLE_NOBODY

    def __init__(self):
        pass

    def __nonzero__(self):
        return False

    def check_password(self, password):
        return False


class PostQuery(db.Query):
    """Add some extra methods to the post model."""

    def type(self, content_type):
        """Filter all posts by a given type."""
        return self.filter_by(content_type=content_type)

    def for_index(self):
        """Return all the types for the index."""
        types = get_application().cfg['index_content_types'].split(',')
        if len(types) == 1:
            return self.filter_by(content_type=types[0].strip())
        return self.filter(Post.content_type.in_([x.strip() for x in types]))

    def published(self, ignore_role=None):
        """Return a queryset for only published posts."""
        role = ROLE_NOBODY
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role
        p = posts.c

        query = self.filter(p.status == STATUS_PUBLISHED)
        if role <= ROLE_SUBSCRIBER:
            return query.filter(p.pub_date <= datetime.utcnow())
        elif role == ROLE_AUTHOR:
            # it's safe to access req here because we only have
            # a non ROLE_NOBODY role if there was a request.
            return query.filter(
                (p.pub_date <= datetime.utcnow()) |
                (p.author == req.user)
            )
        return query

    def drafts(self, ignore_user=False, user=None):
        """Return a query that returns all drafts for the current user.
        or the user provided or no user at all if `ignore_user` is set.
        """
        if user is None and not ignore_user:
            req = get_request()
            if req and req.user:
                user = req.user
        query = self.filter(Post.status == STATUS_DRAFT)
        if user is not None:
            query = query.filter(Post.author_id == user.id)
        return query

    def get_list(self, endpoint=None, page=1, per_page=None,
                 url_args=None, raise_if_empty=True):
        """Return a dict with pagination, the current posts, number of pages,
        total posts and all that stuff for further processing.
        """
        if per_page is None:
            app = get_application()
            per_page = app.cfg['posts_per_page']

        # send the query
        offset = per_page * (page - 1)
        postlist = self.order_by(Post.pub_date.desc()) \
                       .offset(offset).limit(per_page).all()

        # if raising exceptions is wanted, raise it
        if raise_if_empty and (page != 1 and not postlist):
            raise NotFound()

        pagination = Pagination(endpoint, page, per_page,
                                self.count(), url_args)

        return {
            'pagination':       pagination,
            'posts':            postlist
        }

    def get_archive_summary(self, detail='months', limit=None,
                            ignore_role=False):
        """Query function to get the archive of the blog. Usually used
        directly from the templates to add some links to the sidebar.
        """
        # XXX: currently we also return months without articles in it.
        # other blog systems do not, but because we use sqlalchemy we have
        # to go with the functionality provided.  Currently there is no way
        # to do date truncating in a database agnostic way.
        last = self.filter(Post.pub_date != None) \
                   .order_by(Post.pub_date.asc()).first()
        now = datetime.utcnow()

        there_are_more = False
        result = []

        if last is not None:
            now = date(now.year, now.month, now.day)
            oldest = date(last.pub_date.year, last.pub_date.month,
                          last.pub_date.day)
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
            query = query.limit(limit)
        return query

    def date_filter(self, year, month=None, day=None):
        """Filter all the items that match the given date."""
        if month is None:
            return self.filter(
                (Post.pub_date >= datetime(year, 1, 1)) &
                (Post.pub_date < datetime(year + 1, 1, 1))
            )
        elif day is None:
            return self.filter(
                (Post.pub_date >= datetime(year, month, 1)) &
                (Post.pub_date < (month == 12 and
                               datetime(year + 1, 1, 1) or
                               datetime(year, month + 1, 1)))
            )
        return self.filter(
            (Post.pub_date >= datetime(year, month, day)) &
            (Post.pub_date < datetime(year, month, day) +
                             timedelta(days=1))
        )

    def search(self, query):
        """Search for posts by a query."""
        # XXX: use a sophisticated search
        q = self
        for word in query.split():
            q = q.filter(
                posts.c.body.like('%%%s%%' % word) |
                posts.c.intro.like('%%%s%%' % word) |
                posts.c.title.like('%%%s%%' % word)
            )
        return q.all()


class Post(_ZEMLDualContainer):
    """Represents one blog post."""

    query = db.query_property(PostQuery)
    parser_reason = 'post'

    def __init__(self, title, author, text, slug=None, pub_date=None,
                 last_update=None, comments_enabled=True,
                 pings_enabled=True, status=STATUS_PUBLISHED,
                 parser=None, uid=None, content_type='entry'):
        app = get_application()
        self.title = title
        self.author = author
        if parser is None:
            parser = app.cfg['default_parser']

        self.parser = parser
        self.text = text or u''
        self.extra = {}

        if pub_date is None and status == STATUS_PUBLISHED:
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
            self.set_auto_slug()
        else:
            self.slug = slug

        # generate a UID if none is given
        if uid is None:
            uid = build_tag_uri(app, self.pub_date, content_type, self.slug)
        self.uid = uid

        self.content_type = content_type

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
        return make_external_url(self.slug.rstrip('/') + '/feed.atom')

    @property
    def is_draft(self):
        """True if this post is unpublished."""
        return self.status == STATUS_DRAFT

    def set_auto_slug(self):
        """Generate a slug for this post."""
        slug = gen_slug(self.title)
        if not slug:
            slug = self.pub_date.strftime('%H:%M')
        self.slug = u'%s/%s/%s/%s' % (
            self.pub_date.year,
            self.pub_date.month,
            self.pub_date.day,
            slug
        )

    def bind_tags(self, tags):
        """Rebinds the tags to a list of tags (strings, not tag objects)."""
        current_map = dict((x.name, x) for x in self.tags)
        currently_attached = set(x.name for x in self.tags)
        new_tags = set(tags)

        # delete outdated tags
        for name in currently_attached.difference(new_tags):
            self.tags.remove(current_map[name])

        # add new tags
        for name in new_tags.difference(currently_attached):
            self.tags.append(Tag.get_or_create(name))

    def bind_categories(self, categories):
        """Rebinds the categories to the list passed.  The list of objects
        must be a list of category objects.
        """
        currently_attached = set(self.categories)
        new_categories = set(categories)

        # delete outdated categories
        for category in currently_attached.difference(new_categories):
            self.categories.remove(category)

        # attach new categories
        for category in new_categories.difference(currently_attached):
            self.categories.append(category)

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

        # simple rule: admins and editors may always
        if user.role in (ROLE_ADMIN, ROLE_EDITOR):
            return True
        # subscribers and anonymous users may never
        elif user.role in (ROLE_SUBSCRIBER, ROLE_NOBODY):
            return False
        # authors here, they can only view it if they are the
        # author of this post.
        else:
            return self.author_id == user.id

    @property
    def is_published(self):
        """`True` if the post is visible for everyone."""
        return self.can_access(AnonymousUser())

    @property
    def is_sheduled(self):
        """True if the item is sheduled for appearing."""
        return self.status == STATUS_PUBLISHED and \
               self.pub_date > datetime.utcnow()

    def get_url_values(self):
        return self.slug

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.title
        )


class PostLink(object):
    """Represents a link in a post.  This can be used for podcasts or other
    resources that require ``<link>`` categories.
    """

    def __init__(self, post, href, rel='alternate', type=None, hreflang=None,
                 title=None, length=None):
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


class CategoryQuery(db.Query):
    """Also categories have their own manager."""

    def get_or_create(self, slug, name=None):
        """Get the category for this slug or create it if it does not exist."""
        category = self.filter_by(slug=slug).first()
        if category is None:
            if name is None:
                name = slug
            category = Category(name, slug=slug)
        return category

    def get_cloud(self, max=None, ignore_role=False):
        """Get a categorycloud."""
        role = ROLE_NOBODY
        if ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role

        # get a query
        p = post_categories.c
        p2 = posts.c
        t = categories.c

        q = (p.category_id == t.category_id) & (p.post_id == p2.post_id)

        # do the role checking
        if role <= ROLE_SUBSCRIBER:
            q &= ((p2.status == STATUS_PUBLISHED) |
                  (p2.pub_date >= datetime.utcnow()))

        elif role == ROLE_AUTHOR:
            # it's safe to access req here because we only have
            # a non ROLE_NOBODY role if there was a request.
            q &= ((p2.status == STATUS_PUBLISHED) |
                  (p2.author_id == req.user.id))

        s = db.select([t.slug, t.name, db.func.count(p.post_id).label('s_count')],
                      p.category_id == t.category_id,
                      group_by=[t.slug, t.name]).alias('post_count_query').c

        options = {'order_by': [db.asc(s.s_count)]}
        if max is not None:
            options['limit'] = max

        # the label statement circumvents a bug for sqlite3 on windows
        # see #65
        q = db.select([s.slug, s.name, s.s_count.label('s_count')], **options)

        items = [{
            'slug':     row.slug,
            'name':     row.name,
            'count':    row.s_count,
            'size':     100 + log(row.s_count or 1) * 20
        } for row in db.execute(q)]

        items.sort(key=lambda x: x['name'].lower())
        return items


class Category(object):
    """Represents a category."""

    query = db.query_property(CategoryQuery)

    def __init__(self, name, description='', slug=None):
        self.name = name
        if slug is None:
            self.set_auto_slug()
        else:
            self.slug = slug
        self.description = description

    def set_auto_slug(self):
        """Generate a slug for this category."""
        self.slug = gen_slug(self.name)

    def get_url_values(self):
        return 'blog/show_category', {
            'slug':     self.slug
        }

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class CommentQuery(db.Query):
    """The manager for comments"""

    def blocked(self):
        """Filter all blocked comments.  Blocked comments are all comments but
        unmoderated and moderated comments.
        """
        return self.filter(Comment.status.in_([COMMENT_BLOCKED_USER,
                                               COMMENT_BLOCKED_SPAM,
                                               COMMENT_BLOCKED_SYSTEM]))
    def unmoderated(self):
        """Filter all the unmoderated comments and comments blocked by a user
        or system.
        """
        return self.filter(Comment.status.in_([COMMENT_UNMODERATED,
                                               COMMENT_BLOCKED_USER,
                                               COMMENT_BLOCKED_SYSTEM]))

    def spam(self):
        """Filter all the spam comments."""
        return self.filter(Comment.status == COMMENT_BLOCKED_SPAM)

    def latest(self, limit=None, ignore_role=False, ignore_blocked=True):
        """Filter the list of non blocked comments for anonymous users or
        all comments for admin users.
        """
        role = ROLE_NOBODY
        if not ignore_role:
            req = get_request()
            if req is not None:
                role = req.user.role

        query = self
        if role <= ROLE_SUBSCRIBER or ignore_blocked:
            query = self.blocked(query)

        if limit is not None:
            query = query.limit(limit)
        return query

    def comments_for_post(self, post):
        """Return all comments for the blog post."""
        return self.filter(Comment.post_id == post.id)


class Comment(_ZEMLContainer):
    """Represent one comment."""

    query = db.query_property(CommentQuery)
    parser_reason = 'comment'

    def __init__(self, post, author, text, email=None, www=None, parent=None,
                 pub_date=None, submitter_ip='0.0.0.0', parser=None,
                 is_pingback=False, status=COMMENT_MODERATED):
        self.post = post
        if isinstance(author, basestring):
            self.user = None
            self._author = author
            self._email = email
            self._www = www
        else:
            assert email is www is None, \
                'email and www can only be provided if the author is ' \
                'an anonmous user'
            self.user = author

        if parser is None:
            parser = get_application().cfg['comment_parser']
        self.parser = parser
        self.text = text or ''
        self.parent = parent
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        self.blocked_msg = None
        self.submitter_ip = submitter_ip
        self.is_pingback = is_pingback
        self.status = status

    def _union_property(attribute, user_attribute=None):
        """An attribute that can exist on a user and the comment."""
        user_attribute = user_attribute or attribute
        attribute = '_' + attribute
        def get(self):
            if self.user:
                return getattr(self.user, user_attribute)
            return getattr(self, attribute)
        def set(self, value):
            if self.user:
                raise TypeError('can\'t set this attribute if the comment '
                                'does not belong to an anonymous user')
            setattr(self, attribute, value)
        return property(get, set)

    email = _union_property('email')
    www = _union_property('www')
    author = _union_property('author', 'display_name')
    del _union_property

    @property
    def anonymous(self):
        """True if this comment is an anonymous comment."""
        return self.user is None

    @property
    def requires_moderation(self):
        """This is `True` if the comment requires moderation with the
        current moderation settings.  This does not check if the comment
        is already moderated.
        """
        if not self.anonymous:
            return False
        moderate = get_application().cfg['moderate_comments']
        if moderate == MODERATE_ALL:
            return True
        elif moderate == MODERATE_NONE:
            return False
        return db.execute(comments.select(
            (comments.c.author == self._author) &
            (comments.c.email == self._email) &
            (comments.c.status == COMMENT_MODERATED)
        )).fetchone() is None

    def make_visible_for_request(self, request=None):
        """Make the comment visible for the current request."""
        if request is None:
            request = get_request()
        comments = set(request.session.get('visible_comments', ()))
        comments.add(self.id)
        request.session['visible_comments'] = tuple(comments)

    def visible_for_user(self, user=None):
        """Check if the current user or the user given can see this comment"""
        if not self.blocked:
            return True
        if user is None:
            user = get_request().user
        return user.role >= ROLE_AUTHOR

    @property
    def visible(self):
        """Check the current session it can see the comment or check against the
        current user.  To display a comment for a request you can use the
        `make_visible_for_request` function.  This is useful to show a comment
        to a user that submited a comment which is not yet moderated.
        """
        request = get_request()
        print request.session
        if self.id in request.session.get('visible_comments', ()):
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
    def is_unmoderated(self):
        """True if the comment is not yet approved."""
        return self.status == COMMENT_UNMODERATED

    def get_url_values(self):
        return url_for(self.post) + '#comment-%d' % self.id

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


class Tag(object):
    """A single tag."""
    query = db.query_property(db.Query)

    def __init__(self, name, slug=None):
        self.name = name
        if slug is None:
            self.set_auto_slug()
        else:
            self.slug = slug

    @staticmethod
    def get_or_create(name):
        tag = Tag.query.filter_by(name=name).first()
        if tag is not None:
            return tag
        return Tag(name)

    def set_auto_slug(self):
        self.slug = gen_slug(self.name)

    def get_url_values(self):
        return 'blog/show_tag', {'slug': self.slug}

    def __repr__(self):
        return u'<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


# connect the tables.
db.mapper(User, users, properties={
    'id':               users.c.user_id,
    'display_name':     db.synonym('_display_name', map_column=True),
    'posts':            db.dynamic_loader(Post, backref='author',
                                          cascade='all, delete, delete-orphan'),
    'comments':         db.dynamic_loader(Comment, backref='user',
                                          cascade='all, delete, delete-orphan')
})
db.mapper(Category, categories, properties={
    'id':               categories.c.category_id,
    'posts':            db.dynamic_loader(Post, secondary=post_categories)
})
db.mapper(Comment, comments, properties={
    'id':           comments.c.comment_id,
    'text':         db.synonym('_text', map_column=True),
    'author':       db.synonym('_author', map_column=True),
    'email':        db.synonym('_email', map_column=True),
    'www':          db.synonym('_www', map_column=True),
    'children':     db.relation(Comment,
        primaryjoin=comments.c.parent_id == comments.c.comment_id,
        order_by=[db.asc(comments.c.pub_date)],
        backref=db.backref('parent', remote_side=[comments.c.comment_id],
                           primaryjoin=comments.c.parent_id == comments.c.comment_id),
        lazy=True
    )
}, order_by=comments.c.pub_date.desc())
db.mapper(PostLink, post_links, properties={
    'id':           post_links.c.link_id,
})
db.mapper(Tag, tags, properties={
    'id':           tags.c.tag_id,
})
db.mapper(Post, posts, properties={
    'id':               posts.c.post_id,
    'text':             db.synonym('_text', map_column=True),
    'comments':         db.relation(Comment, backref='post',
                                    primaryjoin=posts.c.post_id ==
                                        comments.c.post_id,
                                    order_by=[db.asc(comments.c.pub_date)],
                                    lazy=False,
                                    cascade='all, delete, delete-orphan'),
    'links':            db.relation(PostLink, backref='post',
                                    cascade='all, delete, delete-orphan'),
    'categories':       db.relation(Category, secondary=post_categories, lazy=False,
                                    order_by=[db.asc(categories.c.name)]),
    'tags':             db.relation(Tag, secondary=post_tags, lazy=False,
                                    order_by=[tags.c.name])
}, order_by=posts.c.pub_date.desc())
