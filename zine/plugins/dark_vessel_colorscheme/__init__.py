# -*- coding: utf-8 -*-
"""
    zine.plugins.dark_vessel_colorscheme
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    A dark colorscheme for vessel.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD
"""
from os.path import join, dirname
from zine.api import _
from zine.plugins import vessel_theme


SHARED_FILES = join(dirname(__file__), 'shared')


def setup(app, plugin):
    app.add_shared_exports('dark_vessel_colorscheme', SHARED_FILES)
    vessel_theme.add_variation(u'dark_vessel_colorscheme::dark.css', _('Dark'))
