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
from werkzeug.utils import SharedDataMiddleware, get_current_url
from jinja import Environment, FileSystemLoader

from textpress.api import db
from textpress.models import User, ROLE_ADMIN
from textpress.utils import gen_password, is_valid_email


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

    def setup_done(self, req, start_response, admin_username, admin_password):
        """Display the success message."""
        return render_template(start_response, 'finished.html',
            admin=dict(username=admin_username, password=admin_password),
            admin_url=self.app.cfg['blog_url'].rstrip('/') + '/admin/')

    def calculate_blog_url(self, req):
        """Return the URL to the blog."""
        return get_current_url(req.environ, root_only=True)

    def do_setup(self, req, start_response):
        """Do the application setup."""
        tmpl = jinja_env.get_template('setup.html')
        data = tmpl.render()

        email_error = None
        db_error = None
        severe = False
        database_uri = req.form.get('database_uri')
        email = req.form.get('admin_email')
        if req.method == 'POST':
            if not is_valid_email(email):
                email_error = 'You have to provide a valid email address.'
            try:
                self.app.connect_to_database(database_uri, perform_test=True)
            except Exception, e:
                db_error = str(e)
            else:
                if not email_error:
                    try:
                        self.app.perform_database_upgrade()
                        self.app.set_database_uri(database_uri)
                        self.app.cfg['blog_url'] = self.calculate_blog_url(req)
                        password = gen_password()
                        self.app._reinit()
                        admin = User('admin', password, email,
                                     role=ROLE_ADMIN)
                        admin.save()
                        db.flush()
                    except Exception, e:
                        db_error = str(e)
                        severe = True
                    else:
                        return self.setup_done(req, start_response, 'admin',
                                               password)

        return render_template(start_response, 'setup.html',
                               db_error=db_error, email_error=email_error,
                               database_uri=database_uri, severe=severe,
                               admin_email=email)

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
