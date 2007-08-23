# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.pluginrepo
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module provides a plugin repository for the textpress webpage.
    Users can upload their modules which then are registered automatically
    in the central database.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from base64 import b64decode
from cStringIO import StringIO

from textpress.api import *
from textpress.pluginsystem import get_package_metadata
from textpress.utils import split_email
from textpress.plugins.textpress_webpage.models import Developer, Plugin


def do_index(req):
    return render_response('textpress_webpage/plugins.html',
        plugins=Plugin.select()
    )


def do_show_plugin(req, name):
    plugin = Plugin.get_by(name=name)
    if plugin is None:
        abort(404)
    return render_response('textpress_webpage/show_plugin.html',
        plugin=plugin
    )


def do_upload(req):
    email = req.form.get('email')
    password = req.form.get('password')
    package_data = req.form.get('package_data')
    if email and password and package_data:
        developer = Developer.get_by(email=email)
        if not developer.check_password(password):
            return Response('invalid password', mimetype='text/plain')
        try:
            package_data = b64decode(package_data)
            stream = StringIO(package_data)
            metadata = get_package_metadata(stream)
        except ValueError, e:
            return Response(str(e), mimetype='text/plain')
        if not metadata['uid']:
            return Response('no plugin id', mimetype='text/plain')

        plugin = Plugin.get_or_create(metadata['uid'], developer)
        if plugin is None:
            return Response('plugin associated with other developer')
        author, author_email = split_email(metadata.get('author', ''))
        version = plugin.add_version(
            display_name=metadata.get('name') or metadata['uid'],
            license=metadata.get('license') or 'unknown',
            description=metadata.get('description', ''),
            version=metadata.get('version') or '0.0',
            author=author,
            author_email=author_email,
            author_url=metadata.get('author_url'),
            plugin_url=metadata.get('plugin_url')
        )
        if version is None:
            return Response('version in use')
        db.flush()
        version.write_package(package_data)
        return Response('okay', mimetype='text/plain')
    else:
        return Response('missing parameters', mimetype='text/plain')
