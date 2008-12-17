# -*- coding: utf-8 -*-
"""
    zine.plugins.eric_the_fish
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Annoying fish for the admin panel.  This is somewhat of an demonstration
    plugin because it uses quite a lot of the internal signaling and
    registration system.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from os.path import dirname, join
from random import choice

# the API gives us access to a bunch of functions useful for plugins. The
# api module just acts as an collection module which is save to star import.
# the objects' implementations are in different modules.
from zine.api import *

# because we want to add an admin panel page for our fish we need the
# render_admin_response function that works like the normal render_response
# function, but it assembles a navigation bar for the admin layout template
# and emits the `modify-admin-navigation-bar` event also use here.
from zine.views.admin import render_admin_response

# the following method is used to show notifications in the admin panel.
from zine.utils.admin import flash

# this function is used for redirecting the user to another page
from zine.utils.http import redirect

# Because our fish uses JSON and JavaScript we use the dump_json function
# from the utils module.
from zine.utils import dump_json

# the following exception is raised when the config could not be changed
from zine.config import ConfigurationTransactionError

# we only want the admin to be able to configure eric. so we need the
# BLOG_ADMIN privilege
from zine.privileges import BLOG_ADMIN

# the last thing is importing the FORTUNES list from the fortunes.py file
# from the same folder. It's just a long list with quotes.
from zine.plugins.eric_the_fish.fortunes import FORTUNES

# because we have an admin panel page we need to store the templates
# somewhere. So here we calculate the path to the templates and save them
# in this global variable.
TEMPLATES = join(dirname(__file__), 'templates')

# here we do the same for the shared files (css, fish images and javascript)
SHARED_FILES = join(dirname(__file__), 'shared')

# and that's just the list of skins we have.
SKINS = 'blue green pink red yellow'.split()


def inject_fish(req, context):
    """This is called before the admin response is rendered. We add the
    fish script and the stylesheet and then we add a new header snippet
    which basically is some HTML code that is added to the <head> section.
    In this header snippet we set the global `$ERIC_THE_FISH_SKIN` variable
    to the selected skin.
    """
    add_script(url_for('eric_the_fish/shared', filename='fish.js'))
    add_link('stylesheet', url_for('eric_the_fish/shared',
                                   filename='fish.css'), 'text/css')

    add_header_snippet(
        '<script type="text/javascript">'
            '$ERIC_THE_FISH_SKIN = %s;'
        '</script>' % dump_json(req.app.cfg['eric_the_fish/skin'])
    )


def add_eric_link(req, navigation_bar):
    """Called during the admin navigation bar setup. When the options menu is
    traversed we insert our eric the fish link before the plugins link.
    The outermost is the configuration editor, the next one the plugins
    link and then we add our fish link.
    """
    if not req.user.has_privilege(BLOG_ADMIN):
        return
    for link_id, url, title, children in navigation_bar:
        if link_id == 'options':
            children.insert(-3, ('eric_the_fish', url_for('eric_the_fish/config'),
                                 _('Eric The Fish')))


@require_privilege(BLOG_ADMIN)
def show_eric_options(req):
    """This renders the eric admin panel. Allow switching the skin and show
    the available skins.
    """
    new_skin = req.args.get('select')
    if new_skin in SKINS:
        try:
            req.app.cfg.change_single('eric_the_fish/skin', new_skin)
        except ConfigurationTransactionError, e:
            flash(_('The skin could not be changed.'), 'error')
        return redirect(url_for('eric_the_fish/config'))

    return render_admin_response('admin/eric_the_fish.html',
                                 'options.eric_the_fish',
        skins=[{
            'name':     skin,
            'active':   skin == req.app.cfg['eric_the_fish/skin']
        } for skin in SKINS]
    )


def get_fortune(req):
    """The servicepoint function. Just return one fortune from the list."""
    return {'fortune': choice(FORTUNES)}


def setup(app, plugin):
    """This function is called by Zine in the application initialization
    phase. Here we connect to the events and register our template paths,
    url rules, views etc.
    """

    # we want our fish to appear in the admin panel, so hook into the
    # correct event.
    app.connect_event('before-admin-response-rendered', inject_fish)

    # for our admin panel page we also add a link to the navigation bar.
    app.connect_event('modify-admin-navigation-bar', add_eric_link)

    # our fish has a configurable skin. So we register one for it which
    # defaults to blue.
    app.add_config_var('eric_the_fish/skin', unicode, 'blue')

    # then we add some shared exports for the fish which points to the
    # shared files location from above. There we have all the CSS files
    # and static stuff.
    app.add_shared_exports('eric_the_fish', SHARED_FILES)

    # Whenever we click on the fish we want a quote to appear. Because the
    # quotes are stored on the server we add a servicepoint that sends one
    # quote back. Zine provides JSON and XML export for this servicepoint
    # automatically, plugins may add more export formats.
    app.add_servicepoint('eric_the_fish/get_fortune', get_fortune)

    # for the admin panel we add a url rule. Because it's an admin panel
    # page located in options we add such an url rule.
    app.add_url_rule('/options/eric-the-fish', prefix='admin',
                     endpoint='eric_the_fish/config',
                     view=show_eric_options)

    # add our templates to the searchpath so that Zine can find the
    # admin panel template for the fish config panel.
    app.add_template_searchpath(TEMPLATES)
