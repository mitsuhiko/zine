# -*- coding: utf-8 -*-
"""
    textpress.plugins.miniblog_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Very simple textpress theme.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname

TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')

def setup(app, plugin):
    app.add_theme('miniblog', TEMPLATE_FILES, plugin.metadata)
    app.add_shared_exports('miniblog_theme', SHARED_FILES)