# -*- coding: utf-8 -*-
"""
    zine.plugins.myrtle_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    The current default theme for Zine.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname

TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')
THEME_SETTINGS = {
    'pagination.right_threshold':   1,
    'pagination.left_threshold':    1,
    'pagination.threshold':         2,
    'pagination.next_link':         True,
    'pagination.prev_link':         True,
    'pagination.commata':           u'<span class="commata"> ·\n</span>'
}

def setup(app, plugin):
    app.add_theme('myrtle', TEMPLATE_FILES, plugin.metadata, THEME_SETTINGS)
    app.add_shared_exports('myrtle_theme', SHARED_FILES)
