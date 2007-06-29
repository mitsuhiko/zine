# -*- coding: utf-8 -*-
"""
    textpress.views
    ~~~~~~~~~~~~~~~

    This module implements all the views (some people call that controller)
    for the core module.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.models import Post, get_post_list


def do_index(req, page):
    return render_response('index.html', **get_post_list(page=page))


def do_archive(req, year=None, month=None, day=None, page=1):
    data = get_post_list(year, month, day, page)
    if data['probably_404']:
        abort(404)
    return render_response('archive.html', **data)


def do_show_post(req, year, month, day, slug):
    post = Post.by_timestamp_and_slug(year, month, day, slug)
    if post is None:
        abort(404)
    elif not post.can_access():
        abort(403)
    return render_response('show_post.html',
        post=post
    )
