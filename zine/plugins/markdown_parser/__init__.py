# -*- coding: utf-8 -*-
"""
    zine.plugins.markdown_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blog posts.

    TODO: this parser does not support `<intro>` sections and has a
          very bad implementation as it requires multiple parsing steps.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from zine.api import *
from zine.parsers import BaseParser
from zine.utils.zeml import parse_html
try:
    import markdown as md
except ImportError:
    from zine.plugins.markdown_parser import local_markdown as md


class MarkdownParser(BaseParser):
    """A simple markdown parser."""

    name = _(u'Markdown')

    def parse(self, input_data, reason):
        parser = md.Markdown(safe_mode=reason == 'comment' and 'escape',
                             extensions=['codehilite'],
                             extension_configs={'codehilite':
                                                    {'css_class': 'syntax'}})
        return parse_html(parser.convert(input_data))


def setup(app, plugin):
    app.add_parser('markdown', MarkdownParser)
