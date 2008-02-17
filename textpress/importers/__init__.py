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


class Importer(object):

    #: the shortname of the importer.  This is used for the URLs
    #: and internal addressing.
    name = None

    @property
    def title(self):
        return self.name.title()

    def __init__(self, app):
        self.app = app

    def __call__(self, request):
        pass


class Blog(object):
    """
    Represents a blog.
    """

    def __init__(self, title, link, description, language='en', labels=None,
                 posts=None, authors=None):
        self.title = title
        self.link = link
        self.description = description
        self.language = language
        self.labels = labels or []
        self.posts = posts or []
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
