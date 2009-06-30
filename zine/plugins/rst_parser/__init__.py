# -*- coding: utf-8 -*-
"""
    zine.plugins.rst_parser
    ~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for reStructuredText in posts.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from zine.i18n import lazy_gettext
from zine.parsers import BaseParser
from zine.utils.zeml import Element
from zine.plugins.rst_parser.translator import ZemlTranslator

from docutils import nodes
from docutils.core import publish_string
from docutils.writers import Writer
from docutils.parsers.rst import directives, Directive


def make_extension_directive(extension):
    class ExtDirective(Directive):
        required_arguments = 0
        optional_arguments = 0
        final_argument_whitespace = True
        option_spec = {}
        has_content = True
        def run(self):
            inner = Element(extension.tag)
            inner.text = ''.join(self.content)
            element = extension.process(inner)
            html = element.to_html()
            return [nodes.raw(html, html, format='html')]
    return ExtDirective


class ZemlWriter(Writer):
    """Writer to convert a docutils nodetree to a ZEML nodetree."""

    supported = ('zeml',)
    output = None

    def translate(self):
        visitor = ZemlTranslator(self.document)
        self.document.walkabout(visitor)
        self.output = visitor.root


class RstParser(BaseParser):
    """A parser for reStructuredText."""

    name = lazy_gettext('reStructuredText')
    extensions_registered = False

    def parse(self, input_data, reason):
        if not RstParser.extensions_registered:
            for extension in self.app.markup_extensions:
                directives.register_directive(
                    extension.tag, make_extension_directive(extension))
            RstParser.extensions_registered = True
        return publish_string(source=input_data, writer=ZemlWriter())


def setup(app, plugin):
    app.add_parser('rst', RstParser)
