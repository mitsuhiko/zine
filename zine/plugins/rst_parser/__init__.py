# -*- coding: utf-8 -*-
"""
    zine.plugins.rst_parser
    ~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for reStructuredText in posts.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
#from os.path import join, dirname
#from time import time, asctime, gmtime

#from werkzeug import escape
#from werkzeug.exceptions import NotFound

#from zine.api import *
#from zine.views.admin import render_admin_response, flash
#from zine.privileges import BLOG_ADMIN
#from zine.utils import forms
#from zine.utils.zeml import HTMLElement, ElementHandler
#from zine.utils.http import redirect_to

from zine.i18n import lazy_gettext
from zine.parsers import BaseParser
from zine.utils.zeml import RootElement, Element, HTMLElement, DynamicElement

from docutils.core import publish_string
from docutils.nodes import NodeVisitor
from docutils.writers import Writer

class ZemlTranslator(NodeVisitor):
    def __init__(self, document):
        NodeVisitor.__init__(self, document)
        self.root = RootElement()

    def unknown_visit(self, node):
        return
    def unknown_departure(self, node):
        return


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

    def parse(self, input_data, reason):
        return publish_string(source=input_data, writer=ZemlWriter())


def setup(app, plugin):
    app.add_parser('rst', RstParser)
