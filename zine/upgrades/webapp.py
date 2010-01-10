# -*- coding: utf-8 -*-
"""
    zine.upgrades.webapp
    ~~~~~~~~~~~~~~~~~~~~

    This package implements a simple web application that will be responsible
    for upgrading Zine to the latest schema changes.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from os import remove
from os.path import isfile
from time import time
from sqlalchemy.sql import and_
from zine.database import db, privileges, users, user_privileges
from zine.i18n import load_core_translations
from zine.upgrades import ManageDatabase
from zine.utils.crypto import check_pwhash
from werkzeug.utils import redirect
from werkzeug.contrib.securecookie import SecureCookie
from werkzeug.wrappers import Response, Request

def render_template(tmpl, _stream=False, **context):
    if _stream:
        return tmpl.stream(context)
    return tmpl.render(context)

def render_response(request, template_name, **context):
    context.update(gettext=request.translations.gettext,
                   ngettext=request.translations.ngettext)
    tmpl = request.app.template_env.get_template(template_name)
    return Response(render_template(tmpl, **context), mimetype='text/html')


class WebUpgrades(object):
    upgrade_required = wants_reload = False
    def __init__(self, app):
        self.app = app
        self.database_engine = app.database_engine
        self.lockfile = app.upgrade_lockfile
        self.blog_url = app.url_adapter.build('blog/index')
        self.login_url = app.url_adapter.build('account/login')
        self.maintenance_url = app.url_adapter.build('admin/maintenance')

    def __getattr__(self, name):
        if not hasattr(self, name):
            return getattr(self.app, name)
        return getattr(self, name)

    def get_request(self, environ):
        request = Request(environ)
        request.app = self.app
        request.translations = load_core_translations(self.app.cfg['language'])
        request.is_admin = False
        request.is_somebody = False

        cookie_name = self.app.cfg['session_cookie_name']
        session = SecureCookie.load_cookie(
            request, cookie_name, self.app.cfg['secret_key'].encode('utf-8')
        )
        request.session = session
        engine = self.app.database_engine
        user_id = session.get('uid')

        if user_id:
            admin_privilege = engine.execute(
                privileges.select(privileges.c.name=='BLOG_ADMIN')
            ).fetchone()

            admin = engine.execute(user_privileges.select(and_(
                user_privileges.c.user_id==int(user_id),
                user_privileges.c.privilege_id==admin_privilege.privilege_id
            ))).fetchone()
            request.is_somebody = True
            request.is_admin = admin is not None
        return request

    def dispatch(self, request):
        if request.path not in ('/', self.login_url):
            return redirect('')

        if request.path == self.login_url:
            if request.is_somebody:
                return redirect('')
            elif request.authorization:
                if 'username' in request.authorization:
                    username = request.authorization.get('username')
                    password = request.authorization.get('password')
                    user = self.app.database_engine.execute(
                        users.select(users.c.username==username)
                    ).fetchone()
                    if user and check_pwhash(user.pw_hash, password):
                        request.session['uid'] = user.user_id
                        request.session['lt'] = time()
                        request.is_somebody = True
                        return redirect('')

            response = Response()
            response.www_authenticate.set_basic()
            response.status_code = 401
            return response

        if not request.is_admin:
            response = render_response(request, 'upgrade_maintenance.html',
                                       login_url=self.login_url)
            response.status_code = 503
            return response

        if request.method == 'POST':
            open(self.lockfile, 'w').write('locked on database upgrade\n')
            mdb = ManageDatabase(request.app)
            db.session.close()  # Close open sessions
            def finish():
                # this runs after the upgrade finishes
                remove(self.lockfile)
                db.session.close()  # Close open sessions
                self.wants_reload = True    # Force application reload
                return ''   # just because I need to return something to jinja

            return render_response(request, 'admin/perform_upgrade.html',
                                   live_log=mdb.cmd_upgrade(), _stream=True,
                                   finish=finish, blog_url=self.blog_url,
                                   maintenance_url=self.maintenance_url,
                                   in_progress=False)

        return render_response(request, 'admin/perform_upgrade.html',
                               in_progress=isfile(self.lockfile))

    def __call__(self, environ, start_response):
        request = self.get_request(environ)
        response = self.dispatch(request)
        if request.session.should_save:
            cookie_name = self.app.cfg['session_cookie_name']
            request.session.save_cookie(response, cookie_name, max_age=None,
                                        expires=None, session_expires=None)
        return response(environ, start_response)

