# -*- coding: utf-8 -*-
"""
    zine.plugins.creole_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blg posts.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from urlparse import urljoin

from creoleparser import create_dialect, creole11_base, Parser, parse_args
from creoleparser.elements import BlockElement
from genshi.core import END, START, TEXT
import genshi.builder
from werkzeug import url_quote

from zine.api import *
from zine.parsers import BaseParser
from zine.utils.zeml import RootElement, Element


def path_func(page_name):
    root = get_request().script_root
    if not root.endswith('/'):
        root += '/'
    return urljoin(root, url_quote(page_name))


def intro_tag(body, *pos, **kw):
    contents = creole_parser.generate(body)
    return genshi.builder.tag.intro(contents).generate()


def macro_func(macro_name, arg_string, body, isblock, environ):
    pos, kw = parse_args(arg_string)
    if macro_name == 'intro' and isblock and body:
        return intro_tag(body, *pos, **kw)


zinecreole = create_dialect(creole11_base, wiki_links_base_url=u'',
                                     wiki_links_path_func=path_func,
                                     wiki_links_space_char=u'_',
                                     no_wiki_monospace=True,
                                     macro_func=macro_func)

creole_parser = Parser(dialect=zinecreole())


class CreoleParser(BaseParser):
    """
    Creole wiki markup parser.

    >>> p = CreoleParser(app=None)
    >>> p.parse(u'Hello **there**', 'entry').to_html()
    u'<p>Hello <strong>there</strong></p>\\n'
    >>> p.parse(u'<<intro>>\\nHello //again//\\n<</intro>>\\n that was the __intro__.', 'entry').to_html()
    u'<intro><p>Hello <em>again</em></p>\\n</intro><p> that was the <u>intro</u>.</p>\\n'
    """

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
