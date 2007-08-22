# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.pluginrepo
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module provides a plugin repository for the textpress webpage.
    Users can upload their modules which then are registered automatically
    in the central database.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from textpress.api import *


def do_index(req):
    return render_response('textpress_webpage/plugins.html')
