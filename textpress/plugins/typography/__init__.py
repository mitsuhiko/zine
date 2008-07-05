# -*- coding: utf-8 -*-
"""
    textpress.plugins.typography
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This plugin adds automatic typography support to TextPress.  This probably
    only works with English or German texts, maybe some other languages too.
    I don't think that it's necessary to localize that plugin some more, there
    are ways to tweak it a bit, but if one wants to have that functionality for
    other languages a different plugin is a better idea.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re
from os.path import dirname, join
from textpress.api import *
from textpress.models import ROLE_ADMIN
from textpress.views.admin import require_role, render_admin_response, \
     flash
from textpress.utils.xxx import CSRFProtector


TEMPLATES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')

_ignored_nodes = set(['pre', 'code'])
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


def process_doc_tree(doctree, input_data, reason):
    """
    Parse time callback function that replaces all pre blocks with a
    'syntax' attribute the highlighted sourcecode.
    """
    def handle_match(m):
        all = m.group()
        if not m.groups():
            return used_signs[sign]
        offset = m.start()
        return all[:m.start(1) - offset] + \
               used_signs[sign] + \
               all[m.end(1) - offset:]

    cfg = get_application().cfg
    used_signs = dict((k, cfg['typography/' + k]) for ignore, k, ignore in _rules)
    for node in doctree.query('#'):
        handle_typography = node.parent and \
                            node.parent.attributes.pop('typography', None)
        if handle_typography is None:
            handle_typography = node.parent.name not in _ignored_nodes
        else:
            handle_typography = handle_typography.lower() == 'true'
        if handle_typography:
            for regex, sign, ignore in _rules:
                node.value = regex.sub(handle_match, node.value)


def add_config_link(req, navigation_bar):
    """Add a link to the typography options page"""
    if req.user.role >= ROLE_ADMIN:
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(2, ('typography',
                                    url_for('typography/config'),
                                    _('Typography')))


def show_config(req):
    add_script(url_for('typography/shared', filename='script.js'))
    add_link('stylesheet', url_for('typography/shared',
                                   filename='style.css'), 'text/css')
    form = dict((k, req.app.cfg['typography/' + k])
                for ignore, k, ignore in _rules)
    csrf_protector = CSRFProtector()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        altered = False
        for ignore, key, ignore in _rules:
            value = req.form.get(key)
            if value:
                if req.app.change_single('typography/' + key, value):
                    altered = True
                else:
                    flash(_('Typography settings could not be changed.'), 'error')
        if altered:
            flash(_('Typography settings changed.'), 'configure')
        return redirect(url_for('typography/config'))
    return render_admin_response('admin/typography.html',
                                 'options.typography',
        form=form,
        csrf_protector=csrf_protector
    )


def setup(app, plugin):
    app.connect_event('process-doc-tree', process_doc_tree)
    app.connect_event('modify-admin-navigation-bar', add_config_link)
    app.add_url_rule('/options/typography', prefix='admin',
                     endpoint='typography/config')
    app.add_view('typography/config', show_config)
    app.add_template_searchpath(TEMPLATES)
    app.add_shared_exports('typography', SHARED_FILES)
    for ignore, name, default in _rules:
        app.add_config_var('typography/' + name, unicode, default)
