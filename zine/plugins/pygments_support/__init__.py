# -*- coding: utf-8 -*-
"""
    zine.plugins.pygments_support
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for pygments to pre code blocks.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os.path import join, dirname
from time import time, asctime, gmtime

from werkzeug import escape
from werkzeug.exceptions import NotFound

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    from pygments.styles import get_all_styles, get_style_by_name
    have_pygments = True
except ImportError:
    have_pygments = False

from zine.api import *
from zine.views.admin import render_admin_response, flash
from zine.privileges import BLOG_ADMIN
from zine.utils import forms
from zine.utils.zeml import HTMLElement, ElementHandler
from zine.utils.http import redirect_to


#: cache for formatters
_formatters = {}

#: dict of styles
STYLES = dict((x, None) for x in get_all_styles())


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


class SourcecodeHandler(ElementHandler):
    """Provides a ``<sourcecode>`` tag."""
    tag = 'sourcecode'
    is_isolated = True
    is_block_level = True

    def process(self, element):
        lexer_name = element.attributes.get('syntax', 'text')
        try:
            lexer = get_lexer_by_name(lexer_name)
        except ValueError:
            lexer = get_lexer_by_name('text')
        return HTMLElement(highlight(element.text, lexer, get_formatter()))


class ConfigurationForm(forms.Form):
    style = forms.ChoiceField(required=True)


def get_current_style():
    """Helper function that returns the current style for the current
    application.
    """
    return get_application().cfg['pygments_support/style']


def lookup_style(name):
    """Return the style object for the given name."""
    rv = STYLES.get(name, 'default')
    if rv is None:
        return get_style_by_name(name)
    return rv


def add_style(name, style):
    """Register a new style for pygments."""
    STYLES[name] = style


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
        style_cls = lookup_style(style)
        formatter = HtmlFormatter(style=lookup_style(style),
                                  cssclass=cls)
    except ValueError:
        return None
    if not preview:
        _formatters[style] = formatter
    return formatter


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


@require_privilege(BLOG_ADMIN)
def show_config(req):
    """Request handler that provides an admin page with the configuration
    for the pygments plugin. So far this only allows changing the style.
    """
    active_style = get_current_style()
    styles = sorted([(x, x.title()) for x in STYLES])
    form = ConfigurationForm(initial=dict(style=active_style))
    form.fields['style'].choices = styles

    if req.method == 'POST' and form.validate(req.form):
        active_style = form['style']
        if 'apply' in req.form:
            req.app.cfg.change_single('pygments_support/style',
                                      active_style)
            flash(_('Pygments theme changed successfully.'), 'configure')
            return redirect_to('pygments_support/config')

    preview_formatter = get_formatter(active_style, preview=True)
    add_header_snippet('<style type="text/css">\n%s\n</style>' %
                       escape(preview_formatter.get_style_defs()))
    example = highlight(EXAMPLE, get_lexer_by_name('html+jinja'),
                        preview_formatter)

    return render_admin_response('admin/pygments_support.html',
                                 'options.pygments_support',
                                 example=example, form=form.as_widget())


def inject_style(req):
    """Add a link for the current pygments stylesheet to each page."""
    add_link('stylesheet', url_for('pygments_support/style',
                                   style=get_current_style()),
             'text/css')


def add_pygments_link(req, navigation_bar):
    """Add a link for the pygments configuration page to the admin panel."""
    if req.user.has_privilege(BLOG_ADMIN):
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(-3, ('pygments_support',
                                     url_for('pygments_support/config'),
                                     'Pygments'))


def setup(app, plugin):
    if not have_pygments:
        raise SetupError('The pygments plugin requires the pygments library '
                         'to be installed.')
    app.connect_event('modify-admin-navigation-bar', add_pygments_link)
    app.connect_event('after-request-setup', inject_style)
    app.add_config_var('pygments_support/style',
                       forms.TextField(default=u'default'))
    app.add_zeml_element_handler(SourcecodeHandler)
    app.add_url_rule('/options/pygments', prefix='admin',
                     view=show_config, endpoint='pygments_support/config')
    app.add_url_rule('/_shared/pygments_support/<style>.css',
                     view=get_style, endpoint='pygments_support/style')
    app.add_template_searchpath(TEMPLATES)
