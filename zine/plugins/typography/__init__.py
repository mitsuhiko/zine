# -*- coding: utf-8 -*-
"""
    zine.plugins.typography
    ~~~~~~~~~~~~~~~~~~~~~~~

    This plugin adds automatic typography support to Zine.  This probably
    only works with English or German texts, maybe some other languages too.
    I don't think that it's necessary to localize that plugin some more, there
    are ways to tweak it a bit, but if one wants to have that functionality for
    other languages a different plugin is a better idea.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
from os.path import dirname, join
from zine.api import *
from zine.privileges import BLOG_ADMIN
from zine.views.admin import require_privilege, render_admin_response, \
     flash
from zine.utils.http import redirect_to
from zine.utils import forms


TEMPLATES = join(dirname(__file__), 'templates')

_ignored_elements = set(['pre', 'code'])
_rules = [
    (re.compile(r'(?<!\.)\.\.\.(?!\.)'), 'ellipsis', u'…'),
    (re.compile(r'(?<!-)---(?!-)'), 'emdash', u'—'),
    (re.compile(r'(?<!-)--(?!-)'), 'endash', u'–'),
    (re.compile(r'\d(")(?u)'), 'inch', u'″'),
    (re.compile(r'\d(\')(?u)'), 'foot', u'′'),
    (re.compile(r'\+\-'), 'plus_minus_sign', u'±'),
    (re.compile(r'\(c\)'), 'copyright', u'©'),
    (re.compile(r'\(r\)'), 'registered', u'®'),
    (re.compile(r'\(tm\)'), 'trademark', u'™'),
    (re.compile(r'\d\s+(x)\s+\d(?u)'), 'multiplication_sign', u'×'),
    (re.compile(r'(?:^|\s)(\')(?u)'), 'single_opening_quote', u'‘'),
    (re.compile(r'\S(\')(?u)'), 'single_closing_quote', u'’'),
    (re.compile(r'(?:^|\s)(")(?u)'), 'double_opening_quote', u'“'),
    (re.compile(r'\S(")(?u)'), 'double_closing_quote', u'”')
]


class ConfigurationForm(forms.Form):
    """The configuration form for the quotes."""
    double_opening_quote = forms.TextField(required=True)
    double_closing_quote = forms.TextField(required=True)
    single_opening_quote = forms.TextField(required=True)
    single_closing_quote = forms.TextField(required=True)


def process_doc_tree(doctree, input_data, reason):
    """Parse time callback function that replaces all pre blocks with a
    'syntax' attribute the highlighted sourcecode.
    """
    def apply_typography(text):
        def handle_match(m):
            all = m.group()
            if not m.groups():
                return used_signs[sign]
            offset = m.start()
            return all[:m.start(1) - offset] + \
                   used_signs[sign] + \
                   all[m.end(1) - offset:]
        for regex, sign, ignore in _rules:
            text = regex.sub(handle_match, text)
        return text

    cfg = get_application().cfg
    used_signs = dict((k, cfg['typography/' + k]) for ignore, k, ignore in _rules)
    for element in doctree.walk():
        handle_typography = element.attributes.pop('typography', None)
        if handle_typography is None:
            handle_typography = element.name not in _ignored_elements
        else:
            handle_typography = handle_typography.lower() == 'true'
        if handle_typography:
            if element.text:
                element.text = apply_typography(element.text)
            for child in element.children:
                if child.tail:
                    child.tail = apply_typography(child.tail)


def add_config_link(req, navigation_bar):
    """Add a link to the typography options page"""
    if req.user.has_privilege(BLOG_ADMIN):
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(2, ('typography',
                                    url_for('typography/config'),
                                    _('Typography')))


@require_privilege(BLOG_ADMIN)
def show_config(req):
    """The configuration form."""
    form = ConfigurationForm(initial=dict((k, req.app.cfg['typography/' + k])
                                          for k in ConfigurationForm.fields))

    if req.method == 'POST' and form.validate(req.form):
        if form.has_changed:
            t = req.app.cfg.edit()
            for key, value in form.data.iteritems():
                t['typography/' + key] = value
            try:
                t.commit()
            except IOError:
                flash(_('Typography settings could not be changed.'), 'error')
            else:
                flash(_('Typography settings changed.'), 'configure')
        return redirect_to('typography/config')

    return render_admin_response('admin/typography.html',
                                 'options.typography', form=form.as_widget())


def setup(app, plugin):
    app.connect_event('process-doc-tree', process_doc_tree)
    app.connect_event('modify-admin-navigation-bar', add_config_link)
    app.add_url_rule('/options/typography', prefix='admin',
                     endpoint='typography/config')
    app.add_view('typography/config', show_config)
    app.add_template_searchpath(TEMPLATES)
    for ignore, name, default in _rules:
        app.add_config_var('typography/' + name,
                           forms.TextField(default=default))
