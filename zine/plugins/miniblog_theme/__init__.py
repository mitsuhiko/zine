# -*- coding: utf-8 -*-
"""
    zine.plugins.miniblog_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Very simple zine theme.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from os.path import join, dirname

TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')

THEME_SETTINGS = {
    # small pagination
    'pagination.simple':            True,
    'pagination.prev_link':         True,
    'pagination.next_link':         True,
    'pagination.active':            u'· <strong>%(page)d</strong> ·',

    # and ultra short date formats
    'date.datetime_format.default': 'short',
    'date.date_format.default':     'short'
}

def setup(app, plugin):
    app.add_theme('miniblog', TEMPLATE_FILES, plugin.metadata, THEME_SETTINGS)
    app.add_shared_exports('miniblog_theme', SHARED_FILES)
