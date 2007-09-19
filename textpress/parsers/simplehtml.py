# -*- coding: utf-8 -*-
"""
    textpress.parsers.simplehtml
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    HTML alike syntax.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
from textpress.application import emit_event
from textpress.parsers import BaseParser
from textpress.fragment import Node, TextNode, Fragment
from textpress._ext import beautifulsoup as bt


class SimpleHTMLParser(BaseParser):
    """
    Special class that emits an `setup-markup-parser` event when setting up
    itself so that plugins can change the way elements are processed.

    Don't instanciate this parser yourself, better use the parse() method
    that caches parsers.
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Simplified HTML')

    def __init__(self):
        self.isolated_tags = ['script', 'style', 'pre']
        self.self_closing_tags = ['br', 'img', 'area', 'hr', 'param', 'meta',
                                  'link', 'base', 'input', 'embed', 'col']
        self.nestable_block_tags = ['blockquote', 'div', 'fieldset', 'ins',
                                    'del']
        self.non_nestable_block_tags = ['address', 'form', 'p']
        self.nestable_inline_tags = ['span', 'font', 'q', 'object', 'bdo',
                                     'sub', 'sup', 'center']
        #! allow plugins to modify the semantic rules of tags etc...
        emit_event('setup-simplehtml-parser', self, buffered=True)

        # rather bizarre way to subclass beautiful soup but since the library
        # itself isn't less bizarre...
        self._parser = p = type('_SoupParser', (bt.BeautifulSoup, object), {
            'SELF_CLOSING_TAGS':        dict.fromkeys(self.self_closing_tags),
            'QUOTE_TAGS':               self.isolated_tags,
            'NESTABLE_BLOCK_TAGS':      self.nestable_block_tags,
            'NON_NESTABLE_BLOCK_TAGS':  self.non_nestable_block_tags,
            'NESTABLE_INLINE_TAGS':     self.nestable_inline_tags
        })
        p.RESET_NESTING_TAGS = bt.buildTagMap(None,
            p.NESTABLE_BLOCK_TAGS, 'noscript', p.NON_NESTABLE_BLOCK_TAGS,
            p.NESTABLE_LIST_TAGS, p.NESTABLE_TABLE_TAGS
        )
        p.NESTABLE_TAGS = bt.buildTagMap([],
            p.NESTABLE_INLINE_TAGS, p.NESTABLE_BLOCK_TAGS,
            p.NESTABLE_LIST_TAGS, p.NESTABLE_TABLE_TAGS
        )

    def parse(self, input_data, reason):
        """Parse the data and convert it into a sane, processable format."""
        def convert_tree(node, root):
            if root:
                result = Fragment()
            else:
                result = Node(node.name, node._getAttrMap())
            add = result.children.append
            for child in node.contents:
                if isinstance(child, unicode):
                    # get rid of the navigable string, it breaks dumping
                    add(TextNode(child + ''))
                else:
                    add(convert_tree(child, False))
            return result
        bt_tree = self._parser(input_data, convertEntities=
                               self._parser.HTML_ENTITIES)
        return convert_tree(bt_tree, True)
