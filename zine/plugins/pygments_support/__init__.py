# -*- coding: utf-8 -*-
"""
    zine.plugins.pygments_support
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for pygments to pre code blocks.

    :copyright: 2007-2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname
from time import time, asctime, gmtime
from zine.api import *
from zine.utils.xxx import CSRFProtector
from zine.views.admin import render_admin_response, flash
from zine.models import ROLE_ADMIN
from zine.fragment import DataNode
from werkzeug import escape
from werkzeug.exceptions import NotFound
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    from pygments.styles import get_all_styles
    have_pygments = True
except ImportError:
    have_pygments = False


_formatters = {}
_disabled_for = set(['comment'])


TEMPLATES = join(dirname(__file__), 'templates')
PYGMENTS_URL = 'http://pygments.org/'
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
    """Helper function that returns the current style for the current
    application.
    """
    return get_application().cfg['pygments_support/style']


def get_formatter(style=None, preview=False):
    """Helper function that returns a formatter in either preview or
    normal mode for the style provided or the current style if not
    further defined.

    The formatter returned should be treated as immutable object
    because it might be shared and cached.
    """
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
    """Parse time callback function that replaces all pre blocks with a
    'syntax' attribute the highlighted sourcecode.
    """
    if reason in _disabled_for:
        return
    for node in doctree.query('pre[@syntax]'):
        try:
            lexer = get_lexer_by_name(node.attributes.pop('syntax'))
        except ValueError:
            return
        output = highlight(node.text, lexer, get_formatter())
        node.parent.children.replace(node, DataNode(output))


def get_style(req, style):
    """A request handler that returns the stylesheet for one of the
    pygments styles. If a file does not exist it returns an
    error 404.
    """
    formatter = get_formatter(style)
    if formatter is None:
        raise NotFound()
    resp = Response(formatter.get_style_defs('div.syntax pre'),
                    mimetype='text/css')
    resp.headers['Cache-Control'] = 'public'
    resp.headers['Expires'] = asctime(gmtime(time() + 3600))
    return resp


@require_role(ROLE_ADMIN)
def show_config(req):
    """Request handler that provides an admin page with the configuration
    for the pygments plugin. So far this only allows changing the style.
    """
    csrf_protector = CSRFProtector()
    all_styles = set(get_all_styles())
    active_style = req.form.get('style')
    if not active_style or active_style not in all_styles:
        active_style = get_current_style()

    if req.form.get('apply'):
        csrf_protector.assert_safe()
        if req.app.cfg.change_single('pygments_support/style', active_style):
            flash(_('Pygments theme changed successfully.'), 'configure')
        else:
            flash(_('Pygments theme could not be changed.'), 'error')
        return redirect(url_for('pygments_support/config'))

    preview_formatter = get_formatter(active_style, preview=True)
    add_header_snippet('<style type="text/css">\n%s\n</style>' %
                       escape(preview_formatter.get_style_defs()))
    example = highlight(EXAMPLE, get_lexer_by_name('html+jinja'),
                        preview_formatter)

    return render_admin_response('admin/pygments_support.html',
                                 'options.pygments_support',
        styles=[{
            'name':         style,
            'active':       style == active_style
        } for style in sorted(all_styles)],
        example=example,
        csrf_protector=csrf_protector
    )


def inject_style(req):
    """Add a link for the current pygments stylesheet to each page."""
    add_link('stylesheet', url_for('pygments_support/style',
                                   style=get_current_style()),
             'text/css')


def add_pygments_link(req, navigation_bar):
    """Add a link for the pygments configuration page to the admin panel."""
    if req.user.role >= ROLE_ADMIN:
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(-3, ('pygments_support',
                                     url_for('pygments_support/config'),
                                     'Pygments'))


def setup(app, plugin):
    if not have_pygments:
        raise SetupError('The pygments plugin requires the pygments library '
                         'to be installed.')
    app.add_config_var('pygments_support/style', unicode, u'default')
    app.connect_event('modify-admin-navigation-bar', add_pygments_link)
    app.connect_event('process-doc-tree', process_doc_tree)
    app.connect_event('after-request-setup', inject_style)
    app.add_url_rule('/options/pygments', prefix='admin',
                     view=show_config, endpoint='pygments_support/config')
    app.add_url_rule('/_shared/pygments_support/<style>.css',
                     view=get_style, endpoint='pygments_support/style')
    app.add_template_searchpath(TEMPLATES)
