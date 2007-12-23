# -*- coding: utf-8 -*-
"""
    textpress.websetup.framework
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module brings the helper functions and classes for the websetup.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os import path

from werkzeug import BaseRequest as Request, BaseResponse as Response, \
     get_current_url, redirect
from jinja import Environment, FileSystemLoader


template_path = path.join(path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_path))


def render_response(template_name, context):
    tmpl = jinja_env.get_template(template_name)
    return Response(tmpl.render(context), mimetype='text/html')


def get_blog_url(req):
    return get_current_url(req.environ, root_only=True)
