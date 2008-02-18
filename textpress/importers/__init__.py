# -*- coding: utf-8 -*-
"""
    textpress.importers
    ~~~~~~~~~~~~~~~~~~~

    Package for all kinds of importers.  This implements the basic import
    API as well as some core importers we implement as part of the software
    and not as plugin.

    :copyright: Copyright 2008 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
import os
from time import time
from pickle import dump, load, HIGHEST_PROTOCOL
from datetime import datetime
from textpress.api import require_role
from textpress.models import ROLE_ADMIN


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
        from textpress.views.admin import render_admin_response
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
            dump({
                'importer':     self.title,
                'source':       blog.link,
                'title':        blog.title,
                'dump_date':    blog.dump_date
            }, f, HIGHEST_PROTOCOL)
            dump(blog, f, HIGHEST_PROTOCOL)
        finally:
            f.close()

    def __init__(self, app):
        self.app = app

    def __call__(self, request):
        return require_role(ROLE_ADMIN)(self.configure)(request)

    def configure(self, request):
        """
        Subclasses should override this and implement the admin panel
        that ask for details and imports to the queue.
        """


class Blog(object):
    """
    Represents a blog.
    """

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

    def __repr__(self):
        return '<%s %r posts: %d, authors: %d>' % (
            self.__class__.__name__,
            self.title,
            len(self.posts),
            len(self.authors)
        )


class Author(object):
    """
    Represents an author.
    """

    def __init__(self, name, email):
        self.name = name
        self.email = email

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class Label(object):
    """
    Represents a category or tag.
    """

    def __init__(self, slug, name):
        self.slug = slug
        self.name = name

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.name
        )


class Post(object):
    """
    Represents a blog post.
    """

    def __init__(self, slug, title, link, pub_date, author, intro, body,
                 labels=None, comments=None, comments_enabled=True,
                 pings_enabled=True):
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
                 pub_date, body):
        self.author = author
        self.author_email = author_email
        self.author_url = author_url
        self.remote_addr = remote_addr
        self.pub_date = pub_date
        self.body = body

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.author
        )


from textpress.importers.wordpress import WordPressImporter
all_importers = [WordPressImporter]
