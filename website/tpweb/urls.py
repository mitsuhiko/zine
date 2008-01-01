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
    Rule('/about/features', endpoint='about/features.html'),
    Rule('/about/requirements', endpoint='about/requirements.html'),
    Rule('/about/screenshots/', endpoint='about/screenshots.html'),
    Rule('/about/screenshots/<screenshot>', endpoint='about/screenshots.html'),
    Rule('/about/faq', endpoint='about/faq.html'),
    Rule('/about/license', endpoint='about/license.html'),
    Rule('/about/team', endpoint='about/team.html'),
    Rule('/about/inspiration', endpoint='about/inspiration.html'),

    Rule('/documentation/', defaults={'slug': 'overview'},
         endpoint='documentation/show'),
    Rule('/documentation/<path:slug>', endpoint='documentation/show'),
    Rule('/documentation/extend/', defaults={'slug': 'extend/intro'},
         endpoint='documentation/show'),

    Rule('/extend/', endpoint='extend/index.html'),
    Rule('/download', endpoint='download.html'),

    Rule('/community/', endpoint='community/index.html'),
    Rule('/community/irc', endpoint='community/irc.html'),
    Rule('/community/planet/', defaults={'page': 1},
         endpoint='community/planet'),
    Rule('/community/planet/page/<int:page>', endpoint='community/planet'),
    Rule('/community/planet/feed.atom', endpoint='community/planet_feed'),

    Rule('/shared/<file>', endpoint='shared', build_only=True)
])


# special endpoint handlers.  These are functions accepting a request
# object and some keyword arguments for the url values.  If no handler
# exists for an endpoint the template with the name of the template is
# loaded and the URL parameters are passed to the context of the template.
from tpweb import dochelpers, planet
handlers = {
    'documentation/show':       dochelpers.show_page,
    'community/planet':         planet.show_index,
    'community/planet_feed':    planet.get_feed
}
