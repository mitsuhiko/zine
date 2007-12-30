# -*- coding: utf-8 -*-
"""
    tpweb.application
    ~~~~~~~~~~~~~~~~~

    TextPress webpage WSGI application.  Just a simple PHP like application
    that uses mako templates all over the place, and some nice werkzeug
    powered URL matching.

    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from os import path
from mako.lookup import TemplateLookup
from werkzeug import BaseRequest, BaseResponse, SharedDataMiddleware
from werkzeug.exceptions import HTTPException, NotFound


ROOT = path.realpath(path.dirname(__file__))
metadata = MetaData()
session = scoped_session(sessionmaker(autoflush=True, transactional=True))
configuration = {}
template_lookup = TemplateLookup(
    directories=[path.join(ROOT, 'templates')],
    input_encoding='utf-8'
)


def render_to_response(request, template_name, context, status=200):
    """Render a template into a response object."""
    template = template_lookup.get_template(template_name)
    response = BaseResponse(status=status, mimetype='text/html')
    context.update(
        url_for=lambda e, **v: request.url_adapter.build(e, v),
        template=template_name,
        request=request,
        response=response,
        NotFound=NotFound
    )
    response.write(template.render_unicode(**context))
    return response


def handle_request(request):
    """Handle a request and return a response object."""
    try:
        endpoint, values = request.url_adapter.match(request.path)
        request.endpoint = endpoint
        if endpoint in handlers:
            return handlers[endpoint](request, **values)
        return render_to_response(request, endpoint, values, 200)
    except NotFound:
        return render_to_response(request, 'not_found.html', {}, 404)
    except HTTPException, e:
        return e


def wsgi_app(environ, start_response):
    """Handle the low level WSGI stuff."""
    request = BaseRequest(environ)
    request.url_adapter = url_map.bind_to_environ(environ)
    try:
        return handle_request(request)(environ, start_response)
    finally:
        session.remove()


def configure(**options):
    """Update the configuration."""
    configuration.update(options)
    metadata.bind = create_engine(configuration['database_uri'],
                                  convert_unicode=True)


def init_database():
    """Initialize the database."""
    import tpweb.planet
    metadata.create_all()


# import the handlers and url map here to avoid circular dependencies
from tpweb.urls import url_map, handlers

# create the WSGI application object.
application = SharedDataMiddleware(wsgi_app, {
    '/shared':  path.join(ROOT, 'shared')
})
