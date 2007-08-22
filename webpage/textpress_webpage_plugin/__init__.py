# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage_plugin
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The central plugin for the textpress webpage.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os.path import join, dirname
from textpress.plugins.textpress_webpage_plugin import pluginrepo

THEME_TEMPLATES = join(dirname(__file__), 'templates')
PLUGIN_TEMPLATES = join(dirname(__file__), 'plugin_templates')
SHARED_FILES = join(dirname(__file__), 'shared')


def setup(app, plugin):
    # Theme
    app.add_theme('textpress_webpage', THEME_TEMPLATES, {
        'name':         'TextPress Webpage Design',
        'description':  'the Theme used on textpress.pocoo.org. This is not '
                        'a regular theme, it uses hardcoded strings and is '
                        'english only.',
        'preview':      'textpress_webpage_plugin::theme_preview.png'
    })
    app.add_shared_exports('textpress_webpage_plugin', SHARED_FILES)

    # Plugin Repository
    app.add_url_rule('/plugins/', endpoint='textpress_webpage_plugin/plugin_index')
    app.add_view('textpress_webpage_plugin/plugin_index', pluginrepo.do_index)

    # Requirements
    app.add_template_searchpath(PLUGIN_TEMPLATES)
