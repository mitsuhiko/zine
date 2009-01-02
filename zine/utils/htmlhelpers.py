# -*- coding: utf-8 -*-
"""
    zine.utils.htmlhelpers
    ~~~~~~~~~~~~~~~~~~~~~~

    This module povides helpers for the templates but can be useful for
    the views and modules too. In the template it's available as "h".

    TODO: get rid of that module and use werkzeug.html directly where needed.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import html


def input_field(name, value='', type='text', **attr):
    """Render an input field."""
    return html.input(name=name, value=value, type=type, **attr)


def textarea(name, value='', cols=50, rows=10, **attr):
    """Render a textarea."""
    return html.textarea(value, name=name, cols=cols, rows=rows, **attr)


def checkbox(name, checked=False, value='yes', **attr):
    """Render a checkbox."""
    return html.input(type='checkbox', name=name, value=value,
                      checked=checked, **attr)


def radio_button(name, value='yes', checked=False, **attr):
    """Render a checkbox."""
    return html.input(type='radio', value=value, name=name,
                      checked=checked, **attr)


def script(src, type='text/javascript', **attr):
    """Render a script tag."""
    return html.script(src=src, type=type, **attr)


def meta(http_equiv=None, name=None, content=None, **attr):
    """Render a meta tag."""
    return html.meta(http_equiv=http_equiv, name=name, content=content, **attr)


def link(rel, href, type=None, title=None, charset=None, media=None, **attr):
    """Render a link tag."""
    return html.link(rel=rel, href=href, type=type, title=title, charset=charset,
                     media=media)
