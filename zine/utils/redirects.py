# -*- coding: utf-8 -*-
"""
    zine.utils.redirects
    ~~~~~~~~~~~~~~~~~~~~

    This module implements the access to the redirect table.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from urlparse import urlparse

from zine.application import get_application
from zine.database import redirects, db
from zine.utils.http import make_external_url


def _strip_url(url):
    """Strip an URL so that only the path is left."""
    cfg = get_application().cfg
    if url.startswith(cfg['blog_url']):
        url = url[len(cfg['blog_url']):]
    return url.lstrip('/')


def lookup_redirect(url):
    """Looks up a redirect.  If there is not redirect for the given URL,
    the return value is `None`.
    """
    row = db.execute(redirects.select(
        redirects.c.original == _strip_url(url)
    )).fetchone()
    if row:
        return make_external_url(row.new)


def register_redirect(original, new_url):
    """Register a new redirect."""
    db.execute(redirects.insert(), dict(
        original=_strip_url(original),
        new=_strip_url(new_url)
    ))


def unregister_redirect(url):
    """Unregister a redirect."""
    rv = db.execute(redirects.delete(redirects.c.original == _strip_url(url)))
    if not rv.rowcount:
        raise ValueError('no such URL')


def get_redirect_map():
    """Return a dict of all redirects."""
    return dict((row.original, make_external_url(row.new)) for row in
                db.execute(redirects.select()))
