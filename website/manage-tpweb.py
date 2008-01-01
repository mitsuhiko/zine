#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Manage TextPress Website
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Simple management script for database updates.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
from werkzeug import script


def make_app():
    from tpweb import application, configure
    configure(
        database_uri='sqlite:////tmp/tpweb.db'
    )
    return application

action_shell = script.make_shell(lambda: {'app': make_app()})
action_runserver = script.make_runserver(make_app, use_reloader=True)

def action_initdb():
    """Initialize the database tables."""
    from tpweb import init_database
    make_app()
    init_database()

def action_planet_add(name='', url='', feed_url=''):
    """Add a new blog to the planet."""
    make_app()
    if not name or not url or not feed_url:
        print 'Error: name, url and feed_url required.'
    else:
        from tpweb.planet import Blog, session
        Blog(name, url, feed_url)
        session.commit()

def action_planet_sync():
    """Sync the planet."""
    from tpweb.planet import sync
    make_app()
    sync()


if __name__ == '__main__':
    script.run()
