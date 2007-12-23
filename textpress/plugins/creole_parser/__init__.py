# -*- coding: utf-8 -*-
"""
    textpress.plugins.creole_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blg posts.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.parsers import BaseParser
from textpress.fragment import Node, TextNode, Fragment
from creoleparser import Parser, Creole10
from genshi.core import END, START, TEXT
from werkzeug import url_quote
from urlparse import urljoin


def path_func(page_name):
    root = get_request().script_root
    if not root.endswith('/'):
        root += '/'
    return urljoin(root, url_quote(page_name))


creole_parser = Parser(dialect=Creole10(
    wiki_links_base_url='',
    wiki_links_path_func=path_func,
    wiki_links_space_char='_',
    no_wiki_monospace=True,
    use_additions=True
))


class CreoleParser(BaseParser):

    get_name = staticmethod(lambda: u'Creole')

    def parse(self, input_data, reason):
        result = Fragment()
        stack = [result]
        for kind, data, pos in creole_parser.generate(input_data):
            if kind == START:
                tag, attrs = data
                new_node = Node(tag, dict((k.localname, v) for k, v in attrs))
                stack[-1].children.append(new_node)
                stack.append(new_node)
            elif kind == END:
                stack.pop()
            elif kind == TEXT:
                stack[-1].children.append(TextNode(data))
        return result


def setup(app, plugin):
    app.add_parser('creole', CreoleParser)
