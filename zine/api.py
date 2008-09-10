# -*- coding: utf-8 -*-
"""
    zine.api
    ~~~~~~~~

    Module for plugins and core. Star import this to get
    access to all the important helper functions.

    :copyright: 2007-2008 by Armin Ronacher.
    :license: GNU GPL.
"""

from zine.application import (
    # Event handling
    emit_event, iter_listeners,

    # Request/Response
    Response, get_request, url_for, shared_url, add_link, add_meta,
    add_script, add_header_snippet,

    # View helpers
    require_role,

    # Template helpers
    render_template, render_response,

    # Appliation helpers
    get_application
)

# Database
from zine.database import db

# Cache
from zine import cache

# Gettext
from zine.i18n import gettext, ngettext, lazy_gettext, lazy_ngettext, _

# Plugin syste
from zine.pluginsystem import SetupError


__all__ = list(x for x in locals() if x == '_' or not x.startswith('_'))
