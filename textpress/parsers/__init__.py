# -*- coding: utf-8 -*-
"""
    textpress.parsers
    ~~~~~~~~~~~~~~~~~

    This module holds the base parser informations and the dict of
    default parsers.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
from textpress.application import emit_event, get_application


def parse(input_data, parser=None, reason='unknown', optimize=True):
    """
    Generate a doc tree out of the data provided. If we are not in unbound
    mode the `process-doc-tree` event is sent so that plugins can modify
    the tree in place. The reason is useful for plugins to find out if they
    want to render it or now. For example a normal blog post would have the
    reason 'post-body' or 'post-intro', an isolated page from a plugin maybe
    'page' etc.

    If optimize is enabled the return value might be a non queryable fragment.
    """
    app = get_application()
    if parser is None:
        try:
            parser_cls = app.parsers[app.cfg['default_parser']]
        except KeyError:
            # the plugin that provided the default parser is not
            # longer available.  reset the config value to the builtin
            # parser and parse afterwards.
            app.cfg.revert_to_default('default_parser')
            parser_cls = SimpleHTMLParser
    else:
        try:
            parser_cls = app.parsers[parser]
        except KeyError:
            raise ValueError('parser %r does not exist' % (parser,))

    parser = parser_cls()
    tree = parser.parse(input_data, reason)

    #! allow plugins to alter the doctree.
    for item in emit_event('process-doc-tree', tree, input_data, reason):
        if item is not None:
            tree = item
            break

    if optimize:
        return tree.optimize()
    return tree


class BaseParser(object):
    """
    Baseclass for all kinds of parsers.
    """

    @staticmethod
    def get_name():
        """Return the (localized) name of the parser."""
        return self.__class__.__name__

    def parse(self, input_data, reason):
        """Return a fragment."""


from textpress.parsers.simplehtml import SimpleHTMLParser
from textpress.parsers.comments import CommentParser

all_parsers = {
    'default':          SimpleHTMLParser,
    'comment':          CommentParser
}
