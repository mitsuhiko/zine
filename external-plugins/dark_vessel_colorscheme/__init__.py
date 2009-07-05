# -*- coding: utf-8 -*-
"""
    zine.plugins.dark_vessel_colorscheme
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    A dark colorscheme for vessel.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os.path import join, dirname
from zine.api import _
from zine.plugins import vessel_theme


SHARED_FILES = join(dirname(__file__), 'shared')


def setup(app, plugin):
    app.add_shared_exports('dark_vessel_colorscheme', SHARED_FILES)
    vessel_theme.add_variation(u'dark_vessel_colorscheme::dark.css', _('Dark'))
