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

from docutils import nodes, utils
from docutils.core import publish_string
from docutils.writers import Writer
from docutils.parsers.rst import directives, Directive


class zeml(nodes.Element):
    """Docutils node to insert a raw ZEML tree."""


def make_extension_directive(app, extension):
    class ExtDirective(Directive):
        required_arguments = 0
        optional_arguments = 0
        final_argument_whitespace = True
        option_spec = {}
        has_content = True
        def run(self):
            if self.arguments:
                self.options[extension.argument_attribute] = self.arguments[0]
            content = ''.join(self.content)
            if not extension.is_isolated:
                content = RstParser(app).parse(content, 'nested')
            root_element = extension.process(self.options, content)
            element = Element('div')
            element.children = root_element.children
            for child in element.children:
                child.parent = element
            return [zeml(zeml=element)]
    for attrname in extension.attributes:
        ExtDirective.option_spec[attrname] = directives.unchanged
    if extension.argument_attribute in extension.attributes:
        ExtDirective.optional_arguments = 1
    if extension.is_void:
        ExtDirective.has_content = False
    # give it a nice non-generic name
    ExtDirective.__name__ = '%s_directive' % extension.name
    return ExtDirective


def make_extension_role(extension):
    def role(typ, rawtext, text, lineno, inliner, options={}, content=[]):
        if not extension.is_isolated:
            content = Element('span')
            content.text = utils.unescape(text)
        else:
            content = utils.unescape(text)
        element = extension.process({}, content)
        return [zeml(zeml=element)], []
    role.__name__ = '%s_role' % extension.name
    return role


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
            # need to do this only once...
            for extension in self.app.markup_extensions:
                if extension.is_block_level:
                    directives.register_directive(
                        extension.name, make_extension_directive(self.app, extension))
                else:
                    roles.register_local_role(
                        extension.name, make_extension_role(extension))
            RstParser.extensions_registered = True
        return publish_string(source=input_data, writer=ZemlWriter())


def setup(app, plugin):
    app.add_parser('rst', RstParser)
