# -*- coding: utf-8 -*-
"""
    zine.plugins.vessel_theme
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    A simple default theme that also showcases some of the more advanced
    features of the Zine theme system.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD
"""
from os.path import join, dirname
from zine.api import url_for, _
from zine.views.admin import render_admin_response
from zine.utils.admin import flash
from zine.utils import forms


TEMPLATE_FILES = join(dirname(__file__), 'templates')
SHARED_FILES = join(dirname(__file__), 'shared')


blue_variation = u'vessel_theme::blue.css'
variations = {
    blue_variation:             _('Blue'),
    u'vessel_theme::gray.css':  _('Gray'),
    u'vessel_theme::green.css': _('Green')
}


class ConfigurationForm(forms.Form):
    """Very simple form for the variation selection."""
    variation = forms.ChoiceField(_('Color variation'))

    def __init__(self, initial=None):
        forms.Form.__init__(self, initial)
        choices = sorted(variations.items(), key=lambda x: x[1].lower())
        self.fields['variation'].choices = choices


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
    form = ConfigurationForm(initial=dict(
        variation=cfg['vessel_theme/variation']
    ))

    if request.method == 'POST':
        if 'cancel' in request.form:
            return form.redirect('admin/theme')
        elif form.validate(request.form):
            flash(_('Color variation changed successfully.'), 'configure')
            cfg.change_single('vessel_theme/variation', form['variation'])
            return form.redirect('admin/theme')

    return render_admin_response('admin/configure_vessel_theme.html',
                                 'options.theme', form=form.as_widget())


def setup(app, plugin):
    app.add_theme('vessel', TEMPLATE_FILES, plugin.metadata,
                  configuration_page=configure)
    app.add_shared_exports('vessel_theme', SHARED_FILES)
    app.add_config_var('vessel_theme/variation', forms.TextField(), blue_variation)
