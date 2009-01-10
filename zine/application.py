# -*- coding: utf-8 -*-
"""
    zine.application
    ~~~~~~~~~~~~~~~~

    This module implements the central application object :class:`Zine`
    and a couple of helper functions and classes.


    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os import path, remove, makedirs, walk, environ
from time import time
from itertools import izip
from datetime import datetime, timedelta
from urlparse import urlparse, urljoin
from collections import deque
from inspect import getdoc

from babel import Locale

from jinja2 import Environment, BaseLoader, TemplateNotFound

from werkzeug import Request as RequestBase, Response as ResponseBase, \
     SharedDataMiddleware, url_quote, routing, redirect as _redirect, \
     escape, cached_property
from werkzeug.exceptions import HTTPException, Forbidden, \
     NotFound
from werkzeug.contrib.securecookie import SecureCookie

from zine import _core
from zine.environment import SHARED_DATA, BUILTIN_TEMPLATE_PATH, \
     BUILTIN_PLUGIN_FOLDER
from zine.database import db, cleanup_session
from zine.cache import get_cache
from zine.utils import ClosingIterator, local, local_manager, dump_json, \
     htmlhelpers
from zine.utils.mail import split_email
from zine.utils.datastructures import ReadOnlyMultiMapping
from zine.utils.exceptions import UserException


#: the default theme settings
DEFAULT_THEME_SETTINGS = {
    # pagination defaults
    'pagination.normal':            '<a href="%(url)s">%(page)d</a>',
    'pagination.active':            '<strong>%(page)d</strong>',
    'pagination.commata':           '<span class="commata">,\n</span>',
    'pagination.ellipsis':          u'<span class="ellipsis"> …\n</span>',
    'pagination.threshold':         3,
    'pagination.left_threshold':    2,
    'pagination.right_threshold':   1,
    'pagination.prev_link':         False,
    'pagination.next_link':         False,
    'pagination.gray_prev_link':    True,
    'pagination.gray_next_link':    True,
    'pagination.simple':            False,

    # datetime formatting settings
    'date.date_format.default':     'medium',
    'date.datetime_format.default': 'medium',
    'date.date_format.short':       None,
    'date.date_format.medium':      None,
    'date.date_format.full':        None,
    'date.date_format.long':        None,
    'date.datetime_format.short':   None,
    'date.datetime_format.medium':  None,
    'date.datetime_format.full':    None,
    'date.datetime_format.long':    None
}


def get_request():
    """Return the current request.  If no request is available this function
    returns `None`.
    """
    return getattr(local, 'request', None)


def get_application():
    """Get the application instance.  If the application was not yet set up
    the return value is `None`
    """
    return _core._application


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
                return make_external_url(rv)
            endpoint, updated_args = rv
            args.update(updated_args)
    anchor = args.pop('_anchor', None)
    external = args.pop('_external', False)
    rv = get_application().url_adapter.build(endpoint, args,
                                             force_external=external)
    if anchor is not None:
        rv += '#' + url_quote(anchor)
    return rv


def shared_url(spec):
    """Returns a URL to a shared resource."""
    endpoint, filename = spec.split('::', 1)
    return url_for(endpoint + '/shared', filename=filename)


def emit_event(event, *args, **kwargs):
    """Emit a event and return a list of event results.  Each called
    function contributes one item to the returned list.

    This is equivalent to the following call to :func:`iter_listeners`::

        result = []
        for listener in iter_listeners(event):
            result.append(listener(*args, **kwargs))
    """
    return [x(*args, **kwargs) for x in
            get_application()._event_manager.iter(event)]


def iter_listeners(event):
    """Return an iterator for all the listeners for the event provided."""
    return get_application()._event_manager.iter(event)


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


def select_template(templates):
    """Selects the first template from a list of templates that exists."""
    env = get_application().template_env
    for template in templates:
        if template is not None:
            try:
                return env.get_template(template)
            except TemplateNotFound:
                pass
    raise TemplateNotFound('<multiple-choices>')


def render_template(template_name, _stream=False, **context):
    """Renders a template. If `_stream` is ``True`` the return value will be
    a Jinja template stream and not an unicode object.
    This is used by `render_response`.  If the `template_name` is a list of
    strings the first template that exists is selected.
    """
    if not isinstance(template_name, basestring):
        tmpl = select_template(template_name)
        template_name = tmpl.name
    else:
        tmpl = get_application().template_env.get_template(template_name)

    #! called right before a template is rendered, the return value is
    #! ignored but the context can be modified in place.
    emit_event('before-render-template', template_name, _stream, context)

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


class InternalError(UserException):
    """Subclasses of this exception are used to signal internal errors that
    should not happen, but may do if the configuration is garbage.  If an
    internal error is raised during request handling they are converted into
    normal server errors for anonymous users (but not logged!!!), but if the
    current user is an administrator, the error is displayed.
    """

    help_text = None


class Request(RequestBase):
    """This class holds the incoming request data."""


    def __init__(self, environ, app=None):
        RequestBase.__init__(self, environ)
        if app is None:
            app = get_application()
        self.app = app

        engine = self.app.database_engine

        # get the session and try to get the user object for this request.
        from zine.models import User
        user = None
        cookie_name = app.cfg['session_cookie_name']
        session = SecureCookie.load_cookie(self, cookie_name,
                                           app.cfg['secret_key']
                                              .encode('utf-8'))
        user_id = session.get('uid')
        if user_id:
            user = User.query.options(db.eagerload('groups'),
                                      db.eagerload('groups', '_privileges')) \
                             .get(user_id)
        if user is None:
            user = User.query.get_nobody()
        self.user = user
        self.session = session

    @property
    def is_behind_proxy(self):
        """Are we behind a proxy?"""
        return environ.get('ZINE_BEHIND_PROXY') == '1'

    def login(self, user, permanent=False):
        """Log the given user in. Can be user_id, username or
        a full blown user object.
        """
        from zine.models import User
        if isinstance(user, (int, long)):
            user = User.query.get(user)
        elif isinstance(user, basestring):
            user = User.query.filter_by(username=user).first()
        if user is None:
            raise RuntimeError('User does not exist')
        self.user = user
        #! called after a user was logged in successfully
        emit_event('after-user-login', user)
        self.session['uid'] = user.id
        self.session['lt'] = time()
        if permanent:
            self.session['pmt'] = True

    def logout(self):
        """Log the current user out."""
        from zine.models import User
        user = self.user
        self.user = User.query.get_nobody()
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
            try:
                event.remove(listener_id)
            except ValueError:
                pass

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
    app = None

    def __init__(self, name, template_path, metadata=None,
                 settings=None, configuration_page=None):
        BaseLoader.__init__(self)
        self.name = name
        self.template_path = template_path
        self.metadata = metadata or {}
        self._settings = settings or {}
        self.configuration_page = configuration_page

    @property
    def configurable(self):
        return self.configuration_page is not None

    @property
    def preview_url(self):
        if self.metadata.get('preview'):
            return shared_url(self.metadata['preview'])

    @property
    def has_preview(self):
        return bool(self.metadata.get('preview'))

    @property
    def is_current(self):
        return self.name == self.app.cfg['theme']

    @property
    def display_name(self):
        return self.metadata.get('name') or self.name.title()

    @property
    def description(self):
        """Return the description of the plugin."""
        return self.metadata.get('description', u'')

    @property
    def has_author(self):
        """Does the theme has an author at all?"""
        return 'author' in self.metadata

    @property
    def author_info(self):
        """The author, mail and author URL of the plugin."""
        return split_email(self.metadata.get('author', u'Nobody')) + \
               (self.metadata.get('author_url'),)

    @property
    def html_author_info(self):
        """Return the author info as html link."""
        name, email, url = self.author_info
        if not url:
            if not email:
                return escape(name)
            url = 'mailto:%s' % url_quote(email)
        return u'<a href="%s">%s</a>' % (
            escape(url),
            escape(name)
        )

    @property
    def author(self):
        """Return the author of the plugin."""
        x = self.author_info
        return x[0] or x[1]

    @property
    def author_email(self):
        """Return the author email address of the plugin."""
        return self.author_info[1]

    @property
    def author_url(self):
        """Return the URL of the author of the plugin."""
        return self.author_info[2]

    @cached_property
    def settings(self):
        return ReadOnlyMultiMapping(self._settings, DEFAULT_THEME_SETTINGS)

    def get_url_values(self):
        if self.configurable:
            return self.name + '/configure', {}
        raise TypeError('can\'t link to unconfigurable theme')

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

    def format_datetime(self, datetime=None, format=None):
        """Datetime formatting for the template.  the (`datetimeformat`
        filter)
        """
        format = self._get_babel_format('datetime', format)
        return i18n.format_datetime(datetime, format)

    def format_date(self, date=None, format=None):
        """Date formatting for the template.  (the `dateformat` filter)"""
        format = self._get_babel_format('date', format)
        return i18n.format_date(date, format)

    def _get_babel_format(self, key, format):
        """A small helper for the datetime formatting functions."""
        if format is None:
            format = self.settings['date.%s_format.default' % key]
        if format in ('short', 'medium', 'full', 'long'):
            rv = self.settings['date.%s_format.%s' % (key, format)]
            if rv is not None:
                format = rv
        return format


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


class Zine(object):
    """The central application object.

    Even though the :class:`Zine` class is a regular Python class, you
    can't create instances by using the regular constructor.  The only
    documented way to create this class is the :func:`make_zine`
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
        # this check ensures that only make_app can create Zine instances
        if get_application() is not self:
            raise TypeError('cannot create %r instances. use the '
                            'make_zine factory function.' %
                            self.__class__.__name__)
        self.instance_folder = path.abspath(instance_folder)

        # create the event manager, this is the first thing we have to
        # do because it could happen that events are sent during setup
        self.initialized = False
        self._event_manager = EventManager(self)

        # and instanciate the configuration. this won't fail,
        # even if the database is not connected.
        from zine.config import Configuration
        self.cfg = Configuration(path.join(instance_folder, 'zine.ini'))
        if not self.cfg.exists:
            raise _core.InstanceNotInitialized()

        # and hook in the logger
        self.log = log.Logger(path.join(instance_folder, self.cfg['log_file']),
                              self.cfg['log_level'])

        # the iid of the application
        self.iid = self.cfg['iid'].encode('utf-8')
        if not self.iid:
            self.iid = '%x' % id(self)

        # connect to the database
        self.database_engine = db.create_engine(self.cfg['database_uri'],
                                                self.instance_folder)

        # now setup the cache system
        self.cache = get_cache(self)

        # setup core package urls and shared stuff
        import zine
        from zine.urls import make_urls
        from zine.views import all_views, content_type_handlers, \
             admin_content_type_handlers, absolute_url_handlers
        from zine.services import all_services
        from zine.parsers import all_parsers
        self.views = all_views.copy()
        self.content_type_handlers = content_type_handlers.copy()
        self.admin_content_type_handlers = admin_content_type_handlers.copy()
        self.parsers = dict((k, v(self)) for k, v in all_parsers.iteritems())
        self.zeml_element_handlers = []
        self._url_rules = make_urls(self)
        self._absolute_url_handlers = absolute_url_handlers[:]
        self._services = all_services.copy()
        self._shared_exports = {}
        self._template_globals = {}
        self._template_filters = {}
        self._template_tests = {}
        self._template_searchpath = []

        # initialize i18n/l10n system
        self.locale = Locale(self.cfg['language'])
        self.translations = i18n.load_core_translations(self.locale)

        # init themes
        _ = i18n.gettext
        default_theme = Theme('default', BUILTIN_TEMPLATE_PATH, {
            'name':         _(u'Default Theme'),
            'description':  _(u'Simple default theme that doesn\'t '
                              'contain any style information.'),
            'preview':      'core::default_preview.png'
        })
        default_theme.app = self
        self.themes = {'default': default_theme}

        self.apis = {}
        self.importers = {}
        self.feed_importer_extensions = []

        # register the pingback API.
        from zine import pingback
        self.add_api('pingback', True, pingback.service)
        self.pingback_endpoints = pingback.endpoints.copy()

        # register our builtin importers
        from zine.importers import importers
        for importer in importers:
            self.add_importer(importer)

        # and the feed importer extensions
        from zine.importers.feed import extensions
        for extension in extensions:
            self.add_feed_importer_extension(extension)

        # register the default privileges
        from zine.privileges import DEFAULT_PRIVILEGES, CONTENT_TYPE_PRIVILEGES
        self.privileges = DEFAULT_PRIVILEGES.copy()
        self.content_type_privileges = CONTENT_TYPE_PRIVILEGES.copy()

        # insert list of widgets
        from zine.widgets import all_widgets
        self.widgets = dict((x.name, x) for x in all_widgets)

        # load plugins
        from zine.pluginsystem import find_plugins, set_plugin_searchpath
        self.plugin_folder = path.join(instance_folder, 'plugins')
        self.plugin_searchpath = [self.plugin_folder]
        for folder in self.cfg['plugin_searchpath']:
            folder = folder.strip()
            if folder:
                self.plugin_searchpath.append(folder)
        self.plugin_searchpath.append(BUILTIN_PLUGIN_FOLDER)
        set_plugin_searchpath(self.plugin_searchpath)

        # load the plugins
        self.plugins = {}
        for plugin in find_plugins(self):
            if plugin.active:
                plugin.setup()
                self.translations.merge(plugin.translations)
            self.plugins[plugin.name] = plugin

        # set the active theme based on the config.
        theme = self.cfg['theme']
        if theme not in self.themes:
            log.warning(_(u'Theme “%s” is no longer available, falling back '
                          u'to default theme.') % theme, 'core')
            theme = 'default'
            self.cfg.change_single('theme', theme)
        self.theme = self.themes[theme]

        # init the template system with the core stuff
        from zine import models
        env = Environment(loader=ThemeLoader(self),
                          extensions=['jinja2.ext.i18n'])
        env.globals.update(
            cfg=self.cfg,
            theme=self.theme,
            h=htmlhelpers,
            url_for=url_for,
            shared_url=shared_url,
            emit_event=self._event_manager.template_emit,
            request=local('request'),
            render_widgets=lambda: render_template('_widgets.html'),
            get_page_metadata=self.get_page_metadata,
            widgets=self.widgets,
            zine={
                'version':      zine.__version__,
                'copyright':    _(u'Copyright %(years)s by the Zine Team')
                                % {'years': '2008-2009'}
            }
        )

        env.filters.update(
            json=dump_json,
            datetimeformat=self.theme.format_datetime,
            dateformat=self.theme.format_date,
            monthformat=i18n.format_month,
            timedeltaformat=i18n.format_timedelta
        )

        env.install_gettext_translations(self.translations)

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
        def _error(*args, **kwargs):
            raise RuntimeError('Cannot register new callbacks after '
                               'application setup phase.')
        self.__dict__.update(dict.fromkeys(self._setup_only, _error))

        self.cfg.config_vars['default_parser'].choices = \
            self.cfg.config_vars['comment_parser'].choices = \
            self.list_parsers()

        self.initialized = True

        #! called after the application and all plugins are initialized
        emit_event('application-setup-done')

    @property
    def wants_reload(self):
        """True if the application requires a reload.  This is `True` if
        the config was changed on the file system.  A dispatcher checks this
        value every request and automatically unloads and reloads the
        application if necessary.
        """
        return self.cfg.changed_external

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
        see the :mod:`zine.importers`.
        """
        importer = importer(self)
        endpoint = 'import/' + importer.name
        self.importers[importer.name] = importer
        self.add_url_rule('/maintenance/import/' + importer.name,
                          prefix='admin', endpoint=endpoint)
        self.add_view(endpoint, importer)

    @setuponly
    def add_feed_importer_extension(self, extension):
        """Registers a feed importer extension.  This is for example used
        for to implement the ZXA importing in the feed importer.

        All blogs that provide feeds that extend Atom (and in the future
        RSS) should be imported by registering an importer here.
        """
        self.feed_importer_extensions.append(extension)

    @setuponly
    def add_pingback_endpoint(self, endpoint, callback):
        """Notify the pingback service that the endpoint provided supports
        pingbacks.  The second parameter must be the callback function
        called on pingbacks.
        """
        self.pingback_endpoints[endpoint] = callback

    @setuponly
    def add_theme(self, name, template_path=None, metadata=None,
                  settings=None, configuration_page=None):
        """Add a theme. You have to provide the shortname for the theme
        which will be used in the admin panel etc. Then you have to provide
        the path for the templates. Usually this path is relative to the
        directory of the plugin's `__file__`.

        The metadata can be ommited but in that case some information in
        the admin panel is not available.

        Alternatively a custom :class:`Theme` object can be passed to this
        function as only argument.  This makes it possible to register
        custom theme subclasses too.
        """
        if isinstance(name, Theme):
            if template_path is not metadata is not settings \
               is not configuration_page is not None:
                raise TypeError('if a theme instance is provided extra '
                                'arguments must be ommited or None.')
            theme = name
        else:
            theme = Theme(name, template_path, metadata,
                          settings, configuration_page)
        if theme.app is not None:
            raise TypeError('theme is already registered to an application.')
        theme.app = self
        self.themes[theme.name] = theme

    @setuponly
    def add_shared_exports(self, name, path):
        """Add a shared export for name that points to a given path and
        creates an url rule for <name>/shared that takes a filename
        parameter.  A shared export is some sort of static data from a
        plugin.  Per default Zine will shared the data on it's own but
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
        self.dispatch_wsgi = middleware_factory(self.dispatch_wsgi,
                                                   *args, **kwargs)

    @setuponly
    def add_config_var(self, key, field):
        """Add a configuration variable to the application.  The config
        variable should be named ``<plugin_name>/<variable_name>``.  The
        `variable_name` itself must not contain another slash.  Variables
        that are not prefixed are reserved for Zine' internal usage.
        The `field` is an instance of a field class from zine.utils.forms
        that is used to validate the variable. It has to contain the default
        value for that variable.

        Example usage::

            app.add_config_var('my_plugin/my_var', BooleanField(default=True))
        """
        if key.count('/') > 1:
            raise ValueError('key might not have more than one slash')
        self.cfg.config_vars[key] = field

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
    def add_absolute_url(self, handler):
        """Adds a new callback as handler for absolute URLs.  If the normal
        request handling was unable to find a proper response for the request
        the handler is called with the current request as argument and can
        return a response that is then used as normal response.

        If a handler doesn't want to handle the response it may raise a
        `NotFound` exception or return `None`.

        This is for example used to implement the pages support in Zine.
        """
        self._absolute_url_handlers.append(handler)

    @setuponly
    def add_view(self, endpoint, callback):
        """Add a callback as view.  The endpoint is the endpoint for the URL
        rule and has to be equivalent to the endpoint passed to
        :meth:`add_url_rule`.
        """
        self.views[endpoint] = callback

    @setuponly
    def add_content_type(self, content_type, callback, admin_callbacks=None,
                         create_privilege=None, edit_own_privilege=None,
                         edit_other_privilege=None):
        """Register a view handler for a content type."""
        self.content_type_handlers[content_type] = callback
        if admin_callbacks is not None:
            self.admin_content_type_handlers[content_type] = admin_callbacks
        self.content_type_privileges[content_type] = (
            create_privilege,
            edit_own_privilege,
            edit_other_privilege
        )

    @setuponly
    def add_parser(self, name, class_):
        """Add a new parser class.  This parser has to be a subclass of
        :class:`zine.parsers.BaseParser`.
        """
        self.parsers[name] = class_(self)

    @setuponly
    def add_zeml_element_handler(self, element_handler):
        """Register a new ZEML element handler."""
        self.zeml_element_handlers.append(element_handler(self))

    @setuponly
    def add_widget(self, widget):
        """Add a widget."""
        self.widgets[widget.name] = widget

    @setuponly
    def add_servicepoint(self, identifier, callback):
        """Add a new function as servicepoint.  A service point is a function
        that is called by an external non-human interface such as an
        JavaScript or XMLRPC client.  It's automatically exposed to all
        service interfaces.
        """
        self._services[identifier] = callback

    @setuponly
    def add_privilege(self, privilege):
        """Registers a new privilege."""
        self.privileges[privilege.name] = privilege

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

    def list_parsers(self):
        """Return a sorted list of parsers (parser_id, parser_name)."""
        # we call unicode to resolve the translations once.  parser.name
        # will very likely be a lazy translation
        return sorted([(key, unicode(parser.name)) for key, parser in
                       self.parsers.iteritems()], key=lambda x: x[1].lower())

    def list_privileges(self):
        """Return a sorted list of privileges."""
        # TODO: somehow add grouping...
        result = [(x.name, unicode(x.explanation)) for x in
                  self.privileges.values()]
        result.sort(key=lambda x: x[0] == 'BLOG_ADMIN' or x[1].lower())
        return result

    def get_page_metadata(self):
        """Return the metadata as HTML part for templates.  This is normally
        called by the layout template to get the metadata for the head section.
        """
        from zine.utils import dump_json
        generators = {'script': htmlhelpers.script, 'meta': htmlhelpers.meta,
                      'link': htmlhelpers.link, 'snippet': lambda html: html}
        result = [
            htmlhelpers.meta(name='generator', content='Zine'),
            htmlhelpers.link('EditURI', url_for('blog/service_rsd'),
                             type='application/rsd+xml', title='RSD'),
            htmlhelpers.script(url_for('core/shared', filename='js/jQuery.js')),
            htmlhelpers.script(url_for('core/shared', filename='js/Zine.js')),
            htmlhelpers.script(url_for('blog/serve_translations'))
        ]

        # the url information.  Only expose the admin url for admin users
        # or calls to this method without a request.
        base_url = self.cfg['blog_url'].rstrip('/')
        request = get_request()
        javascript = [
            'Zine.ROOT_URL = %s' % dump_json(base_url),
            'Zine.BLOG_URL = %s' % dump_json(base_url + self.cfg['blog_url_prefix'])
        ]
        if request is None or request.user.is_manager:
            javascript.append('Zine.ADMIN_URL = %s' %
                              dump_json(base_url + self.cfg['admin_url_prefix']))
        result.append(u'<script type="text/javascript">%s;</script>' %
                      '; '.join(javascript))

        for type, attr in local.page_metadata:
            result.append(generators[type](**attr))

        #! this is called before the page metadata is assembled with
        #! the list of already collected metadata.  You can extend the
        #! list in place to add some more html snippets to the page header.
        emit_event('before-metadata-assembled', result)
        return u'\n'.join(result)

    def handle_not_found(self, request, exception):
        """Handle a not found exception.  This also dispatches to plugins
        that listen for for absolute urls.  See `add_absolute_url` for
        details.
        """
        for handler in self._absolute_url_handlers:
            try:
                rv = handler(request)
                if rv is not None:
                    return rv
            except NotFound:
                # a not found exception has the same effect as returning
                # None.  The next handler is processed.  All other http
                # exceptions are passed trough.
                pass
        response = render_response('404.html')
        response.status_code = 404
        return response

    def handle_server_error(self, request, exc_info=None, suppress_log=False):
        """Called if a server error happens.  Logs the error and returns a
        response with an error message.
        """
        if not suppress_log:
            log.exception('Exception happened at "%s"' % request.path,
                          'core', exc_info)
        response = render_response('500.html')
        response.status_code = 500
        return response

    def handle_internal_error(self, request, error):
        """Called if internal errors are caught."""
        if request.user.is_admin:
            response = render_response('internal_error.html', error=error)
            response.status_code = 500
            return response
        return self.handle_server_error(request, suppress_log=True)

    def dispatch_request(self, request):
        #! the after-request-setup event can return a response
        #! or modify the request object in place. If we have a
        #! response we just send it, no other modifications are done.
        for callback in iter_listeners('after-request-setup'):
            result = callback(request)
            if result is not None:
                return result(environ, start_response)

        # normal request dispatching
        try:
            try:
                endpoint, args = self.url_adapter.match(request.path)
                response = self.views[endpoint](request, **args)
            except NotFound, e:
                response = self.handle_not_found(request, e)
            except Forbidden, e:
                if request.user.is_somebody:
                    response = render_response('403.html')
                    response.status_code = 403
                else:
                    response = _redirect(url_for('admin/login',
                                                 next=request.path))
        except HTTPException, e:
            response = e.get_response(request)

        return response

    def dispatch_wsgi(self, environ, start_response):
        """This method is the internal WSGI request and is overridden by
        middlewares applied with :meth:`add_middleware`.  It handles the
        actual request dispatching.
        """
        # Create a new request object, register it with the application
        # and all the other stuff on the current thread but initialize
        # it afterwards.  We do this so that the request object can query
        # the database in the initialization method.
        request = object.__new__(Request)
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
            if not request.user.is_admin:
                response = render_response('maintenance.html')
                response.status_code = 503
                return response(environ, start_response)

        # wrap the real dispatching in a try/except so that we can
        # intercept exceptions that happen in the application.
        try:
            response = self.dispatch_request(request)

            # make sure the response object is one of ours
            response = Response.force_type(response, environ)

            #! allow plugins to change the response object
            for callback in iter_listeners('before-response-processed'):
                result = callback(response)
                if result is not None:
                    response = result
        except InternalError, e:
            response = self.handle_internal_error(request, e)
        except:
            if self.cfg['passthrough_errors']:
                raise
            response = self.handle_server_error(request)

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
        return ClosingIterator(self.dispatch_wsgi(environ, start_response),
                               [local_manager.cleanup, cleanup_session])

    def __repr__(self):
        return '<Zine %r [%s]>' % (
            self.instance_folder,
            self.iid
        )

    # remove our decorator
    del setuponly


# import here because of circular dependencies
from zine import i18n
from zine.utils import log
from zine.utils.http import make_external_url
