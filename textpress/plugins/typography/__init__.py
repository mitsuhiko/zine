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
from textpress.api import *


_ignored_nodes = set(['pre', 'code'])

_rules = [
    (re.compile(r'(?:^|\s)(\')(?u)'), 'single_opening_quote', u'‘'),
    (re.compile(r'\S(\')(?u)'), 'single_closing_quote', u'’'),
    (re.compile(r'(?:^|\s)(")(?u)'), 'double_opening_quote', u'“'),
    (re.compile(r'\S(")(?u)'), 'double_closing_quote', u'”'),
    (re.compile(r'(?<!\.)\.\.\.(?!\.)'), 'ellipsis', u'…'),
    (re.compile(r'(?<!-)---(?!-)'), 'emdash', u'—'),
    (re.compile(r'(?<!-)--(?!-)'), 'endash', u'–')
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
        return all[:m.start(1) - offset] + used_signs[sign] + all[m.end(1) - offset:]

    cfg = get_application().cfg
    used_signs = dict((k, cfg['typography/' + k]) for _, k, _ in _rules)
    for node in doctree.query('#'):
        if node.parent and node.parent.name not in _ignored_nodes:
            for regex, sign, _ in _rules:
                node.value = regex.sub(handle_match, node.value)


def setup(app, plugin):
    app.connect_event('process-doc-tree', process_doc_tree)
    for _, name, default in _rules:
        app.add_config_var('typography/' + name, unicode, default)
