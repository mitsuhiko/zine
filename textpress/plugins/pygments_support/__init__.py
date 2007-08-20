# -*- coding: utf-8 -*-
"""
    textpress.plugins.pygments_support
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for pygments to pre code blocks.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname
from werkzeug.utils import escape
from textpress.api import *
from textpress.utils import CSRFProtector
from textpress.views.admin import render_admin_response, flash
from textpress.htmlprocessor import DataNode
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    from pygments.styles import get_all_styles
    have_pygments = True
except ImportError:
    have_pygments = False


_formatters = {}


TEMPLATES = join(dirname(__file__), 'templates')
EXAMPLE = '''\
<!DOCTYPE HTML>
<html>
  <head>
    <title>{% block title %}Untitled{% endblock %}</title>
    <style type="text/css">
      body {
        background-color: #333;
        color: #eee;
      }
    </style>
    <script type="text/javascript">
      function fun() {
        alert('This is a piece of example code');
      }
    </script>
  </head>
  <body onload="fun()">
    {% block body %}{% endblock %}
  </body>
</html>\
'''


def get_current_style():
    return get_application().cfg['pygments_support/style']


def get_formatter(style=None, preview=False):
    if style is None:
        style = get_current_style()
    if not preview and style in _formatters:
        return _formatters[style]
    try:
        if preview:
            cls = 'highlight_preview'
        else:
            cls = 'syntax'
        formatter = HtmlFormatter(style=style, cssclass=cls)
    except ValueError:
        return None
    if not preview:
        _formatters[style] = formatter
    return formatter


def process_doc_tree(doctree, input_data, reason):
    for node in doctree.query('pre[@syntax]'):
        try:
            lexer = get_lexer_by_name(node.attributes.pop('syntax'))
        except ValueError:
            return
        output = highlight(node.text, lexer, get_formatter())
        node.parent.children.replace(node, DataNode(output))


def get_style(req, style):
    formatter = get_formatter(style)
    if formatter is None:
        abort(404)
    return Response(formatter.get_style_defs('div.syntax pre'),
                    mimetype='text/css')


def show_config(req):
    if not have_pygments:
        return render_admin_response('admin/pygments_support.html',
                                     'options.pygments_support',
            pygments_installed=False
        )

    csrf_protector = CSRFProtector()
    all_styles = set(get_all_styles())
    active_style = req.form.get('style')
    if not active_style or active_style not in all_styles:
        active_style = get_current_style()

    if req.form.get('apply'):
        csrf_protector.assert_safe()
        req.app.cfg['pygments_support/style'] = active_style
        flash(_('Pygments theme changed successfully.'), 'configure')
        redirect(url_for('pygments_support/config'))

    preview_formatter = get_formatter(active_style, preview=True)
    add_header_snippet('<style type="text/css">\n%s\n</style>' %
                       escape(preview_formatter.get_style_defs()))

    return render_admin_response('admin/pygments_support.html',
                                 'options.pygments_support',
        styles=[{
            'name':         style,
            'active':       style == active_style
        } for style in sorted(all_styles)],
        example=highlight(EXAMPLE, get_lexer_by_name('html+jinja'),
                          preview_formatter),
        csrf_protector=csrf_protector,
        pygments_installed=True
    )


def inject_style(req):
    add_link('stylesheet', url_for('pygments_support/style',
                                   style=get_current_style()),
             'text/css')


def add_pygments_link(navigation_bar):
    for link_id, url, title, children in navigation_bar:
        if link_id == 'options':
            children.insert(-2, ('pygments_support',
                                 url_for('pygments_support/config'),
                                 'Pygments'))


def setup(app, plugin):
    app.connect_event('modify-admin-navigation-bar', add_pygments_link)
    app.add_url_rule('/admin/options/pygments',
                     endpoint='pygments_support/config')
    app.add_view('pygments_support/config', show_config)
    app.add_template_searchpath(TEMPLATES)

    if have_pygments:
        app.connect_event('process-doc-tree', process_doc_tree)
        app.connect_event('after-request-setup', inject_style)
        app.add_config_var('pygments_support/style', unicode, u'default')
        app.add_url_rule('/_shared/pygments_support/<style>.css',
                         endpoint='pygments_support/style')
        app.add_view('pygments_support/style', get_style)
