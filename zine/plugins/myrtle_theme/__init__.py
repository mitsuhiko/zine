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

def setup(app, plugin):
    app.add_theme('myrtle', TEMPLATE_FILES, plugin.metadata)
    app.add_shared_exports('myrtle_theme', SHARED_FILES)
