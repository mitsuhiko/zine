# -*- coding: utf-8 -*-
"""
    textpress.plugins.markdown_parser
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Use Markdown for your blog posts.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.parsers import BaseParser
from textpress.parsers.simplehtml import HTMLParser
from textpress.plugins.markdown_parser import markdown as md


class MarkdownParser(BaseParser):

    get_name = staticmethod(lambda: u'Markdown')

    def parse(self, input_data, reason):
        parser = md.Markdown(safe_mode=reason == 'comment')
        html_parser = HTMLParser()
        return html_parser.parse(parser.convert(input_data), None)


def setup(app, plugin):
    app.add_parser('markdown', MarkdownParser)
