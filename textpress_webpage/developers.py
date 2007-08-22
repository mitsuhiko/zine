# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.developers
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The developer central stuff.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from textpress.api import *


def do_register(req):
    return render_response('textpress_webpage/register_developer.html')
