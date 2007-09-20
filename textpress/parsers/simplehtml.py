# -*- coding: utf-8 -*-
"""
    textpress.parsers.simplehtml
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    HTML alike syntax.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL, see LICENSE for more details.
"""
import re
from textpress.application import emit_event
from textpress.parsers import BaseParser
from textpress.fragment import Node, TextNode, Fragment
from textpress._ext import beautifulsoup as bt


_paragraph_re = re.compile(r'\n{2,}')


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
        self.isolated_tags = set(['script', 'style', 'pre'])
        self.self_closing_tags = set(['br', 'img', 'area', 'hr', 'param',
                                      'meta', 'link', 'base', 'input',
                                      'embed', 'col'])
        self.nestable_block_tags = set(['blockquote', 'div', 'fieldset'])
        self.non_nestable_block_tags = set(['address', 'form', 'p'])
        self.nestable_inline_tags = set(['span', 'font', 'q', 'object', 'bdo',
                                         'sub', 'sup', 'center', 'small'])

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


class AutoParagraphHTMLParser(SimpleHTMLParser):
    """
    Non working parser that should one time automatically insert <p>
    tags inside divs and blockquotes if there are lines divided by
    multiple newlines
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('HTML with automatic Paragraphs')

    def __init__(self):
        self.blocks_with_paragraphs = set(['div', 'blockquote'])
        SimpleHTMLParser.__init__(self)

    def parse(self, input_data, reason):
        tree = SimpleHTMLParser.parse(self, input_data, reason)

        def walk(parent):
            for idx, node in enumerate(parent.children[:]):
                if isinstance(node, TextNode) and (parent is tree or
                   node.parent.name in self.blocks_with_paragraphs):
                    paragraphs = _paragraph_re.split(node.value)
                    if len(paragraphs) > 1:
                        parent.children.pop()
                        new_node = Node('p')
                        for x in xrange(1, idx + 1):
                            new_node.children.append(parent.children.pop(0))
                        new_node.children.append(TextNode(paragraphs.pop(0)))
                        parent.children.append(new_node)
                        for paragraph in paragraphs:
                            new_node = Node('p')
                            new_node.children.append(TextNode(paragraph))
                            parent.children.append(new_node)
                        print parent
                elif node.__class__ is Node:
                    walk(node)
        walk(tree)

        return tree
