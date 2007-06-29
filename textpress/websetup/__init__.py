# -*- coding: utf-8 -*-
"""
    textpress.websetup
    ~~~~~~~~~~~~~~~~~~

    This module installs textpress automatically if the app is not ready.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from os import path

from werkzeug.wrappers import BaseRequest
from werkzeug.utils import SharedDataMiddleware
from jinja import Environment, FileSystemLoader


# setup an isolated template environment for the websetup.
template_path = path.join(path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path))


class Request(BaseRequest):
    """simple request object that works even if the app is not installed."""
    charset = 'utf-8'


def render_template(start_response, template_name, **context):
    tmpl = jinja_env.get_template(template_name)
    data = tmpl.render(context)
    start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
    yield data.encode('utf-8')


class WebSetup(object):
    """Minimal WSGI application for installing textpress"""

    def __init__(self, app):
        self.app = app

    def setup_done(self, req, start_response):
        """Display the success message."""
        # for non CLI mode recreate the application
        if not req.environ['wsgi.run_once']:
            self.app._reinit()
        return render_template(start_response, 'finished.html')

    def do_setup(self, req, start_response):
        """Do the application setup."""
        tmpl = jinja_env.get_template('setup.html')
        data = tmpl.render()

        error = None
        severe = False
        database_uri = req.form.get('database_uri')
        if database_uri:
            try:
                self.app.connect_to_database(database_uri, perform_test=True)
            except Exception, e:
                error = str(e)
            else:
                try:
                    self.app.perform_database_upgrade()
                    self.app.set_database_uri(database_uri)
                except Exception, e:
                    error = str(e)
                    severe = True
                else:
                    return self.setup_done(req, start_response)

        return render_template(start_response, 'setup.html', error=error,
                               database_uri=database_uri, severe=severe)

    def __call__(self, environ, start_response):
        req = Request(environ)

        # for persistent setups we might still have the web setup
        # as dispatcher. In that case tell the user to reload the server
        if self.app.get_database_uri() is not None:
            return self.setup_done(req, start_response)
        return self.do_setup(req, start_response)


def make_setup(app):
    """Create a new setup application instance."""
    app = WebSetup(app)
    app = SharedDataMiddleware(app, {
        '/shared':  path.join(path.dirname(__file__), 'shared')
    })
    return app
