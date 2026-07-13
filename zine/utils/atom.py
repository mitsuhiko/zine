"""Small Atom feed builder retained from Werkzeug's removed contrib API.

Based on ``werkzeug.contrib.atom`` (copyright Pallets, BSD-3-Clause).
"""
from datetime import datetime

from werkzeug.wrappers import Response

from zine._compat import escape
from zine.utils.dates import format_iso8601


XHTML_NAMESPACE = 'http://www.w3.org/1999/xhtml'


def _text_block(name, content, content_type=None):
    if content_type == 'xhtml':
        return '<%s type="xhtml"><div xmlns="%s">%s</div></%s>\n' % (
            name, XHTML_NAMESPACE, content, name
        )
    if not content_type:
        return '<%s>%s</%s>\n' % (name, escape(content), name)
    return '<%s type="%s">%s</%s>\n' % (
        name, content_type, escape(content), name
    )


def _authors(value):
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    result = []
    for author in value:
        if not isinstance(author, dict):
            author = {'name': author}
        if 'name' not in author:
            raise TypeError('author must contain at least a name')
        result.append(author)
    return result


def _attributes(values):
    return ''.join(
        '%s="%s" ' % (key, escape(value))
        for key, value in values.items()
        if value is not None
    )


class FeedEntry(object):
    """An entry used by :class:`AtomFeed`."""

    def __init__(self, title=None, content=None, feed_url=None, **kwargs):
        self.title = title
        self.title_type = kwargs.get('title_type', 'text')
        self.content = content
        self.content_type = kwargs.get('content_type', 'html')
        self.url = kwargs.get('url')
        self.id = kwargs.get('id', self.url)
        self.updated = kwargs.get('updated')
        self.summary = kwargs.get('summary')
        self.summary_type = kwargs.get('summary_type', 'html')
        self.author = _authors(kwargs.get('author'))
        self.published = kwargs.get('published')
        self.rights = kwargs.get('rights')
        self.rights_type = kwargs.get('rights_type')
        self.links = kwargs.get('links', [])
        self.categories = kwargs.get('categories', [])
        self.xml_base = kwargs.get('xml_base', feed_url)
        if not self.title:
            raise ValueError('title is required')
        if not self.id:
            raise ValueError('id is required')
        if not self.updated:
            raise ValueError('updated is required')

    def generate(self):
        base = ''
        if self.xml_base:
            base = ' xml:base="%s"' % escape(self.xml_base)
        yield '<entry%s>\n' % base
        yield '  ' + _text_block('title', self.title, self.title_type)
        yield '  <id>%s</id>\n' % escape(self.id)
        yield '  <updated>%s</updated>\n' % format_iso8601(self.updated)
        if self.published:
            yield '  <published>%s</published>\n' % format_iso8601(
                self.published
            )
        if self.url:
            yield '  <link href="%s" />\n' % escape(self.url)
        for author in self.author:
            yield '  <author>\n'
            yield '    <name>%s</name>\n' % escape(author['name'])
            if author.get('uri'):
                yield '    <uri>%s</uri>\n' % escape(author['uri'])
            if author.get('email'):
                yield '    <email>%s</email>\n' % escape(author['email'])
            yield '  </author>\n'
        for link in self.links:
            yield '  <link %s/>\n' % _attributes(link)
        for category in self.categories:
            yield '  <category %s/>\n' % _attributes(category)
        if self.summary:
            yield '  ' + _text_block(
                'summary', self.summary, self.summary_type
            )
        if self.content:
            yield '  ' + _text_block(
                'content', self.content, self.content_type
            )
        if self.rights:
            yield '  ' + _text_block('rights', self.rights, self.rights_type)
        yield '</entry>\n'

    def to_string(self):
        return ''.join(self.generate())

    def __str__(self):
        return self.to_string()


class AtomFeed(object):
    """Compatibility implementation of Werkzeug's former ``AtomFeed``."""

    default_generator = ('Zine', None, None)

    def __init__(self, title=None, entries=None, **kwargs):
        self.title = title
        self.title_type = kwargs.get('title_type', 'text')
        self.url = kwargs.get('url')
        self.feed_url = kwargs.get('feed_url', self.url)
        self.id = kwargs.get('id', self.feed_url)
        self.updated = kwargs.get('updated')
        self.author = _authors(kwargs.get('author'))
        self.icon = kwargs.get('icon')
        self.logo = kwargs.get('logo')
        self.rights = kwargs.get('rights')
        self.rights_type = kwargs.get('rights_type')
        self.subtitle = kwargs.get('subtitle')
        self.subtitle_type = kwargs.get('subtitle_type', 'text')
        self.generator = kwargs.get('generator') or self.default_generator
        self.links = kwargs.get('links', [])
        self.entries = list(entries or ())
        if not self.title:
            raise ValueError('title is required')
        if not self.id:
            raise ValueError('id is required')

    def add(self, *args, **kwargs):
        if len(args) == 1 and not kwargs and isinstance(args[0], FeedEntry):
            entry = args[0]
        else:
            kwargs['feed_url'] = self.feed_url
            entry = FeedEntry(*args, **kwargs)
        self.entries.append(entry)

    def generate(self):
        authors = self.author
        if not authors and any(not entry.author for entry in self.entries):
            authors = [{'name': 'Unknown author'}]
        updated = self.updated
        if updated is None:
            dates = sorted(entry.updated for entry in self.entries)
            updated = dates[-1] if dates else datetime.now()

        yield '<?xml version="1.0" encoding="utf-8"?>\n'
        yield '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        yield '  ' + _text_block('title', self.title, self.title_type)
        yield '  <id>%s</id>\n' % escape(self.id)
        yield '  <updated>%s</updated>\n' % format_iso8601(updated)
        if self.url:
            yield '  <link href="%s" />\n' % escape(self.url)
        if self.feed_url:
            yield '  <link href="%s" rel="self" />\n' % escape(self.feed_url)
        for link in self.links:
            yield '  <link %s/>\n' % _attributes(link)
        for author in authors:
            yield '  <author>\n'
            yield '    <name>%s</name>\n' % escape(author['name'])
            if author.get('uri'):
                yield '    <uri>%s</uri>\n' % escape(author['uri'])
            if author.get('email'):
                yield '    <email>%s</email>\n' % escape(author['email'])
            yield '  </author>\n'
        if self.subtitle:
            yield '  ' + _text_block(
                'subtitle', self.subtitle, self.subtitle_type
            )
        if self.icon:
            yield '  <icon>%s</icon>\n' % escape(self.icon)
        if self.logo:
            yield '  <logo>%s</logo>\n' % escape(self.logo)
        if self.rights:
            yield '  ' + _text_block('rights', self.rights, self.rights_type)
        name, url, version = self.generator
        if name or url or version:
            attributes = _attributes({'uri': url, 'version': version})
            yield '  <generator %s>%s</generator>\n' % (
                attributes, escape(name or '')
            )
        for entry in self.entries:
            for line in entry.generate():
                yield '  ' + line
        yield '</feed>\n'

    def to_string(self):
        return ''.join(self.generate())

    def get_response(self):
        return Response(self.to_string(), mimetype='application/atom+xml')

    def __call__(self, environ, start_response):
        return self.get_response()(environ, start_response)

    def __str__(self):
        return self.to_string()
