# -*- coding: utf-8 -*-
"""
    textpress.plugins.vessel_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Very simple textpress theme.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import join, dirname
from textpress.api import redirect, url_for, lazy_gettext, _
from textpress.views.admin import render_admin_response
from textpress.utils.admin import flash
from textpress.utils.xxx import CSRFProtector


TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')
VARIATIONS = [
    ('blue', lazy_gettext('Blue')),
    ('gray', lazy_gettext('Gray')),
    ('green', lazy_gettext('Green'))
]


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
                                 variations=VARIATIONS,
                                 csrf_protector=csrf_protector)


def setup(app, plugin):
    app.add_theme('vessel', TEMPLATE_FILES, plugin.metadata, configure)
    app.add_shared_exports('vessel_theme', SHARED_FILES)
    app.add_config_var('vessel_theme/variation', unicode, 'blue')
