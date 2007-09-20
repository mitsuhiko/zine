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


_paragraph_re = re.compile(r'(?:\s*\n){2,}')

_unsave_attributes = set([
    'onload', 'onunload', 'onclick', 'ondblclick', 'onmousedown', 'onmouseup',
    'onmouseover', 'onmousemove', 'onmouseout', 'onfocus', 'onblur',
    'onkeypress', 'onkeydown', 'onkeyup', 'onsubmit', 'onreset', 'onselect',
    'onchange', 'style', 'class'
])
_unsafe_tags = set(['style', 'script'])


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

        #: tags that are allowed in a paragraph (not necessariliy inline tags)
        self.paragraph_tags = self.nestable_inline_tags | set([
            'br', 'img', 'are', 'input', 'textarea', 'em', 'strong', 'b', 'i',
            'cite', 'dfn', 'code', 'samp', 'kbd', 'var', 'abbr', 'acronym',
            'big', 'small', 'tt', 'var'
        ])

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


class AutoParagraphHTMLParser(SimpleHTMLParser):
    """
    This parser replaces multiple newlines with paragraphs automatically if
    the active element is either not present (top level), a div or a
    blockquote tag.  There must be no unbalanced inline tags.
    """

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Automatic Paragraphs')

    def __init__(self):
        self.blocks_with_paragraphs = set(['div', 'blockquote'])
        SimpleHTMLParser.__init__(self)

    def parse(self, input_data, reason):
        tree = SimpleHTMLParser.parse(self, input_data, reason)

        def rewrite(parent):
            for node in parent.children[:]:
                rewrite(node)
            if parent is tree or (parent.__class__ is Node and
                                  parent.name in self.blocks_with_paragraphs):
                paragraphs = [[]]
                for child in parent.children:
                    if child.__class__ is TextNode:
                        blocks = _paragraph_re.split(child.value)
                        if len(blocks) > 1:
                            for block in blocks:
                                if block:
                                    paragraphs[-1].append(TextNode(block))
                                paragraphs.append([])
                            continue
                    if child.__class__ is Node and \
                       child.name not in self.paragraph_tags:
                        paragraphs.extend([child, []])
                    else:
                        paragraphs[-1].append(child)

                print paragraphs

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
