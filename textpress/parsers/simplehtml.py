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


_paragraph_re = re.compile(r'(\s*\n){2,}')

_unsave_attributes = set([
    'onload', 'onunload', 'onclick', 'ondblclick', 'onmousedown', 'onmouseup',
    'onmouseover', 'onmousemove', 'onmouseout', 'onfocus', 'onblur',
    'onkeypress', 'onkeydown', 'onkeyup', 'onsubmit', 'onreset', 'onselect',
    'onchange', 'style', 'class'
])
_unsafe_tags = set(['style', 'script'])



class HTMLParser(BaseParser):
    """
    A simple HTML Parser.
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Raw HTML')

    def __init__(self):
        self._init_defs()

        #! allow plugins to modify the semantic rules of tags etc...
        emit_event('setup-html-parser', self, buffered=True)

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

    def _init_defs(self):
        self.isolated_tags = set(['script', 'style'])
        self.self_closing_tags = set(['br', 'img', 'area', 'hr', 'param',
                                      'meta', 'link', 'base', 'input',
                                      'embed', 'col'])
        self.nestable_block_tags = set(['blockquote', 'div', 'fieldset'])
        self.non_nestable_block_tags = set(['address', 'form', 'p'])
        self.nestable_inline_tags = set(['span', 'font', 'q', 'object', 'bdo',
                                         'sub', 'sup', 'center', 'small'])
        self.paragraph_tags = self.nestable_inline_tags | set([
            'br', 'img', 'are', 'input', 'textarea', 'em', 'strong', 'b', 'i',
            'cite', 'dfn', 'code', 'samp', 'kbd', 'var', 'abbr', 'acronym',
            'big', 'small', 'tt', 'var'
        ])

    def parse(self, input_data, reason):
        """Parse the data and convert it into a sane, processable format."""
        restricted = reason == 'comment'

        def convert_tree(node, root):
            if root:
                result = Fragment()
            else:
                attributes = node._getAttrMap()
                node_name = node.name

                # in restricted mode remove all scripts, styles and handlers
                if restricted:
                    if node.name in _unsafe_tags:
                        node_name = 'pre'
                    for attr in _unsave_attributes:
                        attributes.pop(attr, None)
                result = Node(node_name, attributes)

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


class SimpleHTMLParser(HTMLParser):
    """
    Like the HTML Parser but simplifies markup a bit.
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Simplified HTML')

    def _init_defs(self):
        HTMLParser._init_defs(self)
        self.isolated_tags.add('pre')


class AutoParagraphHTMLParser(SimpleHTMLParser):
    """
    Like the Simple HTML parser, but it automatically adds paragraphs if it
    finds multiple newlines.
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Automatic Paragraphs')

    def _init_defs(self):
        SimpleHTMLParser._init_defs(self)
        self.blocks_with_paragraphs = set(['div', 'blockquote'])

    def parse(self, input_data, reason):
        tree = SimpleHTMLParser.parse(self, input_data, reason)

        def rewrite(parent):
            for node in parent.children[:]:
                rewrite(node)

            paragraphs = [[]]

            if parent is tree or (parent.__class__ is Node and
                                  parent.name in self.blocks_with_paragraphs):
                for child in parent.children:
                    if child.__class__ is TextNode:
                        blockiter = iter(_paragraph_re.split(child.value))
                        for block in blockiter:
                            try:
                                is_paragraph = bool(blockiter.next())
                            except StopIteration:
                                is_paragraph = False
                            if block:
                                paragraphs[-1].append(TextNode(block))
                            if is_paragraph:
                                paragraphs.append([])
                    elif child.__class__ is Node and \
                         child.name not in self.paragraph_tags:
                        paragraphs.extend((child, []))
                    else:
                        paragraphs[-1].append(child)

                del parent.children[:]
                for paragraph in paragraphs:
                    if isinstance(paragraph, Node):
                        parent.children.append(paragraph)
                    elif paragraph:
                        new_node = Node('p')
                        new_node.children.extend(paragraph)
                        parent.children.append(new_node)
        rewrite(tree)

        return tree
