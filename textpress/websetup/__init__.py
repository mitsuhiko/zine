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
import sys
from os import path
from textpress.config import Configuration
from textpress.api import db
from textpress.models import User, ROLE_ADMIN
from textpress.utils.crypto import gen_pwhash, gen_secret_key
from textpress.utils.validators import is_valid_email
from textpress.i18n import _
from werkzeug import Request, Response, redirect
from jinja2 import Environment, FileSystemLoader


template_path = path.join(path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path))


def render_response(template_name, context):
    tmpl = jinja_env.get_template(template_name)
    return Response(tmpl.render(context), mimetype='text/html')


class WebSetup(object):
    """Minimal WSGI application for installing textpress"""

    def __init__(self, instance_folder):
        self.instance_folder = instance_folder
        views = [
            ('start', self.test_instance_folder),
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

    def handle_view(self, request, name, ctx=None):
        handler = self.views[name]
        ctx = ctx or {}
        ctx.update({
            'current':     name,
            'prev':        self.prev[name],
            'next':        self.next[name],
            'values':      dict((k, v) for k, v in request.values.iteritems()
                                if not k.startswith('_'))
        })
        return render_response(name + '.html', ctx)

    def test_instance_folder(self, request):
        """Check if the instance folder exists."""
        if not path.exists(self.instance_folder):
            folder = self.instance_folder
            if not isinstance(folder, unicode):
                folder = folder.decode(sys.getfilesystemencoding() or 'utf-8',
                                       'ignore')
            return {'error': u'Instance folder does not exist.  You have to '
                    u'create the folder “%s” before proceeding.' % folder}

    def test_database(self, request):
        """Check if the database uri is valid."""
        database_uri = request.values.get('database_uri')
        error = None
        if not database_uri:
            error = 'You have to provide a database URI.'
        else:
            try:
                db.create_engine(database_uri, self.instance_folder)
            except Exception, e:
                error = str(e)
        if error is not None:
            return {'error': error}

    def test_admin_account(self, request):
        """Check if the admin mail is valid and the passwords match."""
        errors = []
        if not request.values.get('admin_username'):
            errors.append('You have to provide a username.')
        email = request.values.get('admin_email')
        if not email:
            errors.append('You have to enter a mail address.')
        elif not is_valid_email(email):
            errors.append('The mail address is not valid.')
        password = request.values.get('admin_password')
        if not password:
            errors.append('You have to enter a password.')
        if password != request.values.get('admin_password2'):
            errors.append('The two passwords do not match.')
        if errors:
            return {'errors': errors}

    def start_setup(self, request):
        """
        This is called when all the form data is validated
        and TextPress is ready to install the data. In theory
        this can also be called if no form validation is done and
        someone faked the request. But because that's the fault of
        the administrator we don't care about that.
        """
        value = request.values.get
        error = None
        database_uri = value('database_uri', '').strip()

        try:
            from textpress.database import init_database

            # create database and all tables
            e = db.create_engine(database_uri, self.instance_folder)
            init_database(e)
        except Exception, e:
            error = str(e)
        else:
            from textpress.models import ROLE_ADMIN
            from textpress.database import users

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

            # set up the initial config
            config_filename = path.join(self.instance_folder, 'textpress.ini')
            cfg = Configuration(config_filename)
            t = cfg.edit()
            t.update(
                maintenance_mode=True,
                blog_url=request.url_root,
                secret_key=gen_secret_key(),
                database_uri=database_uri
            )
            try:
                t.commit()
            except IOError:
                error = _('The configuration file (%s) could not be opened '
                          'for writing. Please adjust your permissions and '
                          'try again.') % config_filename

        # use a local variable, the global render_response could
        # be None because we reloaded textpress and this module.
        return render_response(error and 'error.html' or 'finished.html', {
            'finished': True,
            'error':    error
        })

    def __call__(self, environ, start_response):
        request = Request(environ)
        response = None

        if request.path == '/':
            view = request.values.get('_current', 'start')
            if request.values.get('_startsetup'):
                response = self.start_setup(request)
            elif view in self.views:
                handler = self.views[view]
                if handler is not None and \
                   request.values.get('_next'):
                    ctx = handler(request)
                    if ctx is not None:
                        response = self.handle_view(request, view, ctx)

                if response is None:
                    if request.values.get('_next'):
                        view = self.next[view]
                    elif request.values.get('_prev'):
                        view = self.prev[view]
                    response = self.handle_view(request, view)

        if response is None:
            response = redirect('/')
        return response(environ, start_response)


def make_setup(app):
    """Create a new setup application instance."""
    return WebSetup(app)
