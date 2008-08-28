# -*- coding: utf-8 -*-
"""
    zine.plugins.markdown_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blog posts.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from zine.api import *
from zine.parsers import BaseParser
from zine.parsers.simplehtml import HTMLParser
from zine.plugins.markdown_parser import markdown as md


class MarkdownParser(BaseParser):

    get_name = staticmethod(lambda: u'Markdown')

    def parse(self, input_data, reason):
        parser = md.Markdown(safe_mode=reason == 'comment' and 'escape')
        html_parser = HTMLParser()
        return html_parser.parse(parser.convert(input_data), None)


def setup(app, plugin):
    app.add_parser('markdown', MarkdownParser)
