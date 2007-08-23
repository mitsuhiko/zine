# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The central plugin for the textpress webpage.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os.path import join, dirname
from textpress.api import *
from textpress.plugins.textpress_webpage.database import upgrade_database
from textpress.plugins.textpress_webpage import pluginrepo, developers


THEME_TEMPLATES = join(dirname(__file__), 'theme_templates')
PLUGIN_TEMPLATES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')


def do_download(req):
    return render_response('textpress_webpage/download.html')


def setup(app, plugin):
    # Theme
    app.add_theme('textpress_webpage', THEME_TEMPLATES, {
        'name':         'TextPress Webpage Design',
        'description':  'the Theme used on textpress.pocoo.org. This is not '
                        'a regular theme, it uses hardcoded strings and is '
                        'english only.',
        'preview':      'textpress_webpage::theme_preview.png'
    })
    app.add_shared_exports('textpress_webpage', SHARED_FILES)

    # Download Textpres
    app.add_url_rule('/download', endpoint='textpress_webpage/download')
    app.add_view('textpress_webpage/download', do_download)

    # Plugin Repository
    app.add_url_rule('/plugins/',
                     endpoint='textpress_webpage/plugin_index')
    app.add_view('textpress_webpage/plugin_index', pluginrepo.do_index)
    app.add_url_rule('/plugins/<name>',
                     endpoint='textpress_webpage/show_plugin')
    app.add_view('textpress_webpage/show_plugin', pluginrepo.do_show_plugin)

    # Developers
    app.add_url_rule('/developers/register',
                     endpoint='textpress_webpage/register_developer')
    app.add_view('textpress_webpage/register_developer', developers.do_register)
    app.add_url_rule('/developers/upload_plugin',
                     endpoint='textpress_webpage/upload_plugin')
    app.add_view('textpress_webpage/upload_plugin', pluginrepo.do_upload)

    # Requirements
    app.add_template_searchpath(PLUGIN_TEMPLATES)
    app.add_database_integrity_check(upgrade_database)

    # Configuration Stuff
    app.add_config_var('textpress_webpage/plugin_folder', unicode,
                       'uploaded_plugins')
    app.add_config_var('textpress_webpage/plugin_url', unicode,
                       'http://textpress.pocoo.org/download/')
