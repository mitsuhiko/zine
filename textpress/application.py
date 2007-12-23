# -*- coding: utf-8 -*-
"""
    textpress.application
    ~~~~~~~~~~~~~~~~~~~~~

    The main application.  This module uses some pretty weird thread local
    stuff.  Basically at least an application is bound to the current thread
    which you can get by calling `get_application`.  The same things happens
    with user requests.  This means that it's impossible to use textpress in
    enviornments where you have multiple requests in one thread (servers that
    use greenlets).

    Once there is a WSGI server that uses greenlets one could add support for
    that here.  So far this limitation is not a real world problem.


    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from os import path, remove, makedirs, walk
from time import time
from thread import allocate_lock
from itertools import izip
from datetime import datetime, timedelta
from urlparse import urlparse

from textpress.database import db, upgrade_database, cleanup_session
from textpress.config import Configuration
from textpress.utils import format_datetime, format_date, format_month, \
     ClosingIterator, check_external_url, local, local_manager

from werkzeug import BaseRequest, BaseResponse, SharedDataMiddleware, \
     url_quote, routing, redirect as simple_redirect
from werkzeug.exceptions import HTTPException, BadRequest, Forbidden, \
     NotFound
from werkzeug.contrib.securecookie import SecureCookie

from jinja import Environment
from jinja.loaders import BaseLoader, CachedLoaderMixin
from jinja.exceptions import TemplateNotFound
from jinja.datastructure import Deferred


#: path to the shared data of the core components
SHARED_DATA = path.join(path.dirname(__file__), 'shared')

#: path to the builtin templates (admin panel and page defaults)
BUILTIN_TEMPLATE_PATH = path.join(path.dirname(__file__), 'templates')

#: the lock for the application setup.
_setup_lock = allocate_lock()

#: because events are not application bound we keep them
#: unique by sharing them. For better performance we don't
#: lock the access to this variable, it's unlikely that
#: two applications connect a new event in the same millisecond
#: because connecting happens during application startup and
#: there is a global application setup lock.
_next_listener_id = 0

#: holds references to all the active textpress instances. This is
#: used by the reloader function in the utils module. Some other
#: modules might want to use this too if they want to modify application
#: independent settings and have to access application objects.
_instances = {}
_instance_lock = allocate_lock()


def get_request():
    """Get the current request."""
    return getattr(local, 'request', None)


def get_application():
    """Get the current application."""
    return getattr(local, 'application', None)


def url_for(endpoint, **args):
    """Get the url to an endpoint."""
    if hasattr(endpoint, 'get_url_values'):
        rv = endpoint.get_url_values()
        if rv is not None:
            endpoint, updated_args = rv
            args.update(updated_args)
    anchor = args.pop('_anchor', None)
    external = args.pop('_external', False)
    rv = local.request.urls.build(endpoint, args, force_external=external)
    if anchor is not None:
        rv += '#' + url_quote(anchor)
    return rv


def redirect(url, code=302, allow_external_redirect=False):
    """
    Return a redirect response.  Like Werkzeug's redirect but this
    one checks for external redirects too.
    """
    if not allow_external_redirect:
        #: check if the url is on the same server
        #: and make it an external one
        try:
            url = check_external_url(local.application, url, True)
        except ValueError:
            raise BadRequest()
    return simple_redirect(url, code)


def emit_event(event, *args, **kw):
    """Emit an event and return a `EventResult` instance."""
    buffered = kw.pop('buffered', False)
    if kw:
        raise TypeError('got invalid keyword argument %r' % iter(kw).next())
    return EventResult(local.application._event_manager.
                       emit(event, args), buffered)


def add_link(rel, href, type, title=None, charset=None, media=None):
    """Add a new link to the metadata of the current page being processed."""
    local.page_metadata.append(('link', {
        'rel':      rel,
        'href':     href,
        'type':     type,
        'title':    title,
        'charset':  charset,
        'media':    media
    }))


def add_meta(http_equiv=None, name=None, content=None):
    """Add a new meta element to the metadata of the current page."""
    local.page_metadata.append(('meta', {
        'http_equiv':   http_equiv,
        'name':         name,
        'content':      content
    }))


def add_script(src, type='text/javascript'):
    """Load a script."""
    local.page_metadata.append(('script', {
            'src':      src,
            'type':     type
        }))


def add_header_snippet(html):
    """Add some HTML as header snippet."""
    local.page_metadata.append(('snippet', {
        'html':     html
    }))


def render_template(template_name, _stream=False, **context):
    """
    Renders a template. If `_stream` is ``True`` the return value will be
    a Jinja template stream and not an unicode object.
    This is used by `render_response`.
    """
    #! called right before a template is rendered, the return value is
    #! ignored but the context can be modified in place.
    emit_event('before-render-template', template_name, _stream, context,
               buffered=True)
    tmpl = local.application.template_env.get_template(template_name)
    if _stream:
        return tmpl.stream(context)
    return tmpl.render(context)


def render_response(template_name, **context):
    """
    Like render_template but returns a response. If `_stream` is ``True``
    the response returned uses the Jinja stream processing. This is useful
    for pages with lazy generated content or huge output where you don't
    want the users to wait until the calculation ended. Use streaming only
    in those situations because it's usually slower than bunch processing.
    """
    return Response(render_template(template_name, **context))


def require_role(role):
    """Wrap a view so that it requires a given role to access."""
    def wrapped(f):
        def decorated(request, **kwargs):
            if request.user.role >= role:
                return f(request, **kwargs)
            raise Forbidden()
        decorated.__name__ = f.__name__
        decorated.__doc__ = f.__doc__
        return decorated
    return wrapped


def get_active_applications():
    """Return a set of all active applications."""
    return set(_instances.values())


def clear_application_cache():
    """
    Applications are cached for performance reasons.  If you create a bunch
    of application objects for some scripted tasks it's a good idea to clear
    the application cache afterwards.
    """
    _instances.clear()


class Request(BaseRequest):
    """The used request class."""
    charset = 'utf-8'

    def __init__(self, app, environ):
        BaseRequest.__init__(self, environ)
        self.app = app

        scheme, netloc, script_name = urlparse(app.cfg['blog_url'])[:3]
        if not (scheme and netloc and script_name):
            self.urls = app.url_map.bind_to_environ(environ)
        else:
            self.urls = app.url_map.bind(netloc, script_name,
                                         url_scheme=scheme)
        engine = self.app.database_engine

        # get the session
        from textpress.models import User
        user = None
        session = SecureCookie.load_cookie(self, app.cfg['session_cookie_name'],
                                           app.cfg['secret_key'])
        user_id = session.get('uid')
        if user_id:
            user = User.objects.get(user_id)
        if user is None:
            user = User.objects.get_nobody()

        self.user = self._old_user = user
        self.session = session

    def login(self, user):
        """Log the given user in. Can be user_id, username or
        a full blown user object."""
        from textpress.models import User
        if isinstance(user, (int, long)):
            user = User.objects.get(user)
        elif isinstance(user, basestring):
            user = User.objects.get_by(username=user)
        if user is None:
            raise RuntimeError('User does not exist')
        self.user = user
        #! called after a user was logged in successfully
        emit_event('after-user-login', user, buffered=True)
        self.session['uid'] = user.user_id

    def logout(self):
        """Log the current user out."""
        from textpress.models import User
        user = self.user
        self.user = User.objects.get_nobody()
        self.session.clear()
        #! called after a user was logged out and the session cleared.
        emit_event('after-user-logout', user, buffered=True)


class Response(BaseResponse):
    """
    An utf-8 response, with text/html as default mimetype.
    """
    charset = 'utf-8'
    default_mimetype = 'text/html'


class EventManager(object):
    """
    Helper class that handles event listeners and events.

    This is *not* a public interface. Always use the emit_event()
    functions to access it or the connect_event() / disconnect_event()
    functions on the application.
    """

    def __init__(self, app):
        self.app = app
        self._listeners = {}

    def connect(self, event, callback):
        global _next_listener_id
        listener_id = _next_listener_id
        event = intern(event)
        if event not in self._listeners:
            self._listeners[event] = {listener_id: callback}
        else:
            self._listeners[event][listener_id] = callback
        _next_listener_id += 1
        return listener_id

    def remove(self, listener_id):
        for event in self._listeners:
            event.pop(listener_id, None)

    def emit(self, name, args):
        if name in self._listeners:
            for listener_id, cb in self._listeners[name].iteritems():
                yield listener_id, cb(*args)


class EventResult(object):
    """Wraps a generator for the emit_event() function."""

    __slots__ = ('_participated_listeners', '_results', '_gen', 'buffered')

    def __init__(self, gen, buffered):
        if buffered:
            items = list(gen)
            self._participated_listeners = set(x[0] for x in items)
            self._results = [x[1] for x in items]
        else:
            self._gen = gen
        self.buffered = buffered

    @property
    def participated_listeners(self):
        if not hasattr(self, '_participated_listeners'):
            tuple(self)
        return self._participated_listeners

    @property
    def results(self):
        if not hasattr(self, '_results'):
            tuple(self)
        return self._results

    def __iter__(self):
        if self.buffered:
            for item in self.results:
                yield item
        elif not hasattr(self, '_results'):
            self._results = []
            self._participated_listeners = []
            for listener_id, result in self._gen:
                self._results.append(result)
                self._participated_listeners.append(listener_id)
                yield result

    def __repr__(self):
        if self.buffered:
            detail = '- buffered [%d participants]' % len(self.results)
        else:
            detail = '(dynamic)'
        return '<EventResult %s>' % detail


class Theme(object):
    """
    Represents a theme and is created automaticall by `add_theme`
    """

    __slots__ = ('app', 'name', 'template_path', 'metadata')

    def __init__(self, app, name, template_path, metadata=None):
        self.app = app
        self.name = name
        self.template_path = template_path
        self.metadata = metadata or {}

    @property
    def preview_url(self):
        if self.metadata.get('preview'):
            endpoint, filename = self.metadata['preview'].split('::')
            return url_for(endpoint + '/shared', filename=filename)

    @property
    def has_preview(self):
        return bool(self.metadata.get('preview'))

    @property
    def detail_name(self):
        return self.metadata.get('name') or self.name.title()

    def get_source(self, name):
        """Get the source of a template or `None`."""
        parts = [x for x in name.split('/') if not x == '..']
        for fn in self.get_searchpath():
            fn = path.join(fn, *parts)
            if path.exists(fn):
                f = file(fn)
                try:
                    return f.read().decode('utf-8')
                finally:
                    f.close()

    def get_overlay_path(self, template):
        """Return the path to an overlay for a template."""
        return path.join(self.app.instance_folder, 'overlays',
                         self.name, template)

    def overlay_exists(self, template):
        """Check if an overlay for a given template exists."""
        return path.exists(self.get_overlay_path(template))

    def get_overlay(self, template):
        """Return the source of an overlay."""
        f = file(self.get_overlay_path(template))
        try:
            lines = f.read().decode('utf-8', 'ignore').splitlines()
        finally:
            f.close()
        return u'\n'.join(lines)

    def parse_overlay(self, template):
        """Return the AST of an overlay."""
        return self.app.template_env.parse(self.get_overlay(template))

    def set_overlay(self, template, data):
        """Set an overlay."""
        filename = self.get_overlay_path(template)
        try:
            makedirs(path.dirname(filename))
        except OSError:
            pass
        data = u'\n'.join(data.splitlines())
        if not data.endswith('\n'):
            data += '\n'
        f = file(filename, 'w')
        try:
            f.write(data.encode('utf-8'))
        finally:
            f.close()

    def remove_overlay(self, template, silent=False):
        """Remove an overlay."""
        try:
            remove(self.get_overlay_path(template))
        except OSError:
            if not silent:
                raise

    def get_searchpath(self):
        """
        Get the searchpath for this theme including plugins and
        all other template locations.
        """
        # before loading the normal template paths we check for overlays
        # in the instance overlay folder
        searchpath = [path.join(self.app.instance_folder, 'overlays',
                                self.name)]

        # if we have a real theme add the template path to the searchpath
        # on the highest position
        if self.name != 'default':
            searchpath.append(self.template_path)

        # add the template locations of the plugins
        searchpath.extend(self.app._template_searchpath)

        # now after the plugin searchpaths add the builtin one
        searchpath.append(BUILTIN_TEMPLATE_PATH)

        return searchpath

    def list_templates(self):
        """Return a sorted list of all templates."""
        templates = set()
        for p in self.get_searchpath():
            for dirpath, dirnames, filenames in walk(p):
                dirpath = dirpath[len(p) + 1:]
                if dirpath.startswith('.'):
                    continue
                for filename in filenames:
                    if filename.startswith('.'):
                        continue
                    templates.add(path.join(dirpath, filename).
                                  replace(path.sep, '/'))
        return sorted(templates)


class ThemeLoader(CachedLoaderMixin, BaseLoader):
    """
    Loads the templates. First it tries to load the templates of the
    current theme, if that doesn't work it loads the templates from the
    builtin template folder (contains base layout templates and admin
    templates).
    """

    def __init__(self, app):
        self.app = app
        CachedLoaderMixin.__init__(self,
            False,      # don't use memory caching for the moment
            40,         # for up to 40 templates
            None,       # path to disk cache
            False,      # don't reload templates
            app.instance_folder
        )

    def get_source(self, environment, name, parent):
        rv = self.app.theme.get_source(name)
        if rv is None:
            raise TemplateNotFound(name)
        return rv


class InstanceNotInitialized(RuntimeError):
    """
    Raised if an application was created for a not yet initialized instance
    folder.
    """


class TextPress(object):
    """The WSGI application."""

    def __init__(self, instance_folder):
        # this check ensures that only make_app can create TextPress instances
        if get_application() is not self:
            raise TypeError('cannot create %r instances. use the '
                            'make_textpress factory function.' %
                            self.__class__.__name__)

        # create the event manager, this is the first thing we have to
        # do because it could happen that events are sent during setup
        self.initialized = None
        self._event_manager = EventManager(self)

        # copy the dispatcher over so that we can apply middlewares
        self.dispatch_request = self._dispatch_request
        self.instance_folder = path.realpath(instance_folder)

        # add a list for database checks
        self._database_checks = [upgrade_database]

        # and instanciate the configuration. this won't fail,
        # even if the database is not connected.
        self.cfg = Configuration(self)

        # connect to the database, ignore errors for now
        self.connect_to_database()

        # setup core package urls and shared stuff
        import textpress
        from textpress.api import _
        from textpress.urls import make_urls
        from textpress.views import all_views
        from textpress.services import all_services
        from textpress.parsers import all_parsers
        self.views = all_views.copy()
        self.parsers = all_parsers.copy()
        self._url_rules = make_urls(self)
        self._services = all_services.copy()
        self._shared_exports = {}
        self._template_globals = {}
        self._template_filters = {}
        self._template_searchpath = []

        default_theme = Theme(self, 'default', BUILTIN_TEMPLATE_PATH, {
            'name':         _('Default Theme'),
            'description':  _('Simple default theme that doesn\'t '
                              'contain any style information.'),
            'preview':      'core::default_preview.png'
        })
        self.themes = {'default': default_theme}
        self.apis = {}

        # insert list of widgets
        from textpress.widgets import all_widgets
        self.widgets = dict((x.NAME, x) for x in all_widgets)

        # load plugins
        from textpress.pluginsystem import find_plugins
        self.plugin_searchpath = [path.join(instance_folder, 'plugins')]
        self.plugins = {}
        for plugin in find_plugins(self):
            if plugin.active:
                plugin.setup()
            self.plugins[plugin.name] = plugin

        # check database integrity by performing the database checks
        self.perform_database_upgrade()

        # init the template system with the core stuff
        from textpress import htmlhelpers, models
        env = Environment(loader=ThemeLoader(self))
        env.globals.update(
            request=Deferred(lambda *a: get_request()),
            cfg=self.cfg,
            h=htmlhelpers,
            url_for=url_for,
            render_widgets=lambda: render_template('_widgets.html'),
            get_page_metadata=self.get_page_metadata,
            textpress={
                'version':      textpress.__version__,
                'copyright':    '2007 by the Pocoo Team'
            }
        )

        # XXX: l10n :-)
        env.filters.update(
            datetimeformat=lambda:lambda e, c, v: format_datetime(v),
            dateformat=lambda:lambda e, c, v: format_date(v),
            monthformat=lambda:lambda e, c, v: format_month(v)
        )

        # copy the widgets into the global namespace
        self._template_globals.update(self.widgets)

        # set up plugin template extensions
        env.globals.update(self._template_globals)
        env.filters.update(self._template_filters)
        del self._template_globals, self._template_filters
        self.template_env = env

        # now add the middleware for static file serving
        self.add_shared_exports('core', SHARED_DATA)
        self.add_middleware(SharedDataMiddleware, self._shared_exports)

        # set up the urls
        self.url_map = routing.Map(self._url_rules)
        del self._url_rules

        # mark the app as finished and send an event
        self.initialized = int(time())

        #! called after the application and all plugins are initialized
        emit_event('application-setup-done')

    def request_reload(self):
        f = file(path.join(self.instance_folder, 'last_reload'), 'w')
        try:
            f.write('%d\n' % time())
        finally:
            f.close()

    @property
    def wants_reload(self):
        """True if the application requests a reload."""
        reload_path = path.join(self.instance_folder, 'last_reload')
        if not path.exists(reload_path):
            return False
        f = file(reload_path, 'r')
        try:
            try:
                last_reload = int(f.read().strip())
            except ValueError:
                return False
        finally:
            f.close()
        return last_reload > self.initialized

    @property
    def theme(self):
        """Return the current theme."""
        theme = self.cfg['theme']
        if theme not in self.themes:
            self.cfg['theme'] = theme = 'default'
        return self.themes[theme]

    def bind_to_thread(self):
        """Bind the application to the current thread."""
        local.application = self

    def connect_to_database(self):
        """Connect the app to the database defined."""
        database_uri_path = path.join(self.instance_folder, 'database.uri')
        if not path.exists(database_uri_path):
            raise InstanceNotInitialized()
        f = file(database_uri_path)
        try:
            database_uri = f.read().strip()
        finally:
            f.close()
        self.database_engine = db.create_engine(database_uri,
                                                convert_unicode=True)

    def perform_database_upgrade(self):
        """Do the database upgrade."""
        for check in self._database_checks:
            check(self)

    def add_template_filter(self, name, callback):
        """Add a template filter."""
        if self.initialized is not None:
            raise RuntimeError('cannot add template filters '
                               'after application setup')
        self._template_filters[name] = callback

    def add_template_global(self, name, value, deferred=False):
        """Add a template global (or deferred factory function)."""
        if self.initialized is not None:
            raise RuntimeError('cannot add template filters '
                               'after application setup')
        if deferred:
            value = Deferred(value)
        self._template_globals[name] = value

    def add_template_searchpath(self, path):
        """Add a new template searchpath to the application.
        This searchpath is queried *after* the themes but
        *before* the builtin templates are looked up."""
        if self.initialized is not None:
            raise RuntimeError('cannot add template filters '
                               'after application setup')
        self._template_searchpath.append(path)

    def add_api(self, name, blog_id, preferred, callback):
        """Add a new API to the blog."""
        if self.initialized is not None:
            raise RuntimeError('cannot add template filters '
                               'after application setup')
        endpoint = 'services/' + name
        self.apis[name] = (blog_id, preferred, endpoint)
        self.add_url_rule('/_services/' + name, endpoint=endpoint)
        self.add_view(endpoint, callback)

    def add_theme(self, name, template_path, metadata=None):
        """
        Add a theme. You have to provide the shortname for the theme
        which will be used in the admin panel etc. Then you have to provide
        the path for the templates. Usually this path is relative to the
        `__file__` directory.

        The metadata can be ommited but in that case some information in
        the admin panel is not available.
        """
        if self.initialized is not None:
            raise RuntimeError('cannot add themes after application setup')
        self.themes[name] = Theme(self, name, template_path, metadata)

    def add_shared_exports(self, name, path):
        """
        Add a shared export for name that points to a given path and
        creates an url rule for <name>/shared that takes a filename
        parameter.
        """
        if self.initialized is not None:
            raise RuntimeError('cannot add middlewares after '
                               'application setup')
        self._shared_exports['/_shared/' + name] = path
        self.add_url_rule('/_shared/%s/<string:filename>' % name,
                          endpoint=name + '/shared', build_only=True)

    def add_middleware(self, middleware_factory, *args, **kwargs):
        """Add a middleware to the application."""
        if self.initialized is not None:
            raise RuntimeError('cannot add middlewares after '
                               'application setup')
        self.dispatch_request = middleware_factory(self.dispatch_request,
                                                   *args, **kwargs)

    def add_config_var(self, key, type, default):
        """Add a configuration variable to the application."""
        if self.initialized is not None:
            raise RuntimeError('cannot add configuration values after '
                               'application setup')
        self.cfg.config_vars[key] = (type, default)

    def add_database_integrity_check(self, callback):
        """Allows plugins to perform database upgrades."""
        if self.initialized is not None:
            raise RuntimeError('cannot add database integrity checks '
                               'after application setup')
        self._database_checks.append(callback)

    def add_url_rule(self, *args, **kwargs):
        """Add a new URL rule to the url map."""
        if self.initialized is not None:
            raise RuntimeError('cannot add url rule after application setup')
        self._url_rules.append(routing.Rule(*args, **kwargs))

    def add_view(self, endpoint, callback):
        """Add a callback as view."""
        if self.initialized is not None:
            raise RuntimeError('cannot add view after application setup')
        self.views[endpoint] = callback

    def add_parser(self, name, class_):
        """Add a new parser class."""
        if self.initialized is not None:
            raise RuntimeError('cannot add parser after application setup')
        self.parsers[name] = class_

    def list_parsers(self):
        """Return a sorted list of parsers (parser_id, parser_name)."""
        return sorted([(key, parser.get_name()) for key, parser in
                       self.parsers.iteritems()], key=lambda x: x[1].lower())

    def add_widget(self, widget):
        """Add a widget."""
        if self.initialized is not None:
            raise RuntimeError('cannot add widget after application setup')
        self.widgets[widget.NAME] = widget

    def add_servicepoint(self, identifier, callback):
        """Add a new function as servicepoint."""
        if self.initialized is not None:
            raise RuntimeError('cannot add servicepoint after application setup')
        self._services[identifier] = callback

    def connect_event(self, event, callback):
        """Connect an event to the current application."""
        return self._event_manager.connect(event, callback)

    def disconnect_event(self, listener_id):
        """Disconnect a given listener_id."""
        self._event_manager.remove(listener_id)

    def get_page_metadata(self):
        """Return the metadata as HTML part for templates."""
        from textpress.htmlhelpers import script, meta, link
        from textpress.utils import dump_json
        generators = {'script': script, 'meta': meta, 'link': link,
                      'snippet': lambda html: html}
        result = [
            meta(name='generator', content='TextPress'),
            link('pingback', url_for('blog/service_rsd')),
            script(url_for('core/shared', filename='js/jQuery.js')),
            script(url_for('core/shared', filename='js/TextPress.js'))
        ]
        result.append(
            u'<script type="text/javascript">'
                u'TextPress.BLOG_URL = %s;'
            u'</script>' % dump_json(self.cfg['blog_url'].rstrip('/'))
        )
        for type, attr in local.page_metadata:
            result.append(generators[type](**attr))

        #! this is called before the page metadata is assembled with
        #! the list of already collected metadata.  You can extend the
        #! list in place to add some more html snippets to the page header.
        emit_event('before-metadata-assembled', result, buffered=True)
        return u'\n'.join(result)

    def _dispatch_request(self, environ, start_response):
        """Handle the incoming request."""
        # Create a new request object, register it with the application
        # and all the other stuff on the current thread but initialize
        # it afterwards.  We do this so that the request object can query
        # the database in the initialization method.
        request = object.__new__(Request)
        local.application = self
        local.request = request
        local.page_metadata = []
        local.request_locals = {}
        request.__init__(self, environ)

        # check if the blog is in maintenance_mode and the user is
        # not an administrator. in that case just show a message that
        # the user is not privileged to view the blog right now. Exception:
        # the page is the login page for the blog.
        if request.path not in ('/admin', '/admin/', '/admin/login') \
           and self.cfg['maintenance_mode']:
            from textpress.models import ROLE_ADMIN
            if request.user.role < ROLE_ADMIN:
                response = render_response('maintenance.html')
                response.status_code = 503
                return response(environ, start_response)

        #! the after-request-setup event can return a response
        #! or modify the request object in place. If we have a
        #! response we just send it. Plugins that inject something
        #! into the request setup have to check if they are in
        #! maintenance mode themselves.
        for result in emit_event('after-request-setup', request):
            if result is not None:
                return result(environ, start_response)

        # normal request dispatching
        try:
            endpoint, args = request.urls.match(request.path)
            response = self.views[endpoint](request, **args)
        except NotFound, e:
            response = render_response('404.html')
            response.status_code = 404
        except Forbidden, e:
            if request.user.is_somebody:
                response = render_response('403.html')
                response.status_code = 403
            else:
                response = simple_redirect(url_for('admin/login',
                                                   next=request.path))
        except HTTPException, e:
            response = e.get_response(environ)

        #! allow plugins to change the response object
        for result in emit_event('before-response-processed', response):
            if result is not None:
                response = result
                break

        if request.session.should_save:
            cookie_name = self.cfg['session_cookie_name']
            request.session.save_cookie(response, cookie_name)

        return response(environ, start_response)

    def __call__(self, environ, start_response):
        """Make the application object a WSGI application."""
        return ClosingIterator(self.dispatch_request(environ, start_response),
                               [local_manager.cleanup, cleanup_session])


def get_dispatcher(instance_folder):
    """
    Pass it the path to the instance folder and it will return a WSGI
    application for that instance.  This WSGI applicaiton will be either
    a `TextPress` object or, if the instance is not yet existing, a
    function that initializes the textpress instance.  Keep in mind that
    you can't have more than one application in the same python interpreter
    for the same instance folder.  A second call for this function with
    the same instance folder will return the same application.
    """
    instance_folder = path.realpath(instance_folder)
    _instance_lock.acquire()
    try:
        application = _instances.get(instance_folder)
        if application is None or application.wants_reload:
            try:
                application = make_textpress(instance_folder)
            except InstanceNotInitialized:
                from textpress.websetup import WebSetup
                application = WebSetup(instance_folder)
            else:
                _instances[instance_folder] = application
        return application
    finally:
        _instance_lock.release()


def make_app(instance_folder=None):
    """
    Return WSGI application for a given instance folder.  If no instance
    folder is given the instance folder is loaded from the WSGI environment,
    from the `textpress.instance_folder` key.
    """
    def application(environ, start_response):
        path = instance_folder or environ['textpress.instance_folder']
        return get_dispatcher(path)(environ, start_response)
    return application


def make_textpress(instance_folder, bind_to_thread=False):
    """
    Creates a new instance of the application. Always use this function to
    create an application because the process of setting the application up
    requires locking which *only* happens in `make_textpress`.

    If bind_to_thread is true the application will be set for this thread.
    For WSGI applications use the `make_app` or `get_dispatcher` functions
    which return proper WSGI applications all the time.
    """
    _setup_lock.acquire()
    try:
        # make sure this thread has access to the variable so just set
        # up a partial class and call __init__ later.
        local.application = app = object.__new__(TextPress)
        app.__init__(instance_folder)
    finally:
        # if there was no error when setting up the TextPress instance
        # we should now have an attribute here to delete
        app = get_application()
        if app is not None and not bind_to_thread:
            local_manager.cleanup()
        _setup_lock.release()

    return app
