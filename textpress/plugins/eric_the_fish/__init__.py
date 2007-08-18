# -*- coding: utf-8 -*-
"""
    textpress.plugins.eric_the_fish
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Annoying fish for the admin panel.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from subprocess import Popen, PIPE
from os.path import dirname, join
from textpress.api import *

SHARED_FILES = join(dirname(__file__), 'shared')

def inject_fish(req, context):
    add_script(url_for('eric_the_fish/shared', filename='fish.js'))
    add_link('stylesheet', url_for('eric_the_fish/shared',
                                   filename='fish.css'), 'text/css')

def get_quote(req):
    error = False
    try:
        fortune = Popen(['fortune', '-s'], stdout=PIPE, close_fds=True)
    except (IOError, OSError):
        error = True
    else:
        quote = fortune.stdout.read().strip()
        if fortune.wait() != 0:
            error = True
    if error:
        quote = None
    return {'error': error, 'quote': quote}

def setup(app, plugin):
    app.connect_event('before-admin-response-rendered', inject_fish)
    app.add_shared_exports('eric_the_fish', SHARED_FILES)
    app.add_servicepoint('eric_the_fish/get_quote', get_quote)
