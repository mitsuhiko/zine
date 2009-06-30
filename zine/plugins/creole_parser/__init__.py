# -*- coding: utf-8 -*-
"""
    zine.plugins.creole_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blog posts.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from urlparse import urljoin

from genshi.core import END, START, TEXT, QName, Attrs, Stream
from genshi.builder import tag

from creoleparser import create_dialect, creole11_base, Parser, parse_args
from creoleparser.elements import BlockElement

from werkzeug import url_quote

from zine.api import *
from zine.parsers import BaseParser
from zine.utils.zeml import RootElement, Element, MarkupErrorElement


macros_set_up = False
macros = {}

macro_result = QName('http://zine.pocoo.org/#creolehack}macro-result')
MACRO_SIGNAL = object()


def path_func(page_name):
    root = get_request().script_root
    if not root.endswith('/'):
        root += '/'
    return urljoin(root, url_quote(page_name))


def intro_tag(body):
    contents = creole_parser.generate(body)
    return tag.intro(contents).generate()


def wrap(tree):
    """Returns a faked genshi stream with the tree wrapped."""
    return Stream([(MACRO_SIGNAL, tree, (1, 0, None))])


def make_macro(extension):
    """Creates a creole macro from a markup extension."""
    def macro(body, args, kwargs, is_block, environ):
        if extension.is_void and body:
            return wrap(MarkupErrorElement(
                _(u'Macro "%s" without body got body') % extension.name))
        body = body or u''
        if not extension.is_isolated:
            arg = CreoleParser().parse(body, environ['reason'])
        else:
            arg = body
        if extension.argument_attribute and args:
            kwargs[extension.argument_attribute] = u' '.join(args)
        return wrap(extension.process(kwargs, arg))
    return macro


def macro_func(macro_name, arg_string, body, is_block, environ):
    """Looks up an extension as babel macro.  The first time the macros
    are looked up the extensions are converted into macros.
    """
    global macros_set_up
    pos, kw = parse_args(arg_string)
    if macro_name == 'intro' and body:
        return intro_tag(body)
    if not macros_set_up:
        app = get_application()
        for extension in app.markup_extensions:
            macros[extension.name] = make_macro(extension)
        macros_set_up = True
    if macro_name in macros:
        return macros[macro_name](body, pos, kw, is_block, environ)


zinecreole = create_dialect(creole11_base, wiki_links_base_url=u'',
                            wiki_links_path_func=path_func,
                            wiki_links_space_char=u'_',
                            no_wiki_monospace=True,
                            macro_func=macro_func)

creole_parser = Parser(dialect=zinecreole())


class CreoleParser(BaseParser):
    """Creole wiki markup parser.

    >>> p = CreoleParser(app=None)
    >>> p.parse(u'Hello **there**', 'entry').to_html()
    u'<p>Hello <strong>there</strong></p>\\n'
    >>> p.parse(u'<<intro>>\\nHello //again//\\n<</intro>>\\n '
    ... u'that was the __intro__.', 'entry').to_html()
    u'<intro><p>Hello <em>again</em></p>\\n</intro><p> that was the <u>intro</u>.</p>\\n'
    """

    name = _(u'Creole')

    def parse(self, input_data, reason):
        result = RootElement()
        stack = [result]
        env = {'parser': self, 'reason': reason}
        for kind, data, pos in creole_parser.generate(input_data, environ=env):
            if kind is MACRO_SIGNAL:
                stack[-1].children.append(data)
            elif kind == START:
                tag, attrs = data
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
