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
    emit_event,

    # Request/Response
    Response, DirectResponse, abort, redirect, get_request, url_for,
    add_link, add_meta, add_script, add_header_snippet,

    # View helpers
    require_role,

    # Template helpers
    render_template, render_response,

    # Appliation helpers
    get_application
)

# Database
from textpress.database import db

# Gettext
from textpress.utils import gettext as _


__all__ = list(x for x in locals() if x == '_' or not x.startswith('_'))
