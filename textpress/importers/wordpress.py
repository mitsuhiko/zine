# -*- coding: utf-8 -*-
"""
    textpress.importers.wordpress
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Implements an importer for WordPress extended RSS feeds.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
import urllib
from time import strptime
from datetime import datetime
from textpress.importers import Importer, Blog, Label, Author, Post, Comment
from textpress.utils import _html_entities, get_etree


class _Namespace(object):
    def __init__(self, uri):
        self._uri = uri
    def __getattr__(self, name):
        return '{%s}%s' % (self._uri, name)

CONTENT = _Namespace('http://purl.org/rss/1.0/modules/content/')
COMMENT_API = _Namespace('http://wellformedweb.org/CommentAPI/')
DC_METADATA = _Namespace('http://purl.org/dc/elements/1.1/')
WORDPRESS = _Namespace('http://wordpress.org/export/1.0/')


def open_and_inject_dtd(resource):
    """
    Opens the resource (file pointer or url/filename), removes the XML
    preamble if there is one and injects an inline DTD that makes the
    parser happy.  Then parses it using etree.
    """
    etree = get_etree()
    if isinstance(resource, basestring):
        resource = urllib.urlopen(resource)

    lines = resource.read().splitlines()
    for idx, line in enumerate(lines):
        line = line.strip()
        if line and line.startswith('<?xml'):
            idx += 1
            break

    lines.insert(idx, '<!DOCTYPE wordpress [ %s ]>' % '\n'.join(
        '<!ENTITY %s "&#%d;">' % (name, codepoint)
        for name, codepoint in _html_entities.iteritems()
    ))

    return etree.fromstring('\n'.join(lines)).find('channel')


def parse_wordpress_date(value):
    """Parse a wordpress date or return `None` if not possible."""
    try:
        return datetime(*strptime(value, '%Y-%m-%d %H:%M:%S')[:7])
    except:
        pass


def parse_feed(resource):
    tree = open_and_inject_dtd(resource)

    authors = {}
    def get_author(name):
        author = authors.get(name)
        if author is None:
            author = authors[name] = Author(name, None)
        return author

    labels = {}
    for item in tree.findall(WORDPRESS.category):
        label = Label(item.findtext(WORDPRESS.cat_name),
                      item.findtext(WORDPRESS.category_nicename))
        labels[label.slug] = label

    posts = []
    for item in tree.findall('item'):
        posts.append(Post(
            item.findtext(WORDPRESS.post_name),
            item.findtext('title'),
            item.findtext('link'),
            parse_wordpress_date(item.findtext(WORDPRESS.post_date_gmt)),
            get_author(item.findtext(DC_METADATA.creator)),
            item.findtext('description'),
            item.findtext(CONTENT.encoded),
            [labels[x] for x in item.find('category') if x in labels],
            [Comment(
                x.findtext(WORDPRESS.comment_author),
                x.findtext(WORDPRESS.comment_author_email),
                x.findtext(WORDPRESS.comment_author_url),
                x.findtext(WORDPRESS.comment_author_ip),
                parse_wordpress_date(x.findtext(WORDPRESS.comment_date_gmt)),
                x.findtext(WORDPRESS.comment_content)
            ) for x in item.findall(WORDPRESS.comment)],
            item.findtext('comment_status') != 'closed',
            item.findtext('ping_status') != 'closed'
        ))

    return Blog(
        tree.findtext('title'),
        tree.findtext('link'),
        tree.findtext('description') or '',
        tree.findtext('language') or 'en',
        labels.values(),
        posts,
        authors.values()
    )


class WordPressImporter(Importer):
    name = 'wordpress'
    title = 'WordPress'
