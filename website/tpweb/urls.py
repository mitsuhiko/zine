# -*- coding: utf-8 -*-
"""
    tbweb.urls
    ~~~~~~~~~~

    The URLs for our public templates.

    :copyright: Copyright 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from werkzeug.routing import Map, Rule


url_map = Map([
    Rule('/', endpoint='index.html'),

    Rule('/about/', endpoint='about/index.html'),
    Rule('/about/requirements', endpoint='about/requirements.html'),
    Rule('/about/screenshots/', endpoint='about/screenshots.html'),
    Rule('/about/screenshots/<screenshot>', endpoint='about/screenshots.html'),
    Rule('/about/faq', endpoint='about/faq.html'),
    Rule('/about/license', endpoint='about/license.html'),
    Rule('/about/team', endpoint='about/team.html'),
    Rule('/about/inspiration', endpoint='about/inspiration.html'),

    Rule('/documentation/', endpoint='documentation/index.html'),
    Rule('/documentation/<path:slug>', endpoint='documentation/show'),
    Rule('/documentation/extend/', defaults={'slug': 'extend/intro'},
         endpoint='documentation/show'),

    Rule('/extend/', endpoint='extend/index.html'),
    Rule('/download', endpoint='download.html'),
    Rule('/shared/<file>', endpoint='shared', build_only=True)
])


# special endpoint handlers.  These are functions accepting a request
# object and some keyword arguments for the url values.  If no handler
# exists for an endpoint the template with the name of the template is
# loaded and the URL parameters are passed to the context of the template.
from tpweb.dochelpers import show_documentation_page
handlers = {
    'documentation/show':       show_documentation_page
}
