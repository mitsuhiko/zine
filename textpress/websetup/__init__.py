# -*- coding: utf-8 -*-
"""
    textpress.websetup
    ~~~~~~~~~~~~~~~~~~

    This module installs textpress automatically if the app is not ready.
    Because the whole TextPress infrastructure is not available during the
    setup this module brings it's own basic framework.

    Please also keep in mind that he CSS files are inlined because the very
    last request could not send any more requests to external files. Those
    would already be returned by the normal TextPress installation.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import db
from textpress.models import User, ROLE_ADMIN
from textpress.utils import is_valid_email, gen_pwhash, reload_textpress, \
     get_blog_url
from textpress.websetup.framework import render_response, redirect, Request


class WebSetup(object):
    """Minimal WSGI application for installing textpress"""

    def __init__(self, app):
        self.app = app
        views = [
            ('start', None),
            ('database', self.test_database),
            ('admin_account', self.test_admin_account),
            ('summary', None)
        ]

        self.prev = {}
        self.next = {}
        self.views = {}
        for idx, (view, handler) in enumerate(views):
            self.views[view] = handler
            if idx:
                prev = views[idx - 1][0]
            else:
                prev = None
            if idx < len(views) - 1:
                next = views[idx + 1][0]
            else:
                next = None
            self.prev[view] = prev
            self.next[view] = next

    def handle_view(self, req, name, ctx=None):
        handler = self.views[name]
        ctx = ctx or {}
        ctx.update({
            'current':          name,
            'prev':             self.prev[name],
            'next':             self.next[name],
            'values':           dict((k, v) for k, v in req.values.items()
                                     if not k.startswith('_'))
        })
        return render_response(name + '.html', ctx)

    def test_database(self, req):
        """Check if the database uri is valid."""
        database_uri = req.values.get('database_uri')
        error = None
        if not database_uri:
            error = 'You have to provide a database URI.'
        else:
            try:
                db.create_engine(database_uri)
            except Exception, e:
                error = str(e)
        if error is not None:
            return {'error': error}

    def test_admin_account(self, req):
        """Check if the admin mail is valid and the passwords match."""
        errors = []
        if not req.values.get('admin_username'):
            errors.append('You have to provide a username.')
        email = req.values.get('admin_email')
        if not email:
            errors.append('You have to enter a mail address.')
        elif not is_valid_email(email):
            errors.append('The mail address is not valid.')
        password = req.values.get('admin_password')
        if not password:
            errors.append('You have to enter a password.')
        if password != req.values.get('admin_password2'):
            errors.append('The two passwords do not match.')
        if errors:
            return {'errors': errors}

    def start_setup(self, req):
        """
        This is called when all the form data is validated
        and TextPress is ready to install the data. In theory
        this can also be called if no form validation is done and
        someone faked the request. But because that's the fault of
        the administrator we don't care about that.
        """
        value = req.values.get
        error = None
        database_uri = value('database_uri', '').strip()

        try:
            from textpress.database import init_database

            # create database and all tables
            e = db.create_engine(database_uri)
            init_database(e)
        except Exception, e:
            error = str(e)
        else:
            # if there was no error so far we store the database uri
            self.app.set_database_uri(database_uri)

            from textpress.models import ROLE_ADMIN
            from textpress.database import users, configuration

            # create admin account
            e.execute(users.insert(),
                username=value('admin_username'),
                pw_hash=gen_pwhash(value('admin_password')),
                email=value('admin_email'),
                first_name='',
                last_name='',
                description='',
                extra={},
                display_name='$nick',
                role=ROLE_ADMIN
            )

            # enter maintenance mode
            e.execute(configuration.insert(),
                key='maintenance_mode',
                value='True'
            )

            # and set the blog url
            e.execute(configuration.insert(),
                key='blog_url',
                value=get_blog_url(req)
            )

            # because we don't have the request bound to this
            # thread we have to check for cgi environments
            # ourselves.
            if not req.environ['wsgi.run_once']:
                reload_textpress()

        # use a local variable, the global render_response could
        # be None because we reloaded textpress and this module.
        from textpress.websetup.framework import render_response
        return render_response(error and 'error.html' or 'finished.html', {
            'finished': True
        })

    def __call__(self, environ, start_response):
        self.app.bind_to_thread()
        req = Request(environ)
        resp = None

        if req.path == '/':
            view = req.values.get('_current', 'start')
            if req.values.get('_startsetup'):
                resp = self.start_setup(req)
            elif view in self.views:
                handler = self.views[view]
                if handler is not None and \
                   req.values.get('_next'):
                    ctx = handler(req)
                    if ctx is not None:
                        resp = self.handle_view(req, view, ctx)

                if resp is None:
                    if req.values.get('_next'):
                        view = self.next[view]
                    elif req.values.get('_prev'):
                        view = self.prev[view]
                    resp = self.handle_view(req, view)

        if resp is None:
            resp = redirect(environ, '/')
        return resp(environ, start_response)


def make_setup(app):
    """Create a new setup application instance."""
    return WebSetup(app)
