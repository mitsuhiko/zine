# -*- coding: utf-8 -*-
"""
    textpress.application
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements the central application object :class:`TextPress`
    and a couple of helper functions and classes.


    :copyright: 2007-2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os import path, remove, makedirs, walk
from time import time
from thread import allocate_lock
from itertools import izip
from datetime import datetime, timedelta
from urlparse import urlparse
from collections import deque
from inspect import getdoc

from babel import Locale

from jinja2 import Environment, BaseLoader, TemplateNotFound

from werkzeug import Request as RequestBase, Response as ResponseBase, \
     SharedDataMiddleware, url_quote, routing, redirect as simple_redirect
from werkzeug.exceptions import HTTPException, BadRequest, Forbidden, \
     NotFound
from werkzeug.contrib.securecookie import SecureCookie

from textpress.database import db, cleanup_session
from textpress.config import Configuration
from textpress.cache import get_cache
from textpress.utils import ClosingIterator, local, local_manager
from textpress.utils.validators import check_external_url


#: path to the shared data of the core components
SHARED_DATA = path.join(path.dirname(__file__), 'shared')

#: path to the builtin templates (admin panel and page defaults)
BUILTIN_TEMPLATE_PATH = path.join(path.dirname(__file__), 'templates')

#: the lock for the application setup.
_setup_lock = allocate_lock()


def get_request():
    """Return the current request.  If no request is available this function
    returns `None`.
    """
    return getattr(local, 'request', None)


def get_application():
    """Get the current application.  If there is not application available
    because no application is bound to the thread, `None` is returned.
    """
    return getattr(local, 'application', None)


def url_for(endpoint, **args):
    """Get the URL to an endpoint.  The keyword arguments provided are used
    as URL values.  Unknown URL values are used as keyword argument.
    Additionally there are some special keyword arguments:

    `_anchor`
        This string is used as URL anchor.

    `_external`
        If set to `True` the URL will be generated with the full server name
        and `http://` prefix.
    """
    if hasattr(endpoint, 'get_url_values'):
        rv = endpoint.get_url_values()
        if rv is not None:
            if isinstance(rv, basestring):
                return rv
            endpoint, updated_args = rv
            args.update(updated_args)
    anchor = args.pop('_anchor', None)
    external = args.pop('_external', False)
    rv = local.application.url_adapter.build(endpoint, args,
                                             force_external=external)
    if anchor is not None:
        rv += '#' + url_quote(anchor)
    return rv


def redirect(url, code=302, allow_external_redirect=False):
    """Return a redirect response.  Like Werkzeug's redirect but this
    one checks for external redirects too.  If a redirect to an external
    target was requested `BadRequest` is raised unless
    `allow_external_redirect` was explicitly set to `True`.
    """
    if not allow_external_redirect:
        #: check if the url is on the same server
        #: and make it an external one
        try:
            url = check_external_url(local.application, url, True)
        except ValueError:
            raise BadRequest()
    return simple_redirect(url, code)


def emit_event(event, *args, **kwargs):
    """Emit a event and return a list of event results.  Each called
    function contributes one item to the returned list.

    This is equivalent to the following call to :func:`iter_listeners`::

        result = []
        for listener in iter_listeners(event):
            result.append(listener(*args, **kwargs))
    """
    return [x(*args, **kwargs) for x in
            local.application._event_manager.iter(event)]


def iter_listeners(event):
    """Return an iterator for all the listeners for the event provided."""
    return local.application._event_manager.iter(event)


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
    """Renders a template. If `_stream` is ``True`` the return value will be
    a Jinja template stream and not an unicode object.
    This is used by `render_response`.
    """
    #! called right before a template is rendered, the return value is
    #! ignored but the context can be modified in place.
    emit_event('before-render-template', template_name, _stream, context)
    tmpl = local.application.template_env.get_template(template_name)
    if _stream:
        return tmpl.stream(context)
    return tmpl.render(context)


def render_response(template_name, **context):
    """Like render_template but returns a response. If `_stream` is ``True``
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


