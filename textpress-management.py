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
        print 'actions: shell | serve | eventmap'
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

    elif action == 'eventmap':
        from textpress.utils import build_eventmap
        print '=' * 80
        print 'EVENT MAP'.center(80)
        print '=' * 80
        sys.stdout.write('Building eventmap...')
        sys.stdout.flush()
        map_ = build_eventmap(app)
        sys.stdout.write('\r')
        for event, places in map_.iteritems():
            print '`%s`' % event
            for location, filename, lineno in places:
                print '    %-46s%10s%20s' % (filename, lineno, location)

    else:
        print 'Error: Unknown action %s' % action
        return 3


if __name__ == '__main__':
    sys.exit(main(sys.argv))
