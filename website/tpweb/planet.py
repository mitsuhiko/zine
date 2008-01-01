# -*- coding: utf-8 -*-
"""
    tpweb.planet
    ~~~~~~~~~~~~

    The planet.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL
"""
import sys
import feedparser
from datetime import datetime, date
from werkzeug import escape
from werkzeug.contrib.atom import AtomFeed
from sqlalchemy import MetaData, Table, Column, ForeignKey, Boolean, \
     Integer, String, DateTime
from sqlalchemy.orm import dynamic_loader
from tpweb.application import session, metadata, render_to_response
from tpweb.utils import Pagination, nl2p, strip_tags


HTML_MIMETYPES = set(['text/html', 'application/xml+xhtml'])


def show_index(request, page):
    """Show the planet index page."""
    days = []
    days_found = set()
    query = Entry.query.order_by(Entry.pub_date.desc())
    pagination = Pagination(request, query, 20, page, 'community/planet')
    for entry in pagination.entries:
        day = date(*entry.pub_date.timetuple()[:3])
        if day not in days_found:
            days_found.add(day)
            days.append({'date': day, 'entries': []})
        days[-1]['entries'].append(entry)
    return render_to_response(request, 'community/planet.html', {
        'days':         days,
        'pagination':   pagination,
        'blogs':        Blog.query.all()
    })


def get_feed(request):
    """Return an Atom feed with the most recent entries."""
    feed = AtomFeed('TextPress Planet', feed_url=request.url,
                    url=request.url_adapter.build('community/planet'),
                    subtitle='TextPress related blogs.')
    for entry in Entry.query.order_by(Entry.pub_date.desc())[:10]:
        feed.add(entry.title, entry.text, content_type='html',
                 author={
                     'name':    entry.blog.name,
                     'uri':     entry.blog.url
                 }, url=entry.url, updated=entry.last_update,
                 published=entry.pub_date)
    return feed.get_response()


def sync():
    """Synchronize the entries."""
    for blog in Blog.query.all():
        # parse the feed. feedparser.parse will never given an exception
        # but the bozo bit might be defined.
        feed = feedparser.parse(blog.feed_url)
        blog_author = feed.get('author') or blog.name
        blog_author_detail = feed.get('author_detail')

        for entry in feed.entries:
            # get the guid. either the id if specified, otherwise the link.
            # if none is available we skip the entry.
            guid = entry.get('id') or entry.get('link')
            if not guid:
                continue

            # get an old entry for the guid to check if we need to update
            # or recreate the item
            old_entry = Entry.query.filter_by(guid=guid).first()

            # get title, url and text. skip if no title or no text is
            # given. if the link is missing we use the blog link.
            if 'title_detail' in entry:
                title = entry.title_detail.get('value') or ''
                if entry.title_detail.get('type') in HTML_MIMETYPES:
                    title = strip_tags(title)
                else:
                    title = escape(title)
            else:
                title = entry.get('title')
            url = entry.get('link') or blog.blog_url
            text = 'content' in entry and entry.content[0] or \
                   entry.get('summary_detail')

            if not title or not text:
                continue

            # if we have an html text we use that, otherwise we HTML
            # escape the text and use that one. We also handle XHTML
            # with our tag soup parser for the moment.
            if text.get('type') not in HTML_MIMETYPES:
                text = escape(nl2p(text.get('value') or ''))
            else:
                text = text.get('value') or ''

            # no text? continue
            if not text.strip():
                continue

            # get the pub date and updated date. This is rather complex
            # because different feeds do different stuff
            pub_date = entry.get('published_parsed') or \
                       entry.get('created_parsed') or \
                       entry.get('date_parsed')
            updated = entry.get('updated_parsed') or pub_date
            pub_date = pub_date or updated

            # if we don't have a pub_date we skip.
            if not pub_date:
                continue

            # convert the time tuples to datetime objects.
            pub_date = datetime(*pub_date[:6])
            updated = datetime(*updated[:6])
            if old_entry and updated <= old_entry.last_update:
                continue

            # create a new entry object based on the data collected or
            # update the old one.
            entry = old_entry or Entry()
            entry.blog = blog
            entry.guid = guid
            entry.title = title
            entry.url = url
            entry.text = text
            entry.pub_date = pub_date
            entry.last_update = updated

    session.commit()


blog_table = Table('blogs', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(120)),
    Column('url', String(200)),
    Column('feed_url', String(250))
)

entry_table = Table('entries', metadata,
    Column('id', Integer, primary_key=True),
    Column('blog_id', Integer, ForeignKey('blogs.id')),
    Column('guid', String(200), unique=True),
    Column('title', String(140)),
    Column('url', String(200)),
    Column('text', String),
    Column('pub_date', DateTime),
    Column('last_update', DateTime)
)


class Blog(object):

    def __init__(self, name, url, feed_url):
        self.name = name
        self.url = url
        self.feed_url = feed_url

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.url)


class Entry(object):

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.guid)


session.mapper(Entry, entry_table)
session.mapper(Blog, blog_table, properties=dict(
    entries=dynamic_loader(Entry, backref='blog')
))
