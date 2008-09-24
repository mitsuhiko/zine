# -*- coding: utf-8 -*-
"""
    zine.parsers
    ~~~~~~~~~~~~

    This module holds the base parser informations and the dict of
    default parsers.

    :copyright: Copyright 2007-2008 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
from werkzeug import escape

from zine.application import iter_listeners, get_application
from zine.utils.zeml import parse_html, parse_zeml, sanitize
from zine.i18n import lazy_gettext


def parse(input_data, parser=None, reason='unknown'):
    """Generate a doc tree out of the data provided.  If we are not in unbound
    mode the `process-doc-tree` event is sent so that plugins can modify
    the tree in place. The reason is useful for plugins to find out if they
    want to render it or now. For example a normal blog post would have the
    reason 'post-body' or 'post-intro', an isolated page from a plugin maybe
    'page' etc.
    """
    input_data = u'\n'.join(input_data.splitlines())
    app = get_application()
    if parser is None:
        try:
            parser = app.parsers[app.cfg['default_parser']]
        except KeyError:
            # the plugin that provided the default parser is not
            # longer available.  reset the config value to the builtin
            # parser and parse afterwards.
            t = app.cfg.edit()
            t.revert_to_default('default_parser')
            t.commit()
            parser = app.parsers[app.cfg['default_parser']]
    else:
        try:
            parser = app.parsers[parser]
        except KeyError:
            raise ValueError('parser %r does not exist' % (parser,))

    tree = parser.parse(input_data, reason)

    #! allow plugins to alter the doctree.
    for callback in iter_listeners('process-doc-tree'):
        item = callback(tree, input_data, reason)
        if item is not None:
            tree = item

    return tree


class BaseParser(object):
    """Baseclass for all kinds of parsers."""

    #: the localized name of the parser.
    name = None

    def __init__(self, app):
        self.app = app

    def parse(self, input_data, reason):
        """Return a ZEML tree."""


class ZEMLParser(BaseParser):
    """The parser for the ZEML Markup language."""

    name = lazy_gettext('Zine-Markup')

    def parse(self, input_data, reason):
        rv = parse_zeml(input_data, self.app.zeml_element_handlers)
        if reason == 'comment':
            rv = sanitize(rv)
        return rv


class HTMLParser(BaseParser):
    """A parser that understands plain old HTML."""

    name = lazy_gettext('HTML')

    def parse(self, input_data, reason):
        rv = parse_html(input_data)
        if reason == 'comment':
            rv = sanitize(rv)
        return rv


class PlainTextParser(BaseParser):

    name = lazy_gettext('Text')

    def parse(self, input_data, reason):
        return escape(input_data)


all_parsers = {
    'zeml':             ZEMLParser,
    'html':             HTMLParser,
    'text':             PlainTextParser
}
