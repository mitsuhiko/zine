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
import os.path
import re
from zine.api import *
from zine.parsers import BaseParser
from zine.views.admin import flash, render_admin_response
from zine.privileges import BLOG_ADMIN, require_privilege
from zine.utils.zeml import parse_html
from zine.utils import forms
try:
    import markdown as md
except ImportError:
    from zine.plugins.markdown_parser import local_markdown as md

TEMPLATES = os.path.join(os.path.dirname(__file__), 'templates')
CFG_EXTENSIONS='markdown_parser/extensions'
CFG_MAKEINTRO='markdown_parser/makeintro'
MORE_TAG = re.compile(r'\n<!--\s*more\s*-->\n(?u)')


class ConfigurationForm(forms.Form):
    """Markdown configuration form."""
    extensions = forms.LineSeparated(forms.TextField(),
                                                    _(u'Enabled Extensions'))
    makeintro = forms.BooleanField(_(u'Make Intro Section'),
        help_text=_(u'Place &lt;!--more--&gt; on a line by itself with blank '\
                    u'lines above and below to cut the post at that point.'))


@require_privilege(BLOG_ADMIN)
def show_markdown_config(req):
    """Show Markdown Parser configuration options."""
    form = ConfigurationForm(initial=dict(
                                    extensions=req.app.cfg[CFG_EXTENSIONS],
                                    makeintro=req.app.cfg[CFG_MAKEINTRO]))

    if req.method == 'POST' and form.validate(req.form):
        if form.has_changed:
            cfg = req.app.cfg.edit()
            cfg[CFG_EXTENSIONS] = form['extensions']
            cfg[CFG_MAKEINTRO] = form['makeintro']
            cfg.commit()
            flash(_('Markdown Parser settings saved.'), 'ok')
    return render_admin_response('admin/markdown_options.html',
                                 'options.markdown',
                                 form=form.as_widget())


def add_config_link(req, navigation_bar):
    """Add a link to the Markdown options page"""
    if req.user.has_privilege(BLOG_ADMIN):
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(2, ('markdown',
                                    url_for('markdown_parser/config'),
                                    _('Markdown')))


class MarkdownParser(BaseParser):
    """A simple markdown parser."""

    name = _(u'Markdown')

    def parse(self, input_data, reason):
        cfg = get_application().cfg
        parser = md.Markdown(safe_mode=reason == 'comment' and 'escape',
                             extensions=cfg[CFG_EXTENSIONS],
                             #: For compatibility with the Pygments plugin
                             extension_configs={'codehilite':
                                                    {'css_class': 'syntax'}})
        html = parser.convert(input_data)
        if cfg[CFG_MAKEINTRO]:
            if MORE_TAG.search(html):
                #: Crude hack, but parse_html will correct any html
                #: closure errors we introduce
                html = u'<intro>' + MORE_TAG.sub(u'</intro>', html, 1)
        return parse_html(html)


def setup(app, plugin):
    app.add_parser('markdown', MarkdownParser)
    app.add_config_var(CFG_EXTENSIONS,
                       forms.LineSeparated(forms.TextField(), default=[]))
    app.add_config_var(CFG_MAKEINTRO, forms.BooleanField(default=False))
    app.connect_event('modify-admin-navigation-bar', add_config_link)
    app.add_url_rule('/options/markdown', prefix='admin',
                     endpoint='markdown_parser/config',
                     view=show_markdown_config)
    app.add_template_searchpath(TEMPLATES)
