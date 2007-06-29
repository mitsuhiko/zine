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
import sys
from getopt import getopt
from textpress import make_app
from werkzeug.serving import run_simple
from werkzeug.debug import DebuggedApplication


BANNER = '''\
*** TextPress Shell
    Preinitialized objects: app and all the api functions
    Have fun!\
'''


def main(argv):
    opts, args = getopt(argv[1:], 'rdh')
    opts = dict(opts)

    if len(args) != 2 or '-h' in opts:
        print 'usage: %s [-d] [-r] <instance> <action>' % sys.argv[0]
        print 'use -d for debugging'
        print 'use -r for automatic reloading'
        return 2

    instance, action = args
    if not os.path.exists(instance):
        print 'Error: instance folder does not exist'
        return 3

    app = make_app(instance)

    if action == 'serve':
        if '-d' in opts:
            app = DebuggedApplication(app, True)
        run_simple('localhost', 4000, app, '-r' in opts)
        #from paste import httpserver
        #httpserver.serve(app, 'localhost', 4000)
    elif action == 'shell':
        del sys.argv[1:]
        app.bind_to_thread()
        globals = {'app': app}
        from textpress import api
        for key in api.__all__:
            globals[key] = getattr(api, key)

        import IPython
        sh = IPython.Shell.IPShellEmbed(banner=BANNER)
        sh(global_ns=globals, local_ns={})
        return
    else:
        print 'Error: Unknown action %s' % action
        return 3


if __name__ == '__main__':
    sys.exit(main(sys.argv))
