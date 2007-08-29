# -*- coding: utf-8 -*-
"""
    textpress.websetup.framework
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module brings the helper functions and classes for the websetup.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os import path

from werkzeug.wrappers import BaseRequest, BaseResponse
from werkzeug.utils import get_current_url
from jinja import Environment, FileSystemLoader


template_path = path.join(path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path))


class Request(BaseRequest):
    """simple request object that works even if the app is not installed."""
    charset = 'utf-8'


class Response(BaseResponse):
    """Small response class for the websetup."""
    charset = 'utf-8'


def render_response(template_name, context):
    tmpl = jinja_env.get_template(template_name)
    return Response(tmpl.render(context), mimetype='text/html')


def redirect(environ, target):
    url = get_current_url(environ, root_only=True).rstrip('/') + target
    resp = Response('redirecting to %s...' % url, mimetype='text/plain',
                    status=302)
    resp.headers['Location'] = url
    return resp
