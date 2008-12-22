# -*- coding: utf-8 -*-
"""
    zine.plugins.creole_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blg posts.

    :copyright: 2007 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from urlparse import urljoin

from creoleparser import Parser, Creole10
from creoleparser.elements import InlineElement
from genshi.core import END, START, TEXT
from werkzeug import url_quote

from zine.api import *
from zine.parsers import BaseParser
from zine.utils.zeml import RootElement, Element


def path_func(page_name):
    root = get_request().script_root
    if not root.endswith('/'):
        root += '/'
    return urljoin(root, url_quote(page_name))


class ZineCreole(Creole10):

    def __init__(self):
        Creole10.__init__(self,
            wiki_links_base_url=u'',
            wiki_links_path_func=path_func,
            wiki_links_space_char=u'_',
            no_wiki_monospace=True,
            use_additions=False
        )
        # support for <intro> ... </intro>
        self.intro_marker = InlineElement('intro', ('<intro>', '</intro>'),
                                          self.inline_elements +
                                          self.block_elements)
        self.block_elements.insert(0, self.intro_marker)


creole_parser = Parser(dialect=ZineCreole())


class CreoleParser(BaseParser):

    name = _(u'Creole')

    def parse(self, input_data, reason):
        result = RootElement()
        stack = [result]
        for kind, data, pos in creole_parser.generate(input_data):
            if kind == START:
                tag, attrs = data
                # tt is deprecated but creoleparser is using it
                if tag == 'tt':
                    tag = 'code'
                element = Element(tag)
                for key, value in attrs:
                    element.attributes[key] = value
                stack[-1].children.append(element)
                stack.append(element)
            elif kind == END:
                stack.pop()
            elif kind == TEXT:
                if stack[-1].children:
                    stack[-1].children[-1].tail += data
                else:
                    stack[-1].text += data
        return result


def setup(app, plugin):
    app.add_parser('creole', CreoleParser)
