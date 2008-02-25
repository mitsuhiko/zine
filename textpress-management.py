#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    TextPress Management
    ~~~~~~~~~~~~~~~~~~~~

    This script starts a server or a shell for a textpress
    instance. Useful for plugin development and debugging.

    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: GNU GPL.
"""
import os
import sys
from werkzeug import script
from werkzeug.contrib import profiler

INSTANCE_FOLDER = os.environ.get('TEXTPRESS_INSTANCE')
if not INSTANCE_FOLDER:
    INSTANCE_FOLDER = os.path.join(os.path.dirname(__file__), 'instance')


def make_app():
    from textpress import make_app
    return make_app(INSTANCE_FOLDER)

def make_shell():
    from textpress import make_textpress
    app = make_textpress(INSTANCE_FOLDER, True)
    from textpress import models
    from textpress.database import db
    del make_textpress
    return locals()

def action_deployplugin(plugin_path='', output_path='./'):
    """Deploys a plugin"""

    USAGE = """\
usage: %(script)s deployplugin [options]

examples:
    %(script)s deployplugin /path/to/plugin/foo
    %(script)s deployplugin /path/to/plugin/foo /path/to/output/dir
    %(script)s deployplugin --plugin-path=/path/to/plugin/foo
    %(script)s deployplugin --plugin-path=/path/to/plugin/foo --output-dir=/path/to/output/dir
""" % {'script': sys.argv[0]}

    from textpress import make_textpress
    app = make_textpress(INSTANCE_FOLDER, True)

    if not plugin_path:
        print "Please pass the plugin directory path"
        print USAGE
        sys.exit(1)

    plugin_name = [p for p in plugin_path.split(os.sep) if p][-1]
    try:
        plugin = app.plugins[plugin_name]
    except KeyError:
        print "Plugin '%s' not known" % plugin_name
        print USAGE
        sys.exit(1)

    if output_path != './':
        if not os.path.exists(output_path):
            print "Output directory '%s' does not exist" % output_path
            print USAGE
            sys.exit(1)
        elif not os.access(output_path, os.R_OK|os.W_OK|os.X_OK):
            print "cannot write to '%s'" % output_path
            print USAGE
            sys.exit(1)
    plugin = app.plugins[plugin_name]
    output_plugin_name = '%s-%s.plugin' % (
        ''.join(plugin.display_name.split()),
        plugin.version
    )
    plugin.dump(os.path.join(output_path, output_plugin_name))
    print "Created '%s' in '%s'" % (output_plugin_name, output_path)


action_runserver = script.make_runserver(make_app, use_reloader=True,
                                         port=4000, use_debugger=True)
action_profile = profiler.make_action(make_app, port=4000)
action_shell = script.make_shell(make_shell)

if __name__ == '__main__':
    script.run()
