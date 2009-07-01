# -*- coding: utf-8 -*-
"""
    zine.plugins.blogger_feedimport
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Import from the blogger.com extended feed format.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from zine.importers import Tag, Post, Comment, Author
from zine.importers.feed import Extension, SkipItem, atom
from zine.utils.xml import Namespace
from zine.utils.dates import parse_iso8601

BLOGGER_LABEL_SCHEME_URI = 'http://www.blogger.com/atom/ns#'
BLOGGER_KIND_SCHEME_URI = 'http://schemas.google.com/g/2005#kind'
BLOGGER_KIND_BASE_URI = 'http://schemas.google.com/blogger/2008/kind#'


thr = Namespace('http://purl.org/syndication/thread/1.0')


class BloggerExtension(Extension):
    """Handles Blogger's Atom export format.

    Blogger's output uses <entry> elements for

    * posts
    * comments
    * the HTML template
    * blog settings

    in order to get every setting exported.  These are distinguished by a
    <category> element with a special scheme URI; this is determined by
    `_blogger_entry_kind`.  Since all extensions for a specific feed type
    ("atom" in this case) are called for a given feed file, this class needs
    to respect the case that it doesn't deal with a Blogger feed at all.
    """

    feed_types = frozenset(['atom'])

    def __init__(self, app, parser, root):
        Extension.__init__(self, app, parser, root)
        self._posts = {}
        self._comments = []
        self._settings = {}
        self._authors = {}

    def _blogger_entry_kind(self, entry):
        """Find out the "kind" of the entry; returns one of 'post', 'comment',
        'settings', or 'template'.
        """
        for category in entry.findall(atom.category):
            if category.attrib.get('scheme') != BLOGGER_KIND_SCHEME_URI:
                continue
            kind_uri = category.attrib.get('term')
            if kind_uri.startswith(BLOGGER_KIND_BASE_URI):
                return kind_uri[len(BLOGGER_KIND_BASE_URI):]
            else:
                return None

    def _convert_settings(self, blog):
        """Convert as many blogger-exported settings in self._settings as possible
        to equivalent Zine settings.
        """
        get = self._settings.get
        blog.description = get('BLOG_DESCRIPTION', '')
        cfg = blog.configuration
        cfg['comments_enabled'] = get('BLOG_COMMENTS_ALLOWED') == 'true'
        cfg['pings_enabled'] = get('BLOG_BACKLINKS_ALLOWED') == 'true'
        cfg['posts_per_page'] = int(get('BLOG_MAX_NUM', 10))
        cfg['blog_email'] = get('BLOG_COMMENT_EMAIL', '')

    def _assign_comments(self):
        """Assign comments to their respective posts."""
        for (entry, body, pub_date) in self._comments:
            for related in entry.findall(thr['in-reply-to']):
                # this tag has the reference to the post the comment belongs to
                post_id = related.attrib.get('ref')
                if not post_id:
                    continue
                if post_id not in self._posts:
                    print 'XXX unknown post for comment:', post_id
                    continue
                post = self._posts[post_id]
                author_tag = entry.find(atom.author)
                if author_tag is not None:
                    author_uri = author_tag.findtext(atom.uri)
                    # find the author -- either it's one of the post authors, in
                    # which case we can use the same object
                    if author_uri in self._authors:
                        author = self._authors[author_uri]
                        www = None
                    # otherwise, make it an anonymous user
                    else:
                        author = author_tag.findtext(atom.name)
                        www = author_tag.findtext(atom.uri)
                else:
                    author = None
                comment = Comment(author, body, None, www, None,
                                  pub_date, None, 'html')
                post.comments.append(comment)

    def handle_root(self, blog):
        self._assign_comments()
        self._convert_settings(blog)

    def postprocess_post(self, post):
        # the blogger format uses entries for everything; try to find out
        # if this is a post or another piece of data
        entry = post.element
        kind = self._blogger_entry_kind(entry)
        if not kind:
            # not a blogger entry
            return
        elif kind == 'post':
            # ok, this is really a post, record it by ID and its author
            self._posts[entry.findtext(atom.id)] = post
            self._authors[post.author.www] = post.author
            return
        elif kind == 'settings':
            # put the settings in a dictionary; they are assigned to Zine
            # settings in _convert_settings()
            id_parts = entry.findtext(atom.id).split('.')
            if len(id_parts) >= 3 and id_parts[-2] == 'settings':
                self._settings[id_parts[-1]] = entry.findtext(atom.content)
            raise SkipItem
        elif kind == 'template':
            # no way to keep that
            raise SkipItem
        elif kind == 'comment':
            # keep the whole entry, but also don't throw away what parsing the
            # Parser class already did for us
            self._comments.append((entry, post.body, post.pub_date))
            raise SkipItem
        else:
            # unknown blogger entry kind
            raise SkipItem

    def lookup_author(self, author, entry, username, email, uri):
        kind = self._blogger_entry_kind(entry)
        if not kind:
            # not a blogger export
            return None
        if kind != 'post':
            # only create author objects for posts, not comments (or settings)
            raise SkipItem

    def parse_comments(self, post):
        # no way to parse comments here, we have to do this after all entries
        # (which comments are in the blogger output) are parsed
        return None

    def tag_or_category(self, category):
        # assigning labels as tags, since they don't have a description
        scheme = category.attrib.get('scheme')
        if scheme is None:
            return
        if scheme == BLOGGER_LABEL_SCHEME_URI:
            return Tag(category.attrib['term'])
        elif scheme == BLOGGER_KIND_SCHEME_URI:
            raise SkipItem
        # else it's not a blogger special category


def setup(app, plugin):
    app.add_feed_importer_extension(BloggerExtension)
