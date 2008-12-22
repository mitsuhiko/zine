# -*- coding: utf-8 -*-
"""
    zine.docs
    ~~~~~~~~~~~~~~

    This module implements a simple multilingual documentation system on
    top of docutils.  The `build-documentation` script builds pickled files
    for all the documentation in Zine or a plugin.

    This is separate from the sphinx powered developer documentation.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import re
import os
import cPickle as pickle
from mimetypes import guess_type

from werkzeug import escape

from zine.application import Response, url_for
from zine.i18n import _


_plugin_links_re = re.compile(r'<!-- PLUGIN_LINKS -->')


def _iter_file_choices(app, base, *parts):
    for lang in app.cfg['language'], 'en':
        yield os.path.join(base, lang, *parts) + '.page', False
        yield os.path.join(base, lang, *(parts + ('index.page',))), True


def _find_path(app, parts):
    """Pass it a *list* of parts and it will return the path to the
    path to the requested resource.  The list is modified in place.
    """
    if len(parts) >= 2 and parts[0] == 'plugins':
        plugin = app.plugins.get(parts[1])
        if plugin is not None:
            del parts[:2]
            return os.path.join(plugin.path, 'docs')
    return os.path.dirname(__file__)


def _expand_page(app, page):
    _documented_plugins = []
    def handle_links(match):
        if not _documented_plugins:
            _documented_plugins.append(list_documented_plugins(app))
        return _documented_plugins[0]
    page['body'] = _plugin_links_re.sub(handle_links, page['body'])
    return page


def list_documented_plugins(app):
    """Return a list of all documented plugins."""
    plugins = []
    for plugin in app.plugins.itervalues():
        if plugin.is_documented:
            plugins.append('<li><a href="%s">%s</a></li>' % (
                url_for('admin/help', page='plugins/%s/' % plugin.name),
                escape(plugin.display_name)
            ))
    if not plugins:
        return u'<ul><li>%s</li></ul>' % _('no documented plugins installed.')
    return '<ul>%s</ul>' % '\n'.join(plugins)


def load_page(app, identifier):
    """Load a documentation page.  If the page does not exist the
    return value is `None`.
    """
    parts = identifier.rstrip('/').split('/')

    # no folder or file with a leading dot or the special
    # name "index" is allowed.  Just abort with in that case
    for part in parts:
        if part == 'index' or part[:1] == '.':
            return

    base = _find_path(app, parts)

    for filename, is_index in _iter_file_choices(app, base, *parts):
        if os.path.isfile(filename):
            f = file(filename, 'rb')
            try:
                return _expand_page(app, pickle.load(f)), is_index
            finally:
                f.close()


def get_resource(app, filename):
    """Get a resource as response object."""
    parts = filename.split('/')

    # no folder or file with a leading dot or the special is allowed
    for part in parts:
        if part[:1] == '.':
            return

    base = _find_path(app, parts)

    for filename in os.path.join(base, app.cfg['language'], *parts), \
                    os.path.join(base, 'en', *parts):
        if os.path.isfile(filename):
            f = file(filename, 'rb')
            try:
                return Response(f.read(), mimetype=guess_type(filename)[0] or
                                'application/octet-stram')
            finally:
                f.close()
