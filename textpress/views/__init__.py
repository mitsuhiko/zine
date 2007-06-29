# -*- coding: utf-8 -*-
"""
    textpress.views
    ~~~~~~~~~~~~~~~

    Get all the core views into a list.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.views import blog, admin


#: bind the views to url endpoints
all_views = {
    # blog views
    'blog/index':           blog.do_index,
    'blog/archive':         blog.do_archive,
    'blog/show_tag':        blog.do_show_tag,
    'blog/tag_cloud':       blog.do_show_tag_cloud,
    'blog/show_post':       blog.do_show_post,
    'blog/show_author':     blog.do_show_author,
    'blog/authors':         blog.do_authors,
    'blog/service_rsd':     blog.do_service_rsd,
    'blog/atom_feed':       blog.do_atom_feed,

    # admin views
    'admin/index':          admin.do_index,
    'admin/show_posts':     admin.do_show_posts,
    'admin/new_post':       admin.do_edit_post,
    'admin/edit_post':      admin.do_edit_post,
    'admin/show_tags':      admin.do_show_tags,
    'admin/new_tag':        admin.do_edit_tag,
    'admin/edit_tag':       admin.do_edit_tag,
    'admin/login':          admin.do_login,
    'admin/logout':         admin.do_logout
}
