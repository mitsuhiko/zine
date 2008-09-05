# -*- coding: utf-8 -*-
"""
    zine.plugins.vessel_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    A simple default theme that also showcases some of the more advanced
    features of the Zine theme system.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname
from zine.api import redirect, url_for, _
from zine.views.admin import render_admin_response
from zine.utils.admin import flash
from zine.utils.xxx import CSRFProtector


TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')


blue_variation = 'vessel_theme::blue.css'
variations = {
    blue_variation:             _('Blue'),
    'vessel_theme::gray.css':   _('Gray'),
    'vessel_theme::green.css':  _('Green')
}


def add_variation(spec, title):
    """Registers a new variation."""
    variations[spec] = title


def configure(request):
    """This callback is called from the admin panel if the theme configuration
    page is opened.  Because only the active theme can be configured it's
    perfectly okay to ship the template for the configuration page as part of
    the theme template folder.  No need to register a separate template folder
    just for the admin panel template.
    """
    cfg = request.app.cfg
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()
        if 'save' in request.form:
            flash(_('Color variation changed successfully.'), 'configure')
            cfg.change_single('vessel_theme/variation', request.form['variation'])
        return redirect(url_for('admin/theme'))
    return render_admin_response('admin/configure_vessel_theme.html',
                                 'options.theme',
                                 current=cfg['vessel_theme/variation'],
                                 variations=sorted(variations.items(),
                                                   key=lambda x: x[1].lower()),
                                 csrf_protector=csrf_protector)


def setup(app, plugin):
    app.add_theme('vessel', TEMPLATE_FILES, plugin.metadata,
                  configuration_page=configure)
    app.add_shared_exports('vessel_theme', SHARED_FILES)
    app.add_config_var('vessel_theme/variation', unicode, blue_variation)
