# -*- coding: utf-8 -*-
"""
    textpress.plugins.markdown_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blog posts.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.parsers import BaseParser
from textpress.fragment import Fragment, Node, TextNode, DataNode
from textpress.plugins.markdown_parser import markdown as md


class MarkdownParser(BaseParser):

    get_name = staticmethod(lambda: u'Markdown')

    def parse(self, input_data, reason):
        parser = md.Markdown(input_data)
        def convert_tree(node):
            if isinstance(node, md.Document):
                return convert_tree(node.documentElement)
            elif isinstance(node, md.CDATA):
                return DataNode(node.text)
            elif isinstance(node, md.TextNode):
                return TextNode(node.value)
            elif isinstance(node, md.EntityReference):
                return DataNode(node.toxml())
            elif node.isDocumentElement:
                result = Fragment()
            else:
                result = Node(node.nodeName, node.attribute_values)
            for child in node.childNodes:
                result.children.append(convert_tree(child))
            return result
        return convert_tree(parser._transform())


def setup(app, plugin):
    app.add_parser('markdown', MarkdownParser)
