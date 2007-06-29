# -*- coding: utf-8 -*-
"""
    textpress.htmlhelpers
    ~~~~~~~~~~~~~~~~~~~~~

    This module povides helpers for the templates but can be useful for
    the views and modules too. In the template it's available as "h".

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from xml.sax.saxutils import escape, quoteattr
from textpress.htmlprocessor import SELF_CLOSING_TAGS

jinja_allowed_attributes = __all__ = [
    'input_field', 'checkbox', 'radio_button', 'textarea'
]

_binary = object()


def _generate_tag(name, attr=None, contents=''):
    buf = [u'<' + name]
    if attr:
        if 'name' in attr and not 'id' in attr:
            attr['id'] = attr['name']
        tmp = []
        for key, value in attr.iteritems():
            if value is _binary:
                tmp.append(key)
            elif value is not None:
                value = unicode(value)
                tmp.append(u'%s=%s' % (key, quoteattr(value)))
        if tmp:
            buf.append(' ' + u' '.join(tmp))
    buf.append('>')
    if name in SELF_CLOSING_TAGS:
        if contents:
            raise RuntimeError('got contents for empty tag')
    else:
        if contents:
            buf.append(escape(contents))
        buf.append(u'</%s>' % name)
    return u''.join(buf)


def input_field(name, value='', type='text', **attr):
    """Render an input field."""
    attr.update(name=name, value=value, type=type)
    return _generate_tag('input', attr)


def textarea(name, value='', cols=50, rows=10, **attr):
    """Render a textarea."""
    attr.update(name=name, cols=cols, rows=rows)
    return _generate_tag('textarea', attr, value)


def checkbox(name, value='yes', checked=False, **attr):
    """Render a checkbox."""
    attr.update(type='checkbox', name=name, value=value)
    if checked:
        attr['checked'] = _binary
    return _generate_tag('input', attr)


def radio_button(name, value='yes', checked=False, **attr):
    """Render a radio button."""
    attr.update(type='radio', name=name, value=value)
    if checked:
        attr['checked'] = _binary
    return _generate_tag('input', attr)


def script(href, type='text/x-javascript', **attr):
    """Render a script tag."""
    attr.update(href=href, type=type, id=None)
    return _generate_tag('script', attr)


def meta(http_equiv=None, name=None, content=None, **attr):
    """Render a meta tag."""
    attr.update(http_equiv=http_equiv, name=name, content=content, id=None)
    return _generate_tag('meta', attr)


def link(rel, href, type=None, title=None, charset=None, media=None, **attr):
    """Render a link tag."""
    attr.update(rel=rel, href=href, type=type, title=title, charset=charset,
                media=media, id=None)
    return _generate_tag('link', attr)
