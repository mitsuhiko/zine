# -*- coding: utf-8 -*-
"""
    textpress.plugins.pygments_support
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for pygments to pre code blocks.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.htmlprocessor import DataNode
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    have_pygments = True
except ImportError:
    have_pygments = False


class PygmentsHighlighter(object):

    def __init__(self, style):
        self.formatter = HtmlFormatter(style=style)

    def process_doc_tree(self, event):
        for node in event.data['doctree'].query('pre[@tp:lang]'):
            lexer = get_lexer_by_name(node.attributes.pop('tp:lang'))
            output = highlight(node.text, lexer, self.formatter)
            node.parent.children.replace(node, DataNode(output))

    def get_style(self, req):
        return Response(self.formatter.get_style_defs(), mimetype='text/css')

    def inject_style(self, event):
        add_link('stylesheet', url_for('pygments_support/style'), 'text/css')


def setup(app, plugin):
    if not have_pygments:
        return
    app.add_config_var('pygments_support/style', unicode, u'default')
    app.add_url_rule('/_shared/pygments_support/style.css',
                     endpoint='pygments_support/style')

    c = PygmentsHighlighter(app.cfg['pygments_support/style'])
    app.connect_event('process-doc-tree', c.process_doc_tree)
    app.connect_event('after-request-setup', c.inject_style)
    app.add_view('pygments_support/style', c.get_style)
