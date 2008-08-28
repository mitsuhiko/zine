# -*- coding: utf-8 -*-
"""
    zine.importers
    ~~~~~~~~~~~~~~

    Package for all kinds of importers.  This implements the basic import
    API as well as some core importers we implement as part of the software
    and not as plugin.

    :copyright: Copyright 2008 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
import os
import md5
from time import time
from pickle import dump, load, HIGHEST_PROTOCOL
from datetime import datetime
from zine.api import _, require_role
from zine.database import db, posts
from zine.utils.xml import escape, get_etree
from zine.models import ROLE_ADMIN, ROLE_AUTHOR, COMMENT_MODERATED


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
    from zine.models import User, Tag, Post, Comment
    author_mapping = {}
    label_mapping = {}

    def prepare_author(author):
        """Adds an author to the author mapping and returns it."""
        if author.id not in author_mapping:
            author_rewrite = d.get('author_%s' % author.id)
            if author_rewrite:
                user = User.objects.get(int(author_rewrite))
            else:
                user = User(author.name, None, author.email, role=ROLE_AUTHOR)
            author_mapping[author.id] = user
        return author_mapping[author.id]

    def prepare_label(label):
        """Get a tag for a label."""
        tag = label_mapping.get(label.slug)
        if tag is not None:
            return tag
        tag = Tag.objects.filter_by(slug=label.slug).first()
        if tag is not None:
            label_mapping[label.slug] = tag
            return tag
        tag = Tag.objects.filter_by(name=label.name).first()
        if tag is not None:
            label_mapping[label.slug] = tag
            return tag
        tag = label_mapping[label.id] = Tag(label.name, '', label.slug)
        return tag

    # start debug output
    yield '<ul>'

    # update blog configuration if user wants that
    if 'import_blog_title' in d:
        app.cfg.change_single('blog_title', blog.title)
        yield '<li>%s</li>\n' % _('set blog title from dump')
    if 'import_blog_description' in d:
        app.cfg.change_single('blog_tagline', blog.description)
        yield '<li>%s</li>\n' % _('set blog tagline from dump')

    # convert the posts now
    for old_post in blog.posts:
        # in theory that will never happen because there are no
        # checkboxes for already imported posts on the form, but
        # who knows what users manage to do and also skip posts
        # we don't want converted
        if old_post.already_imported or not \
           'import_post_%s' % old_post.id in d:
            continue

        post = Post(old_post.title, prepare_author(old_post.author),
                    old_post.body, old_post.intro, old_post.slug,
                    old_post.pub_date, old_post.updated,
                    old_post.comments_enabled, old_post.pings_enabled,
                    parser=old_post.parser, uid=old_post.uid)
        yield '<li><strong>%s</strong>' % escape(post.title)
        for label in old_post.labels:
            post.tags.append(prepare_label(label))
            yield '.'

        # now the comments if use wants them.
        if 'import_comments_%s' % old_post.id in d:
            for comment in old_post.comments:
                Comment(post, comment.author, comment.body,
                        comment.author_email, comment.author_url, None,
                        comment.pub_date, comment.remote_addr,
                        comment.parser, comment.is_pingback,
                        comment.status)
                yield '.'
        yield u' <em>%s</em></li>\n' % _('done')

    # send to the database
    yield '<li>%s' % _('Committing transaction...')
    db.commit()
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
        return render_admin_response(template_name, 'maintenance.import',
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
        return require_role(ROLE_ADMIN)(self.configure)(request)

    def configure(self, request):
        """Subclasses should override this and implement the admin panel
        that ask for details and imports to the queue.
        """


class Blog(object):
    """Represents a blog."""

    def __init__(self, title, link, description, language='en', labels=None,
                 posts=None, authors=None):
        self.dump_date = datetime.utcnow()
        self.title = title
        self.link = link
        self.description = description
        self.language = language
        if labels:
            labels.sort(key=lambda x: x.name.lower())
        self.labels = labels or []
        if posts:
            posts.sort(key=lambda x: x.pub_date, reverse=True)
        self.posts = posts or []
        if authors:
            authors.sort(key=lambda x: x.name.lower())
        self.authors = authors or []

    def __getstate__(self):
        for post in self.posts:
            post.__dict__.pop('already_imported', None)
        return self.__dict__

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


class Author(object):
    """Represents an author."""

    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class Label(object):
    """Represents a category or tag."""

    def __init__(self, slug, name):
        self.slug = slug
        self.name = name

    @property
    def id(self):
        return md5.new(self.slug).hexdigest()

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class Post(object):
    """Represents a blog post."""

    def __init__(self, slug, title, link, pub_date, author, intro, body,
                 labels=None, comments=None, comments_enabled=True,
                 pings_enabled=True, updated=None, uid=None, parser=None):
        self.slug = slug
        self.title = title
        self.link = link
        self.pub_date = pub_date
        self.author = author
        self.intro = intro
        self.body = body
        self.labels = labels or []
        self.comments = comments or []
        self.comments_enabled = comments_enabled
        self.pings_enabled = pings_enabled
        self.updated = updated or self.pub_date
        self.uid = uid or self.link
        self.parser = parser or 'plain'

    @property
    def id(self):
        return md5.new(self.uid).hexdigest()

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.title
        )


class Comment(object):
    """
    Represents a comment on a post.
    """

    def __init__(self, author, author_email, author_url, remote_addr,
                 pub_date, body, parser=None, is_pingback=False,
                 status=COMMENT_MODERATED):
        self.author = author
        self.author_email = author_email
        self.author_url = author_url
        self.remote_addr = remote_addr
        self.pub_date = pub_date
        self.body = body
        self.parser = parser or 'plain'
        self.is_pingback = is_pingback
        self.status = status

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


from zine.importers.wordpress import WordPressImporter
from zine.importers.blogger import BloggerImporter
all_importers = [WordPressImporter, BloggerImporter]