class Request(RequestBase):
    """This class holds the incoming request data."""

    def __init__(self, environ, app=None):
        RequestBase.__init__(self, environ)
        if app is None:
            app = get_application()
        self.app = app

        engine = self.app.database_engine

        # get the session and try to get the user object for this request.
        from textpress.models import User
        user = None
        cookie_name = app.cfg['session_cookie_name']
        session = SecureCookie.load_cookie(self, cookie_name,
                                           app.cfg['secret_key'])
        user_id = session.get('uid')
        if user_id:
            user = User.objects.get(user_id)
        if user is None:
            user = User.objects.get_nobody()
        self.user = user
        self.session = session

    def login(self, user, permanent=False):
        """Log the given user in. Can be user_id, username or
        a full blown user object.
        """
        from textpress.models import User
        if isinstance(user, (int, long)):
            user = User.objects.get(user)
        elif isinstance(user, basestring):
            user = User.objects.filter_by(username=user).first()
        if user is None:
            raise RuntimeError('User does not exist')
        self.user = user
        #! called after a user was logged in successfully
        emit_event('after-user-login', user)
        self.session['uid'] = user.user_id
        if permanent:
            self.session['pmt'] = True

    def logout(self):
        """Log the current user out."""
        from textpress.models import User
        user = self.user
        self.user = User.objects.get_nobody()
        self.session.clear()
        #! called after a user was logged out and the session cleared.
        emit_event('after-user-logout', user)


class Response(ResponseBase):
    """This class holds the resonse data.  The default charset is utf-8
    and the default mimetype ``'text/html'``.
    """
    default_mimetype = 'text/html'


class EventManager(object):
    """Helper class that handles event listeners and event emitting.

    This is *not* a public interface. Always use the `emit_event` or
    `iter_listeners` functions to access it or the `connect_event` or
    `disconnect_event` methods on the application.
    """

    def __init__(self, app):
        self.app = app
        self._listeners = {}
        self._last_listener = 0

    def connect(self, event, callback, position='after'):
        """Connect a callback to an event."""
        assert position in ('before', 'after'), 'invalid position'
        listener_id = self._last_listener
        event = intern(event)
        if event not in self._listeners:
            self._listeners[event] = deque([callback])
        elif position == 'after':
            self._listeners[event].append(callback)
        elif position == 'before':
            self._listeners[event].appendleft(callback)
        self._last_listener += 1
        return listener_id

    def remove(self, listener_id):
        """Remove a callback again."""
        for event in self._listeners:
            event.pop(listener_id, None)

    def iter(self, event):
        """Return an iterator for all listeners of a given name."""
        if event not in self._listeners:
            return iter(())
        return iter(self._listeners[event])

    def template_emit(self, event, *args, **kwargs):
        """Emits events for the template context."""
        results = []
        for f in self.iter(event):
            rv = f(*args, **kwargs)
            if rv is not None:
                results.append(rv)
        return TemplateEventResult(results)


class TemplateEventResult(list):
    """A list subclass for results returned by the event listener that
    concatenates the results if converted to string, otherwise it works
    exactly like any other list.
    """

    def __init__(self, items):
        list.__init__(self, items)

    def __unicode__(self):
        return u''.join(map(unicode, self))

    def __str__(self):
        return unicode(self).encode('utf-8')


