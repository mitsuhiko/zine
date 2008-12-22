# -*- coding: utf-8 -*-
"""
    zine.importers
    ~~~~~~~~~~~~~~

    Package for all kinds of importers.  This implements the basic import
    API as well as some core importers we implement as part of the software
    and not as plugin.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import os
try:
    from hashlib import md5
except ImportError:
    from md5 import md5
from time import time
from pickle import dump, load, HIGHEST_PROTOCOL
from datetime import datetime, MAXYEAR
from zine.i18n import _
from zine.database import db, posts
from zine.utils.xml import escape
from zine.models import COMMENT_MODERATED
from zine.privileges import BLOG_ADMIN, ENTER_ADMIN_PANEL, require_privilege


ignored_config_keys = frozenset(['database_uri'])

_distant_future = datetime(MAXYEAR, 12, 31)


def _make_id(*args):
    hash = md5()
    for arg in args:
        if isinstance(arg, unicode):
            arg = arg.encode('utf-8')
        hash.update('|' + str(arg))
    return hash.hexdigest()


def list_import_queue(app):
    """Return a list of all items in the import queue."""
    path = os.path.join(app.instance_folder, 'import_queue')
    if not os.path.isdir(path):
        return []
    result = []
    for id in os.listdir(path):
        if not id.isdigit():
            continue
        filename = os.path.join(path, id)
        f = file(filename)
        try:
            d = load(f)
        finally:
            f.close()
        d.update(
            size=os.path.getsize(filename),
            id=int(id)
        )
        result.append(d)
    result.sort(key=lambda x: x['id'])
    return result


def load_import_dump(app, id):
    """Load an import dump."""
    path = os.path.join(app.instance_folder, 'import_queue', str(id))
    if not os.path.isfile(path):
        return
    f = file(path, 'rb')
    try:
        load(f)
        blog = load(f)
    finally:
        f.close()
    if isinstance(blog, Blog):
        return blog


def delete_import_dump(app, id):
    """Delete an import dump."""
    path = os.path.join(app.instance_folder, 'import_queue', str(id))
    if os.path.isfile(path):
        os.remove(path)


def _perform_import(app, blog, d):
    # import models here because they have the same names as our
    # importer objects this module exports
    from zine.models import User, Tag, Category, Post, Comment
    author_mapping = {}
    tag_mapping = {}
    category_mapping = {}

    def prepare_author(author):
        """Adds an author to the author mapping and returns it."""
        if author.id not in author_mapping:
            author_rewrite = d['authors'][author.id]
            if author_rewrite is not None:
                user = User.query.get(int(author_rewrite))
            else:
                user = User(author.username, None, author.email,
                            author.real_name, author.description,
                            author.www, author.is_author)
                if author.pw_hash:
                    user.pw_hash = author.pw_hash
                user.privileges.update(author.privileges)
            author_mapping[author.id] = user
        return author_mapping[author.id]

    def prepare_tag(tag):
        """Get a tag for a tag."""
        t = tag_mapping.get(tag.slug)
        if t is not None:
            return t
        t = Tag.query.filter_by(slug=tag.slug).first()
        if t is not None:
            tag_mapping[tag.slug] = t
            return t
        t = Tag.query.filter_by(name=tag.name).first()
        if t is not None:
            tag_mapping[tag.slug] = t
            return t
        t = tag_mapping[tag.id] = Tag(tag.name, tag.slug)
        return t

    def prepare_category(category):
        """Get a category for a category."""
        c = category_mapping.get(category.slug)
        if c is not None:
            return c
        c = Category.query.filter_by(slug=category.slug).first()
        if c is not None:
            category_mapping[category.slug] = c
            return c
        c = Category.query.filter_by(name=category.name).first()
        if c is not None:
            category_mapping[category.slug] = c
            return c
        c = category_mapping[category.id] = Category(category.name,
                                                     category.description,
                                                     category.slug)
        return c

    # start debug output
    yield u'<ul>'

    # update blog configuration if user wants that
    if d['title']:
        app.cfg.change_single('blog_title', blog.title)
        yield u'<li>%s</li>\n' % _('set blog title from dump')
    if d['description']:
        app.cfg.change_single('blog_tagline', blog.description)
        yield u'<li>%s</li>\n' % _('set blog tagline from dump')

    # convert the posts now
    for old_post in blog.posts:
        # in theory that will never happen because there are no
        # checkboxes for already imported posts on the form, but
        # who knows what users manage to do and also skip posts
        # we don't want converted
        if old_post.already_imported or not d['posts'][old_post.id]:
            continue

        post = Post(old_post.title, prepare_author(old_post.author),
                    old_post.text, old_post.slug, old_post.pub_date,
                    old_post.updated, old_post.comments_enabled,
                    old_post.pings_enabled, parser=old_post.parser,
                    uid=old_post.uid)
        if old_post.parser_data is not None:
            post.parser_data = old_post.parser_data
        yield u'<li><strong>%s</strong>' % escape(post.title)

        for tag in old_post.tags:
            post.tags.append(prepare_tag(tag))
            yield u'.'

        for category in old_post.categories:
            post.categories.append(prepare_category(category))
            yield u'.'

        # now the comments if user wants them.
        if d['comments'][old_post.id]:
            to_create = set(old_post.comments)
            created = {}

            def _create_comment(comment):
                parent = None
                if comment.parent is not None:
                    if comment.parent in created:
                        parent = created[comment.parent]
                    else:
                        parent = _create_comment(comment.parent)
                    to_create.discard(comment.parent)
                rv = Comment(post, comment.author, comment.body,
                             comment.author_email, comment.author_url, parent,
                             comment.pub_date, comment.remote_addr,
                             comment.parser, comment.is_pingback,
                             comment.status)
                if comment.blocked_msg:
                    rv.blocked_msg = comment.blocked_msg
                created[comment] = rv
                return rv

            while to_create:
                _create_comment(to_create.pop())
                yield u'.'

        yield u' <em>%s</em></li>\n' % _('done')

    # send to the database
    yield u'<li>%s' % _('Committing transaction...')
    db.commit()

    # write config if we have
    if d['load_config']:
        yield u'<li>%s' % _('Updating configuration...')
        t = app.cfg.edit()
        for key, value in blog.config.iteritems():
            if key in t and key not in ignored_config_keys:
                t.set_from_string(key, value)
        t.commit()

    yield u' <em>%s</em></li></ul>' % _('done')


def perform_import(app, blog, data, stream=False):
    """Perform an import from form data.  This function was designed to be
    called from a web request, if you call it form outside, make sure the
    config is flushed afterwards.
    """
    generator = _perform_import(app, blog, data)

    # ignore the debug output, just do the import
    if not stream:
        for item in generator:
            pass
    else:
        return generator


def rewrite_import(app, id, callback, title='Modified Import'):
    """Calls a callback with the blog from the dump `id` for rewriting.  The
    callback can modify the blog in place (it's passed as first argument) and
    the changes are written back to the filesystem as new dump.

    `app` can either be a `Zine` object that is also bound to the active
    thread or a string with the path to the instance folder.  The latter is
    useful for simple scripts that should rewrite imports.
    """
    close = False
    if isinstance(app, basestring):
        from zine import make_zine
        app = make_zine(app, bind_to_thread=True)
        close = True

    blog = load_import_dump(app, id)
    callback(blog)
    f = file(os.path.join(app.instance_folder, 'import_queue',
                          '%d' % time()), 'wb')
    try:
        blog.dump(f, title)
    finally:
        f.close()

    if close:
        app.close()


class Importer(object):

    #: the shortname of the importer.  This is used for the URLs
    #: and internal addressing.
    name = None

    @property
    def title(self):
        return self.name.title()

    def get_url_values(self):
        return 'import/' + self.name, {}

    def render_admin_page(self, template_name, **context):
        """Shortcut for rendering an page for the admin."""
        from zine.views.admin import render_admin_response
        return render_admin_response(template_name, 'system.import',
                                     **context)

    def enqueue_dump(self, blog):
        """Enqueue a `Blog` object into the dump space."""
        path = os.path.join(self.app.instance_folder, 'import_queue')
        try:
            os.makedirs(path)
        except OSError:
            pass
        f = file(os.path.join(path, '%d' % time()), 'wb')
        try:
            blog.dump(f, self.title)
        finally:
            f.close()

    def __init__(self, app):
        self.app = app

    def __call__(self, request):
        return require_privilege(BLOG_ADMIN)(self.configure)(request)

    def configure(self, request):
        """Subclasses should override this and implement the admin panel
        that ask for details and imports to the queue.
        """


class _Element(object):
    element = None

    def __getstate__(self):
        self.__dict__.pop('element', None)
        return self.__dict__


class Blog(_Element):
    """Represents a blog."""

    def __init__(self, title, link, description, language='en', tags=None,
                 categories=None, posts=None, authors=None,
                 configuration=None):
        self.dump_date = datetime.utcnow()
        self.title = title
        self.link = link
        self.description = description
        self.language = language
        if tags:
            tags.sort(key=lambda x: x.name.lower())
        self.tags = tags or []
        if categories:
            categories.sort(key=lambda x: x.name.lower())
        self.categories = categories or []
        if posts:
            posts.sort(key=lambda x: x.pub_date or _distant_future, reverse=True)
        self.posts = posts or []
        if authors:
            authors.sort(key=lambda x: x.username.lower())
        self.authors = authors or []
        if configuration is None:
            configuration = {}
        self.configuration = configuration

    def __getstate__(self):
        for post in self.posts:
            post.__dict__.pop('already_imported', None)
        return _Element.__getstate__(self)

    def __setstate__(self, d):
        self.__dict__ = d
        uids = set(x.uid for x in db.execute(db.select([posts.c.uid])))
        for post in self.posts:
            post.already_imported = post.uid in uids

    def dump(self, f, importer_name=None):
        """Dump the blog into a file descriptor."""
        dump({
            'importer':     importer_name,
            'source':       self.link,
            'title':        self.title,
            'dump_date':    self.dump_date
        }, f, HIGHEST_PROTOCOL)
        dump(self, f, HIGHEST_PROTOCOL)

    def __repr__(self):
        return '<%s %r posts: %d, authors: %d>' % (
            self.__class__.__name__,
            self.title,
            len(self.posts),
            len(self.authors)
        )


class Author(_Element):
    """Represents an author."""

    def __init__(self, username, email, real_name=u'', description=u'',
                 pw_hash=None, is_author=True, extra=None, id=None):
        if id is None:
            id = _make_id(username, email)
        self.id = id
        self.username = username
        self.real_name = real_name or u''
        self.email = email or u''
        self.description = description or u''
        self.privileges = set([ENTER_ADMIN_PANEL])
        self.is_author = is_author
        self.pw_hash = pw_hash
        self.extra = extra or {}

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.username
        )


class Tag(_Element):
    """Represents a tag."""

    def __init__(self, slug, name=None):
        self.slug = slug
        if name is None:
            name = slug
        self.name = name

    @property
    def id(self):
        return _make_id(self.slug)

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class Category(Tag):
    """Represents a category."""
    element = None

    def __init__(self, slug, name=None, description=u''):
        Tag.__init__(self, slug, name)
        self.description = description


class Post(_Element):
    """Represents a blog post."""

    def __init__(self, slug, title, link, pub_date, author, intro, body,
                 tags=None, categories=None, comments=None,
                 comments_enabled=True, pings_enabled=True, updated=None,
                 uid=None, parser=None, parser_data=None):
        self.slug = slug
        self.title = title
        self.link = link
        self.pub_date = pub_date
        self.author = author
        self.intro = intro
        self.body = body
        self.tags = tags or []
        self.categories = categories or []
        self.comments = comments or []
        self.comments_enabled = comments_enabled
        self.pings_enabled = pings_enabled
        self.updated = updated or self.pub_date
        self.uid = uid or self.link
        self.parser = parser or 'html'
        self.parser_data = parser_data

    @property
    def text(self):
        result = self.body
        if self.intro:
            result = u'<intro>%s</intro>%s' % (self.intro, result)
        return result

    @property
    def id(self):
        return _make_id(self.uid)

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.title
        )


class Comment(_Element):
    """Represents a comment on a post."""

    def __init__(self, author, body, author_email, author_url, parent,
                 pub_date, remote_addr, parser=None, is_pingback=False,
                 status=COMMENT_MODERATED, blocked_msg=u'',
                 parser_data=None):
        self.author = author
        self.author_email = author_email
        self.author_url = author_url
        self.parent = parent
        self.remote_addr = remote_addr
        self.pub_date = pub_date
        self.body = body
        self.parser = parser or 'html'
        self.is_pingback = is_pingback
        self.status = status
        self.blocked_msg = blocked_msg
        self.parser_data = parser_data

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


from zine.importers.wordpress import WordPressImporter
from zine.importers.blogger import BloggerImporter
from zine.importers.feed import FeedImporter
importers = [WordPressImporter, BloggerImporter, FeedImporter]
