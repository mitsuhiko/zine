# -*- coding: utf-8 -*-
"""
    textpress.api
    ~~~~~~~~~~~~~

    Module for plugins and core. Star import this to get
    access to all the important helper functions.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""

from textpress.application import (
    # Event handling
    emit_event, iter_listeners,

    # Request/Response
    Response, redirect, get_request, url_for, add_link, add_meta,
    add_script, add_header_snippet,

    # View helpers
    require_role,

    # Template helpers
    render_template, render_response,

    # Appliation helpers
    get_application
)

# Database
from textpress.database import db

# Cache
from textpress import cache

# Gettext
from textpress.i18n import gettext, ngettext, _

# Plugin syste
from textpress.pluginsystem import SetupError


__all__ = list(x for x in locals() if x == '_' or not x.startswith('_'))