class Theme(object):
    """Represents a theme and is created automaticall by `add_theme`"""

    __slots__ = ('app', 'name', 'template_path', 'metadata')

    def __init__(self, app, name, template_path, metadata=None):
        BaseLoader.__init__(self)
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
        parts = [x for x in name.split('/') if not x == '..']
        for fn in self.get_searchpath():
            fn = path.join(fn, *parts)
            if path.exists(fn):
                f = file(fn)
                try:
                    contents = f.read().decode('utf-8')
                finally:
                    f.close()
                mtime = path.getmtime(fn)
                return contents, fn, lambda: mtime == path.getmtime(fn)

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
        """Get the searchpath for this theme including plugins and
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


class ThemeLoader(BaseLoader):
    """Forwards theme lookups to the current active theme."""

    def __init__(self, app):
        BaseLoader.__init__(self)
        self.app = app

    def get_source(self, environment, name):
        rv = self.app.theme.get_source(name)
        if rv is None:
            raise TemplateNotFound(name)
        return rv


class InstanceNotInitialized(RuntimeError):
    """Raised if an application was created for a not yet initialized
    instance folder.
    """


class TextPress(object):
    """The central application object.

    Even though the :class:`TextPress` class is a regular Python class, you
    can't create instances by using the regular constructor.  The only
    documented way to create this class is the :func:`make_textpress`
    function or by using one of the dispatchers created by :func:`make_app`.
    """

    _setup_only = []
    def setuponly(f, container=_setup_only):
        """Mark a function as "setup only".  After the setup those
        functions will be replaced with a dummy function that raises
        an exception."""
        container.append(f.__name__)
        f.__doc__ = (getdoc(f) or '') + '\n\n*This function can only be ' \
                    'called during application setup*'
        return f

    def __init__(self, instance_folder):
        # this check ensures that only make_app can create TextPress instances
        if get_application() is not self:
            raise TypeError('cannot create %r instances. use the '
                            'make_textpress factory function.' %
                            self.__class__.__name__)
        self.instance_folder = instance_folder

        # create the event manager, this is the first thing we have to
        # do because it could happen that events are sent during setup
        self.initialized = False
        self._event_manager = EventManager(self)

        # and instanciate the configuration. this won't fail,
        # even if the database is not connected.
        self.cfg = Configuration(path.join(instance_folder, 'textpress.ini'))
        if not self.cfg.exists:
            raise InstanceNotInitialized()

        # connect to the database
        self.database_engine = db.create_engine(self.cfg['database_uri'],
                                                self.instance_folder)

        # now setup the cache system
        self.cache = get_cache(self)

        # setup core package urls and shared stuff
        import textpress
        from textpress.urls import make_urls
        from textpress.views import all_views
        from textpress.services import all_services
        from textpress.parsers import all_parsers
        from textpress import i18n
        self.views = all_views.copy()
        self.parsers = all_parsers.copy()
        self._url_rules = make_urls(self)
        self._services = all_services.copy()
        self._shared_exports = {}
        self._template_globals = {}
        self._template_filters = {}
        self._template_tests = {}
        self._template_searchpath = []

        # initialize i18n/l10n system
        self.locale = Locale(self.cfg['language'])
        self.translations = i18n.load_translations(self.locale)

        # init themes
        _ = i18n.gettext
        default_theme = Theme(self, 'default', BUILTIN_TEMPLATE_PATH, {
            'name':         _('Default Theme'),
            'description':  _('Simple default theme that doesn\'t '
                              'contain any style information.'),
            'preview':      'core::default_preview.png'
        })
        self.themes = {'default': default_theme}

        self.apis = {}
        self.importers = {}

        # register the pingback API.
        from textpress import pingback
        self.add_api('pingback', True, pingback.service)
        self.pingback_endpoints = pingback.endpoints.copy()

        # register our builtin importers
        from textpress.importers import all_importers
        for importer in all_importers:
            self.add_importer(importer)

        # insert list of widgets
        from textpress.widgets import all_widgets
        self.widgets = dict((x.NAME, x) for x in all_widgets)

        # load plugins
        from textpress.pluginsystem import find_plugins, \
             register_application, BUILTIN_PLUGIN_FOLDER
        self.plugin_folder = path.join(instance_folder, 'plugins')
        self.plugin_searchpath = [self.plugin_folder]
        for folder in self.cfg['plugin_searchpath'].split(','):
            self.plugin_searchpath.append(folder.strip())
        self.plugin_searchpath.append(BUILTIN_PLUGIN_FOLDER)

        # register the application in the ihook
        register_application(self)

        # load the plugins
        self.plugins = {}
        for plugin in find_plugins(self):
            if plugin.active:
                plugin.setup()
            self.plugins[plugin.name] = plugin

        # init the template system with the core stuff
        from textpress import htmlhelpers, models
        env = Environment(loader=ThemeLoader(self),
                          extensions=['jinja2.ext.i18n'])
        env.globals.update(
            cfg=self.cfg,
            h=htmlhelpers,
            url_for=url_for,
            emit_event=self._event_manager.template_emit,
            request=local('request'),
            render_widgets=lambda: render_template('_widgets.html'),
            get_page_metadata=self.get_page_metadata,
            textpress={
                'version':      textpress.__version__,
                'copyright':    _('Copyright %(years)s by the Pocoo Team')
                                % {'years': '2007-2008'}
            }
        )

        env.filters.update(
            json=__import__('simplejson').dumps,
            datetimeformat=i18n.format_datetime,
            dateformat=i18n.format_date,
            monthformat=i18n.format_month
        )

        env.install_gettext_translations(self.translations)

        # copy the widgets into the global namespace
        for name, widget in self.widgets.iteritems():
            if not widget.INVISIBLE:
                self._template_globals[name] = widget

        # set up plugin template extensions
        env.globals.update(self._template_globals)
        env.filters.update(self._template_filters)
        env.tests.update(self._template_tests)
        del self._template_globals, self._template_filters, \
            self._template_tests
        self.template_env = env

        # now add the middleware for static file serving
        self.add_shared_exports('core', SHARED_DATA)
        self.add_middleware(SharedDataMiddleware, self._shared_exports)

        # set up the urls
        self.url_map = routing.Map(self._url_rules)
        del self._url_rules

        # and create a url adapter
        scheme, netloc, script_name = urlparse(self.cfg['blog_url'])[:3]
        self.url_adapter = self.url_map.bind(netloc, script_name,
                                             url_scheme=scheme)

        # mark the app as finished and override the setup functions
        def _error():
            raise RuntimeError('Cannot register new callbacks after '
                               'application setup phase.')
        self.__dict__.update(dict.fromkeys(self._setup_only, _error))
        self.initialized = True

        #! called after the application and all plugins are initialized
        emit_event('application-setup-done')

    def close(self):
        """Called by the dispatcher before reloading.  This method should be
        called by hand if the application object is no longer in use for shell
        scripts and similar situations.  This cleans up data stored outside of
        the application object such as loaded plugins.  After this was called,
        the application object can't be used any more and has undefined
        behavior.

        Multiple calls to :meth:`close` are safe and won't cause errors.
        """
        from textpress.pluginsystem import unregister_application
        unregister_application(self)
        local.application = None

    def generate_apache_config(self):
        """Return a string with an apache config for shared data."""
        buf = []
        for alias, dst in self._shared_exports.iteritems():
            dst = path.abspath(dst)
            if len(dst.split()) != 1:
                dst = '"%s"' % dst
            buf.append('Alias %s %s' % (alias, dst))
        return '\n'.join(buf)

    @setuponly
    def add_template_filter(self, name, callback):
        """Add a Jinja2 template filter."""
        self._template_filters[name] = callback

    @setuponly
    def add_template_test(self, name, callback):
        """Add a Jinja2 template test."""
        self._template_tests[name] = callback

    @setuponly
    def add_template_global(self, name, value):
        """Add a template global.  Object's added that way are available in
        the global template namespace.
        """
        self._template_globals[name] = value

    @setuponly
    def add_template_searchpath(self, path):
        """Add a new template searchpath to the application.  This searchpath
        is queried *after* the themes but *before* the builtin templates are
        looked up.
        """
        self._template_searchpath.append(path)

    @setuponly
    def add_api(self, name, preferred, callback, blog_id=1):
        """Add a new API to the blog.  The newly added API is available at
        ``/_services/<name>`` and automatically exported in the RSD file.
        The `blog_id` is an unused oddity of the RSD file, preferred an
        indicator if this API is preferred or not.
        The callback is called for all requests to the service URL.
        """
        endpoint = 'services/' + name
        self.apis[name] = (blog_id, preferred, endpoint)
        self.add_url_rule('/_services/' + name, endpoint=endpoint)
        self.add_view(endpoint, callback)

    @setuponly
    def add_importer(self, importer):
        """Register an importer.  For more informations about importers
        see the :mod:`textpress.importers`.
        """
        importer = importer(self)
        endpoint = 'import/' + importer.name
        self.importers[importer.name] = importer
        self.add_url_rule('/maintenance/import/' + importer.name,
                          prefix='admin', endpoint=endpoint)
        self.add_view(endpoint, importer)

    @setuponly
    def add_pingback_endpoint(self, endpoint, callback):
        """Notify the pingback service that the endpoint provided supports
        pingbacks.  The second parameter must be the callback function
        called on pingbacks.
        """
        self.pingback_endpoints[endpoint] = callback

    @setuponly
    def add_theme(self, name, template_path, metadata=None):
        """Add a theme. You have to provide the shortname for the theme
        which will be used in the admin panel etc. Then you have to provide
        the path for the templates. Usually this path is relative to the
        directory of the plugin's `__file__`.

        The metadata can be ommited but in that case some information in
        the admin panel is not available.
        """
        self.themes[name] = Theme(self, name, template_path, metadata)

    @setuponly
    def add_shared_exports(self, name, path):
        """Add a shared export for name that points to a given path and
        creates an url rule for <name>/shared that takes a filename
        parameter.  A shared export is some sort of static data from a
        plugin.  Per default TextPress will shared the data on it's own but
        in the future it would be possible to generate an Apache/nginx
        config on the fly for the static data.

        The static data is available at `/_shared/<name>` and points to
        `path` on the file system.  This also generates a URL rule named
        `<name>/shared` that accepts a `filename` parameter.  This can be
        used for URL generation.
        """
        self._shared_exports['/_shared/' + name] = path
        self.add_url_rule('/_shared/%s/<string:filename>' % name,
                          endpoint=name + '/shared', build_only=True)

    @setuponly
    def add_middleware(self, middleware_factory, *args, **kwargs):
        """Add a middleware to the application.  The `middleware_factory`
        is a callable that is called with the active WSGI application as
        first argument, `args` as extra positional arguments and `kwargs`
        as keyword arguments.

        The newly applied middleware wraps an internal WSGI application.
        """
        self.dispatch_request = middleware_factory(self.dispatch_request,
                                                   *args, **kwargs)

    @setuponly
    def add_config_var(self, key, type, default):
        """Add a configuration variable to the application.  The config
        variable should be named ``<plugin_name>/<variable_name>``.  The
        `variable_name` itself must not contain another slash.  Variables
        that are not prefixed are reserved for TextPress' internal usage.
        The `type` can be one of the following builtins:

        +-------------+--------------------------+
        | `int`       | An integer value         |
        +-------------+--------------------------+
        | `unicode`   | An unicode value         |
        +-------------+--------------------------+
        | `bool`      | A boolean value          |
        +-------------+--------------------------+

        Lists and other data structures are not supported at the moment,
        you can however use strings and split them by comma.

        Example usage::

            app.add_config_var('my_plugin/with_useless_stuff', bool, True)
        """
        if key.count('/') > 1:
            raise ValueError('key might not have more than one slash')
        self.cfg.config_vars[key] = (type, default)

    @setuponly
    def add_url_rule(self, rule, **kwargs):
        """Add a new URL rule to the url map.  This function accepts the same
        arguments as a werkzeug routing rule.  Additionally a `prefix`
        parameter is accepted that can be used to add the common prefixes
        based on the configuration.  Basically the following two calls
        do exactly the same::

            app.add_url_rule('/foo', prefix='admin', ...)
            app.add_url_rule(app.cfg['admin_url_prefix'] + '/foo', ...)

        It also takes a `view` keyword argument that, if given registers
        a view for the url view::

            app.add_url_rule(..., endpoint='bar', view=bar)

        is equivalent to::

            app.add_url_rule(..., endpoint='bar')
            app.add_view('bar', bar)
        """
        prefix = kwargs.pop('prefix', None)
        if prefix is not None:
            rule = self.cfg[prefix + '_url_prefix'] + rule
        view = kwargs.pop('view', None)
        self._url_rules.append(routing.Rule(rule, **kwargs))
        if view is not None:
            self.views[kwargs['endpoint']] = view

    @setuponly
    def add_view(self, endpoint, callback):
        """Add a callback as view.  The endpoint is the endpoint for the URL
        rule and has to be equivalent to the endpoint passed to
        :meth:`add_url_rule`.
        """
        self.views[endpoint] = callback

    @setuponly
    def add_parser(self, name, class_):
        """Add a new parser class.  This parser has to be a subclass of
        :class:`textpress.parsers.BaseParser`.
        """
        self.parsers[name] = class_

    @setuponly
    def add_widget(self, widget):
        """Add a widget."""
        self.widgets[widget.NAME] = widget

    @setuponly
    def add_servicepoint(self, identifier, callback):
        """Add a new function as servicepoint.  A service point is a function
        that is called by an external non-human interface such as an
        JavaScript or XMLRPC client.  It's automatically exposed to all
        service interfaces.
        """
        self._services[identifier] = callback

    @setuponly
    def connect_event(self, event, callback, position='after'):
        """Connect a callback to an event.  Per default the callback is
        appended to the end of the handlers but handlers can ask for a higher
        privilege by setting `position` to ``'before'``.

        Example usage::

            def on_before_metadata_assembled(metadata):
                metadata.append('<!-- IM IN UR METADATA -->')

            def setup(app):
                app.connect_event('before-metadata-assembled',
                                  on_before_metadata_assembled)
        """
        self._event_manager.connect(event, callback, position)

    @property
    def wants_reload(self):
        """True if the application requires a reload.  This is `True` if
        the config was changed on the file system.  A dispatcher checks this
        value every request and automatically unloads and reloads the
        application if necessary.
        """
        return self.cfg.changed_external

    @property
    def theme(self):
        """Return the current :class:`Theme`."""
        theme = self.cfg['theme']
        if theme not in self.themes:
            theme = 'default'
            self.cfg.change_single('theme', theme)
        return self.themes[theme]

    def bind_to_thread(self):
        """Bind the application to the current thread.  For more information
        about the context concept have a look at :ref:`contexts`.
        """
        local.application = self

    def list_parsers(self):
        """Return a sorted list of parsers (parser_id, parser_name)."""
        return sorted([(key, parser.get_name()) for key, parser in
                       self.parsers.iteritems()], key=lambda x: x[1].lower())

    def get_page_metadata(self):
        """Return the metadata as HTML part for templates.  This is normally
        called by the layout template to get the metadata for the head section.
        """
        from textpress.htmlhelpers import script, meta, link
        from textpress.utils import dump_json
        generators = {'script': script, 'meta': meta, 'link': link,
                      'snippet': lambda html: html}
        result = [
            meta(name='generator', content='TextPress'),
            link('EditURI', url_for('blog/service_rsd'),
                 type='application/rsd+xml', title='RSD'),
            script(url_for('core/shared', filename='js/jQuery.js')),
            script(url_for('core/shared', filename='js/TextPress.js')),
            script(url_for('blog/serve_translation', locale=self.cfg['language']))
        ]
        base_url = self.cfg['blog_url'].rstrip('/')
        result.append(
            u'<script type="text/javascript">'
                u'TextPress.BLOG_URL = %s;'
                u'TextPress.ADMIN_URL = %s;'
            u'</script>' % (
                dump_json(base_url),
                dump_json(base_url + self.cfg['admin_url_prefix'])
            )
        )
        for type, attr in local.page_metadata:
            result.append(generators[type](**attr))

        #! this is called before the page metadata is assembled with
        #! the list of already collected metadata.  You can extend the
        #! list in place to add some more html snippets to the page header.
        emit_event('before-metadata-assembled', result)
        return u'\n'.join(result)

    def dispatch_request(self, environ, start_response):
        """This method is the internal WSGI request and is overridden by
        middlewares applied with :meth:`add_middleware`.  It handles the
        actual request dispatching.
        """
        # Create a new request object, register it with the application
        # and all the other stuff on the current thread but initialize
        # it afterwards.  We do this so that the request object can query
        # the database in the initialization method.
        request = object.__new__(Request)
        local.application = self
        local.request = request
        local.page_metadata = []
        local.request_locals = {}
        request.__init__(environ, self)

        # check if the blog is in maintenance_mode and the user is
        # not an administrator. in that case just show a message that
        # the user is not privileged to view the blog right now. Exception:
        # the page is the login page for the blog.
        admin_prefix = self.cfg['admin_url_prefix']
        if self.cfg['maintenance_mode'] and \
           request.path != admin_prefix and not \
           request.path.startswith(admin_prefix + '/'):
            from textpress.models import ROLE_ADMIN
            if request.user.role < ROLE_ADMIN:
                response = render_response('maintenance.html')
                response.status_code = 503
                return response(environ, start_response)

        #! the after-request-setup event can return a response
        #! or modify the request object in place. If we have a
        #! response we just send it, no other modifications are done.
        for callback in iter_listeners('after-request-setup'):
            result = callback(request)
            if result is not None:
                return result(environ, start_response)

        # normal request dispatching
        try:
            endpoint, args = self.url_adapter.match(request.path)
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

        # make sure the response object is one of ours
        response = Response.force_type(response, environ)

        #! allow plugins to change the response object
        for callback in iter_listeners('before-response-processed'):
            result = callback(response)
            if result is not None:
                response = result

        # update the session cookie at the request end if the
        # session data requires an update.
        if request.session.should_save:
            cookie_name = self.cfg['session_cookie_name']
            if request.session.get('pmt'):
                max_age = 60 * 60 * 24 * 31
                expires = time() + max_age
            else:
                max_age = expires = None
            request.session.save_cookie(response, cookie_name, max_age=max_age,
                                        expires=expires, session_expires=expires)

        return response(environ, start_response)

    def __call__(self, environ, start_response):
        """Make the application object a WSGI application."""
        return ClosingIterator(self.dispatch_request(environ, start_response),
                               [local_manager.cleanup, cleanup_session])

    def __repr__(self):
        return '<TextPress %r [%s]>' % (
            self.instance_folder,
            self.iid
        )

    # remove our decorator
    del setuponly


class StaticDispatcher(object):
    """Dispatches to textpress or the websetup and handles reloads.  Instances
    of this class are created by :func:`make_app` when passed the path to an
    instance folder.
    """

    def __init__(self, instance_folder):
        self.instance_folder = instance_folder
        self.application = None
        self.reload_lock = allocate_lock()

    def get_handler(self):
        # we have an application and that application has no changed config
        if self.application and not self.application.wants_reload:
            return self.application

        # otherwise we have no up to date application, reload
        self.reload_lock.acquire()
        try:
            if self.application:
                # it could be that we waited for the lock to come free and
                # a different request reloaded the application for us.  check
                # here for that a second time.
                if not self.application.wants_reload:
                    return self.application

                # otherwise close the application
                self.application.close()

            # now try to setup the application.  it the setup does not
            # work because the instance is not initialized we hook the
            # websetup in.
            try:
                self.application = make_textpress(self.instance_folder)
            except InstanceNotInitialized:
                from textpress.websetup import WebSetup
                return WebSetup(self.instance_folder)
        finally:
            self.reload_lock.release()

        # if we reach that point we have a valid application from the
        # reloading process which we can return
        return self.application

    def __call__(self, environ, start_response):
        return self.get_handler()(environ, start_response)


class DynamicDispatcher(object):
    """A dispatcher that creates applications on the fly from values of the
    WSGI environment.  This means that the first request to a not yet
    existing application will create it.  Internally it's creating a
    :class:`StaticDispatcher` for every instance folder.
    """

    def __init__(self):
        self.dispatchers = {}
        self.init_lock = Lock()

    def __call__(self, environ, start_response):
        instance_folder = path.realpath(environ['textpress.instance_folder'])
        self.init_lock.acquire()
        try:
            if instance_folder not in self.dispatchers:
                dispatcher = StaticDispatcher(instance_folder)
                self.dispatchers[instance_folder] = dispatcher
            else:
                dispatcher = self.dispatchers[instance_folder]
        finally:
            self.init_lock.release()
        return dispatcher(environ, start_response)


def make_app(instance_folder=None):
    """This function creates a WSGI application for TextPress.   Even though
    the central :class:`TextPress` object implements the WSGI protocol it's
    not forwarded to the webserver directly because the it's reloaded under
    some circumstances by the :ref:`dispatchers <dispatchers>` that wrap it.
    These dispatchers also redirect requests to the websetup if the instance
    does not exist by now.

    The return value of this function is guaranteed to be a WSGI application.
    It's either a :class:`StaticDispatcher` that points to the instance
    provided or a :class:`DynamicDispatcher`.

    If the `instance_folder` is provided a simple dispatcher is returned that
    manages the TextPress application for this instance.  If you don't provide
    one the return value will be a dynamic dispatcher that can handle multiple
    TextPress instances.  The textpress instance for one request is specified
    in the WSGI environ in the ``'textpress.instance'`` key.

    If you need a :class:`TextPress` object for scripts or other situations
    you should use the :func:`make_textpress` function that returns a
    :class:`TextPress` object instead.
    """
    if instance_folder is None:
        return DynamicDispatcher()
    return StaticDispatcher(path.realpath(instance_folder))


def make_textpress(instance_folder, bind_to_thread=False):
    """Creates a new instance of the application.  Always use this function
    to create an application because the process of setting the application
    up requires locking which *only* happens in :func:`make_textpress`.

    If `bind_to_thread` is `True` the application will be set for this thread.
    Don't use the application object returned as WSGI application beside for
    scripting / testing or if you know what you're doing.

    The :class:`TextPress` object alone does not handle any reloading or
    instance setup.
    """
    _setup_lock.acquire()
    try:
        # make sure this thread has access to the variable so just set
        # up a partial class and call __init__ later.
        local.application = app = object.__new__(TextPress)

        # attach the iid
        app.iid = 'tp_%x' % id(app)

        # now initialize the application
        app.__init__(instance_folder)
    finally:
        # if there was no error when setting up the TextPress instance
        # we should now have an attribute here to delete
        app = get_application()
        if app is not None and not bind_to_thread:
            local_manager.cleanup()
        _setup_lock.release()

    return app
