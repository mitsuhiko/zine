# -*- coding: utf-8 -*-
"""
    zine.websetup
    ~~~~~~~~~~~~~

    This module installs Zine automatically if the app is not ready.
    Because the whole Zine infrastructure is not available during the
    setup this module brings it's own basic framework.

    Please also keep in mind that he CSS files are inlined because the very
    last request could not send any more requests to external files. Those
    would already be returned by the normal Zine installation.

    :copyright: 2007-2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import sys
from os import path
from zine import environment
from zine.config import Configuration
from zine.api import db
from zine.config import ConfigurationTransactionError
from zine.models import User
from zine.utils.crypto import gen_pwhash, gen_secret_key, new_iid
from zine.utils.validators import is_valid_email, check
from zine.i18n import load_translations, has_language, list_languages
from werkzeug import Request, Response, redirect
from jinja2 import Environment, FileSystemLoader


template_path = path.join(path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path),
                        extensions=['jinja2.ext.i18n'])
jinja_env.install_null_translations()


#: header for the config file
CONFIG_HEADER = '''\
# Zine configuration file
# This file is also updated by the Zine admin interface.
# The charset of this file must be utf-8!

'''


def render_response(request, template_name, context):
    context.update(
        gettext=request.translations.gettext,
        ngettext=request.translations.ngettext,
        lang=request.translations.language
    )
    tmpl = jinja_env.get_template(template_name)
    return Response(tmpl.render(context), mimetype='text/html')


class WebSetup(object):
    """Minimal WSGI application for installing zine"""

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
                                if not k.startswith('_')),
            'languages':   list_languages(self_translated=True)
        })
        return render_response(request, name + '.html', ctx)

    def test_instance_folder(self, request):
        """Check if the instance folder exists."""
        _ = request.translations.gettext
        if not path.exists(self.instance_folder):
            folder = self.instance_folder
            if not isinstance(folder, unicode):
                folder = folder.decode(sys.getfilesystemencoding() or 'utf-8',
                                       'ignore')
            return {'error': _(u'Instance folder does not exist.  You have to '
                    u'create the folder “%s” before proceeding.') % folder}

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
        _ = request.translations.gettext
        errors = []
        if not request.values.get('admin_username'):
            errors.append(_('You have to provide a username.'))
        email = request.values.get('admin_email')
        if not email:
            errors.append(_('You have to enter a mail address.'))
        elif not check(is_valid_email, email):
            errors.append(_('The mail address is not valid.'))
        password = request.values.get('admin_password')
        if not password:
            errors.append(_('You have to enter a password.'))
        if password != request.values.get('admin_password2'):
            errors.append(_('The two passwords do not match.'))
        if errors:
            return {'error': errors[0]}

    def start_setup(self, request):
        """
        This is called when all the form data is validated
        and Zine is ready to install the data. In theory
        this can also be called if no form validation is done and
        someone faked the request. But because that's the fault of
        the administrator we don't care about that.
        """
        value = request.values.get
        error = None
        database_uri = value('database_uri', '').strip()

        try:
            from zine.database import init_database

            # create database and all tables
            e = db.create_engine(database_uri, self.instance_folder)
            init_database(e)
        except Exception, error:
            error = str(error).decode('utf-8', 'ignore')
        else:
            from zine.database import users, user_privileges, privileges
            from zine.privileges import BLOG_ADMIN

            # create admin account
            user_id = e.execute(users.insert(),
                username=value('admin_username'),
                pw_hash=gen_pwhash(value('admin_password')),
                email=value('admin_email'),
                real_name=u'',
                description=u'',
                extra={},
                display_name='$username',
                is_author=True
            ).last_inserted_ids()[0]

            # insert a privilege for the user
            privilege_id = e.execute(privileges.insert(),
                name=BLOG_ADMIN.name
            ).last_inserted_ids()[0]
            e.execute(user_privileges.insert(),
                user_id=user_id,
                privilege_id=privilege_id
            )

            # set up the initial config
            config_filename = path.join(self.instance_folder, 'zine.ini')
            cfg = Configuration(config_filename)
            t = cfg.edit()
            t.update(
                maintenance_mode=environment.MODE != 'development',
                blog_url=request.url_root,
                secret_key=gen_secret_key(),
                database_uri=database_uri,
                language=request.translations.language,
                iid=new_iid(),
                # load one plugin by default for a better theme
                plugins='vessel_theme',
                theme='vessel'
            )
            cfg._comments['[zine]'] = CONFIG_HEADER
            try:
                t.commit()
            except ConfigurationTransactionError:
                _ = request.translations.gettext
                error = _('The configuration file (%s) could not be opened '
                          'for writing. Please adjust your permissions and '
                          'try again.') % config_filename

        # use a local variable, the global render_response could
        # be None because we reloaded zine and this module.
        return render_response(request, error and 'error.html' or 'finished.html', {
            'finished': True,
            'error':    error
        })

    def __call__(self, environ, start_response):
        request = Request(environ)
        lang = request.values.get('_lang')
        if lang is None:
            lang = (request.accept_languages.best or 'en').split('-')[0].lower()
        if not has_language(lang):
            lang = 'en'
        request.translations = load_translations(lang)
        request.translations.language = lang
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
