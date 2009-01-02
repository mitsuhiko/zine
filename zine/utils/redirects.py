# -*- coding: utf-8 -*-
"""
    zine.utils.redirects
    ~~~~~~~~~~~~~~~~~~~~

    This module implements the access to the redirect table.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
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
    """Register a new redirect.  Also an old one that may still exist."""
    original = _strip_url(original)
    db.execute(redirects.delete(original=original))
    db.execute(redirects.insert(), dict(
        original=original,
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


def change_url_prefix(old, new):
    """Changes a URL prefix from `old` to `new`.  This does not update the
    configuration but renames all slugs there were below the old one and
    puts it to the new and also registers redirects.
    """
    from zine.models import Post

    def _rewrite(s):
        s = s.strip('/')
        if s:
            s += '/'
        return s

    old = _rewrite(old)
    new = _rewrite(new)
    cut_off = len(old)

    posts = Post.query.filter(
        Post.slug.like(old.replace('%', '%%') + '%')
    ).all()

    for post in posts:
        new_slug = new + post.slug[cut_off:]
        register_redirect(post.slug, new_slug)
        post.slug = new_slug
