# -*- coding: utf-8 -*-
"""
    textpress.feedbuilder
    ~~~~~~~~~~~~~~~~~~~~~

    Provides a class that generates ATOM feeds.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from xml.dom.minidom import Document
from datetime import datetime

from textpress.application import Response
from textpress.utils import format_iso8601


class AtomFeed(object):
    """
    This class generates valid Atom feeds.
    """

    NAMESPACE = 'http://www.w3.org/2005/Atom'
    MIMETYPE = 'application/atom+xml'

    def __init__(self, title, description, link):
        self.title = title
        self.description = description
        self.link = link
        self.items = []
        self._last_update = None

    def add_item(self, title, author, link, description, pub_date,
                 links=None):
        if self._last_update is None or pub_date > self._last_update:
            self._last_update = pub_date
        date = pub_date or datetime.utcnow()
        self.items.append({
            'title':        title,
            'author':       author,
            'link':         link,
            'description':  description,
            'pub_date':     date,
            'links':        links or []
        })

    def generate_document(self):
        doc = Document()
        Element = doc.createElement
        Text = doc.createTextNode

        atom = doc.appendChild(Element('feed'))
        atom.setAttribute('xmlns', self.NAMESPACE)

        atom.appendChild(Element('title')).appendChild(Text(self.title))
        atom.appendChild(Element('link')).setAttribute('href', self.link)

        subtitle = atom.appendChild(Element('subtitle'))
        subtitle.setAttribute('type', 'html')
        subtitle.appendChild(Text(self.description))

        date = format_iso8601(self._last_update or datetime.utcnow())
        atom.appendChild(Element('updated')).appendChild(Text(date))

        for item in self.items:
            d = Element('entry')
            d.appendChild(Element('title')).appendChild(Text(item['title']))
            author = d.appendChild(Element('author'))
            author.appendChild(Element('name')).appendChild(Text(item['author']))
            d.appendChild(Element('link')).setAttribute('href', item['link'])
            d.appendChild(Element('id')).appendChild(Text(item['link']))
            date = format_iso8601(item['pub_date'])
            d.appendChild(Element('published')).appendChild(Text(date))
            d.appendChild(Element('updated')).appendChild(Text(date))
            content = d.appendChild(Element('summary'))
            content.setAttribute('type', 'html')
            content.appendChild(Text(unicode(item['description'])))

            for link in item['links']:
                d = Element('link')
                for key, value in link.iteritems():
                    d.setAttribute(key, unicode(value))

            atom.appendChild(d)

        return doc.toxml('utf-8')

    def generate_response(self):
        return Response(self.generate_document(), mimetype=self.MIMETYPE)
