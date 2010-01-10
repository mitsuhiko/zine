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
from zine.utils.zeml import Element, sanitize
from zine.plugins.rst_parser.translator import ZemlTranslator

from docutils import nodes, utils
from docutils.core import publish_string
from docutils.writers import Writer
from docutils.parsers.rst import roles, directives, Directive


class zeml(nodes.Element):
    """Docutils node to insert a raw ZEML tree."""


class intro(nodes.Element):
    """Docutils node to insert an intro section."""


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
            content = '\n'.join(self.content)
            reason = self.state.document.settings.parsing_reason
            if not extension.is_isolated:
                content_tmp = RstParser(app).parse(content, reason)
                content = Element('div')
                content.children = content_tmp.children
                for child in content.children:
                    child.parent = content
            element = extension.process(self.options, content, reason)
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


class IntroDirective(Directive):
    required_arguments = 0
    optional_arguments = 0
    has_content = True

    def run(self):
        node = intro()
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


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
            directives.register_directive('intro', IntroDirective)
            for extension in self.app.markup_extensions:
                if extension.is_block_level:
                    directives.register_directive(
                        extension.name,
                        make_extension_directive(self.app, extension))
                else:
                    roles.register_local_role(
                        extension.name, make_extension_role(extension))
            RstParser.extensions_registered = True
        settings_overrides = {
            'file_insertion_enabled': False,
            'parsing_reason': reason,
        }
        rv = publish_string(source=input_data, writer=ZemlWriter(),
                            settings_overrides=settings_overrides)
        if reason == 'comment':
            rv = sanitize(rv)
        return rv


def setup(app, plugin):
    app.add_parser('rst', RstParser)
