# -*- coding: utf-8 -*-
"""
    zine.parsers
    ~~~~~~~~~~~~

    This module holds the base parser informations and the dict of
    default parsers.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import escape

from zine.i18n import lazy_gettext
from zine.application import iter_listeners, get_application
from zine.utils.zeml import parse_html, parse_zeml, sanitize, split_intro, \
     Element, RootElement
from zine.utils.xml import replace_entities


def parse(input_data, parser=None, reason='unknown'):
    """Generate a doc tree out of the data provided.  If we are not in unbound
    mode the `process-doc-tree` event is sent so that plugins can modify
    the tree in place. The reason is useful for plugins to find out if they
    want to render it or now. For example a normal blog post would have the
    reason 'post', a comment 'comment', an isolated page from a plugin maybe
    'page' etc.
    """
    input_data = u'\n'.join(input_data.splitlines())
    app = get_application()
    if parser is None:
        try:
            parser = app.parsers[app.cfg['default_parser']]
        except KeyError:
            # the plugin that provided the default parser is not
            # longer available.  reset the config value to the builtin
            # parser and parse afterwards.
            t = app.cfg.edit()
            t.revert_to_default('default_parser')
            t.commit()
            parser = app.parsers[app.cfg['default_parser']]
    else:
        try:
            parser = app.parsers[parser]
        except KeyError:
            raise ValueError('parser %r does not exist' % (parser,))

    tree = parser.parse(input_data, reason)

    #! allow plugins to alter the doctree.
    for callback in iter_listeners('process-doc-tree'):
        item = callback(tree, input_data, reason)
        if item is not None:
            tree = item

    return tree


def render_preview(text, parser, component='post'):
    """Renders a preview text for the given text using the parser
    provided.
    """
    tree = parse(text, parser, '%s-preview' % component)
    intro, body = split_intro(tree)
    if intro:
        return u'<div class="intro">%s</div>%s' % (intro.to_html(),
                                                   body.to_html())
    return body.to_html()


class MarkupExtension(object):
    """Handler for a markup language-agnostic markup extension.

    The following attributes must/can be set on subclasses:

        `name`
            The name under which the extension is accessible. This is the tag
            name for XML-like markup languages, or the directive name for
            reStructuredText (reST), etc.
        `is_block_level`
            True if the element is to be rendered as a block-level element.
            This may also change how the element is accessed; for example, in
            reST, inline elements are used as roles, while block-level elements
            are used as directives.
        `is_void`
            True if the element doesn't have content.
        `is_isolated`
            True if the element's contents should not be parsed by the markup
            parser and converted to a ZEML tree.
        `broken_by`
            A sequence of element names by which this element is implicitly
            closed.  Applies only to XML-like markup languages.
        `attributes`
            A set of allowed attribute (option) names.  Note that inline elements
            may not support attributes in all markup languages.
        `argument_attribute`
            For markup languages that support arguments to elements as well
            as attributes, if this is the name of an attribute given in
            `attributes`, the element will accept one argument and map it
            to the given attribute.  Note that inline elements may not support
            arguments in all markup languages.

    The `process` method must be overwritten.  Is given three arguments:

        `attributes`
            A dictionary of attributes (options) of the markup element.
        `content`
            The content of the element; if `is_isolated` is True, this has
            already been parsed with the markup parser and is a ZEML tree,
            otherwise it is raw text.
        `reason`
            The parsing reason -- either "post", "comment", "post-preview",
            "comment-preview", or "system".  The element can change behavior
            depending on the reason, for example disable potentially unsafe
            features for comments.

    It must return a ZEML tree.
    """

    name = None
    is_void = False
    is_isolated = False
    is_block_level = True
    broken_by = None
    attributes = set()
    argument_attribute = None

    def __init__(self, app):
        self.app = app

    def process(self, attributes, content, reason):
        """Called each time the element is encountered."""
        raise NotImplementedError


class BaseParser(object):
    """Baseclass for all kinds of parsers."""

    #: the localized name of the parser.
    name = None

    def __init__(self, app):
        self.app = app

    def parse(self, input_data, reason):
        """Return a ZEML tree."""


class ZEMLParser(BaseParser):
    """The parser for the ZEML Markup language."""

    name = lazy_gettext('Zine-Markup')

    def parse(self, input_data, reason):
        rv = parse_zeml(input_data, reason, self.app.markup_extensions)
        if reason == 'comment':
            rv = sanitize(rv)
        return rv


class HTMLParser(BaseParser):
    """A parser that understands plain old HTML."""

    name = lazy_gettext('HTML')

    def parse(self, input_data, reason):
        rv = parse_html(input_data)
        if reason == 'comment':
            rv = sanitize(rv)
        return rv


class PlainTextParser(BaseParser):
    """Parses simple text into a ZEML tree by utilizing pottymouth."""

    name = lazy_gettext('Text')

    def _to_text(self, token):
        """Convert a token to normal text."""
        return replace_entities(unicode(token))

    def _to_zeml(self, node):
        """Convert a potty-mouth node into a ZEML tree."""
        from zine._ext.pottymouth import Token
        def add_text(node, text):
            if node.children:
                node.children[-1].tail += text
            else:
                node.text += text

        def convert(node, is_root):
            if is_root:
                result = RootElement()
            else:
                result = Element(node.name)
            if node._attributes:
                result.attributes.update(node._attributes)

            for item in node:
                if isinstance(item, (str, unicode, Token)):
                    add_text(result, self._to_text(item))
                else:
                    child = convert(item, False)
                    # remove the useless empty spans
                    if child.name == 'span' and not child.attributes:
                        add_text(result, child.text)
                        result.children.extend(child.children)
                        add_text(result, child.tail)
                    else:
                        result.children.append(child)

            # fixes an output bug from pottymouth
            if len(result.children) == 1 and node.name == 'p' and \
               result.children[0].name == 'blockquote':
                result = result.children[0]

            return result
        return convert(node, True)

    def parse(self, input_data, reason):
        from zine._ext.pottymouth import PottyMouth
        parser = PottyMouth(emdash=False, ellipsis=False, smart_quotes=False,
                            youtube=False, image=False, italic=False)
        node = parser.parse(input_data)
        return self._to_zeml(node)


all_parsers = {
    'zeml':             ZEMLParser,
    'html':             HTMLParser,
    'text':             PlainTextParser
}
