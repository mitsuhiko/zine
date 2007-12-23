#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    TextPress Management
    ~~~~~~~~~~~~~~~~~~~~

    This script starts a server or a shell for a textpress
    instance. Useful for plugin development and debugging.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
from werkzeug import script

INSTANCE_FOLDER = os.environ.get('TEXTPRESS_INSTNACE')
if not INSTANCE_FOLDER:
    INSTANCE_FOLDER = os.path.join(os.path.dirname(__file__), 'instance')


def make_app():
    from textpress import make_app
    #from werkzeug.contrib.profiler import ProfilerMiddleware
    #return ProfilerMiddleware(make_app(INSTANCE_FOLDER))
    return make_app(INSTANCE_FOLDER)

def make_shell():
    from textpress import make_textpress
    textpress = make_textpress(INSTANCE_FOLDER)
    from textpress import models, database
    del make_textpress
    return locals()

action_runserver = script.make_runserver(make_app, use_reloader=True,
                                         port=4000, use_debugger=True)
action_shell = script.make_shell(make_shell)

if __name__ == '__main__':
    script.run()
