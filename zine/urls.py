# -*- coding: utf-8 -*-
"""
    zine.urls
    ~~~~~~~~~

    This module implements a function that creates a list of urls for all
    the core components.

    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: GNU GPL.
"""
from werkzeug.routing import Rule, Submount


def make_urls(app):
    """Make the URLs for a new zine application."""
    blog_urls = [
        Rule('/', defaults={'page': 1}, endpoint='blog/index'),
        Rule('/feed.atom', endpoint='blog/atom_feed'),
        Rule('/page/<int:page>', endpoint='blog/index'),
        Rule('/archive', endpoint='blog/archive'),
        Submount(app.cfg['profiles_url_prefix'], [
            Rule('/', endpoint='blog/authors'),
            Rule('/<string:username>', defaults={'page': 1}, endpoint='blog/show_author'),
            Rule('/<string:username>/page/<int:page>', endpoint='blog/show_author'),
            Rule('/<string:author>/feed.atom', endpoint='blog/atom_feed'),
        ]),
        Submount(app.cfg['category_url_prefix'], [
            Rule('/<string:slug>', defaults={'page': 1}, endpoint='blog/show_category'),
            Rule('/<string:slug>/page/<int:page>', endpoint='blog/show_category'),
            Rule('/<string:category>/feed.atom', endpoint='blog/atom_feed')
        ]),
        Submount(app.cfg['tags_url_prefix'], [
            Rule('/<string:slug>', defaults={'page': 1}, endpoint='blog/show_tag'),
            Rule('/<string:slug>/page/<int:page>', endpoint='blog/show_tag'),
            Rule('/<string:tag>/feed.atom', endpoint='blog/atom_feed')
        ])
    ]
    admin_urls = [
        Rule('/', endpoint='admin/index'),
        Rule('/login', endpoint='admin/login'),
        Rule('/logout', endpoint='admin/logout'),
        Rule('/_bookmarklet', endpoint='admin/bookmarklet'),
        Rule('/entries/', endpoint='admin/manage_entries', defaults={'page': 1}),
        Rule('/entries/page/<int:page>', endpoint='admin/manage_entries'),
        Rule('/entries/new', endpoint='admin/new_entry'),
        Rule('/pages/', endpoint='admin/manage_pages', defaults={'page': 1}),
        Rule('/pages/page/<int:page>', endpoint='admin/manage_pages'),
        Rule('/pages/new', endpoint='admin/new_page'),
        Rule('/p/<int:post_id>', endpoint='admin/edit_post'),
        Rule('/p/<int:post_id>/delete', endpoint='admin/delete_post'),
        Rule('/p/<int:post_id>/comments',
             endpoint='admin/show_post_comments', defaults={'page': 1}),
        Rule('/comments/', endpoint='admin/show_comments', defaults={'page': 1}),
        Rule('/comments/page/<int:page>', endpoint='admin/show_comments'),
        Rule('/comments/unmoderated', defaults={'page': 1},
             endpoint='admin/show_unmoderated_comments'),
        Rule('/comments/unmoderated/page/<int:page>',
             endpoint='admin/show_unmoderated_comments'),
        Rule('/comments/spam', defaults={'page': 1},
             endpoint='admin/show_spam_comments'),
        Rule('/comments/spam/page/<int:page>', endpoint='admin/show_spam_comments'),
        Rule('/comments/<int:comment_id>', endpoint='admin/edit_comment'),
        Rule('/comments/<int:comment_id>/delete', endpoint='admin/delete_comment'),
        Rule('/comments/<int:comment_id>/approve', endpoint='admin/approve_comment'),
        Rule('/comments/<int:comment_id>/block', endpoint='admin/block_comment'),
        Rule('/categories/', endpoint='admin/manage_categories', defaults={'page': 1}),
        Rule('/categories/page/<int:page>', endpoint='admin/manage_categories'),
        Rule('/categories/new', endpoint='admin/new_category'),
        Rule('/categories/<int:category_id>', endpoint='admin/edit_category'),
        Rule('/categories/<int:category_id>/delete', endpoint='admin/delete_category'),
        Rule('/users/', endpoint='admin/manage_users', defaults={'page': 1}),
        Rule('/users/page/<int:page>', endpoint='admin/manage_users'),
        Rule('/users/new', endpoint='admin/new_user'),
        Rule('/users/<int:user_id>', endpoint='admin/edit_user'),
        Rule('/users/<int:user_id>/delete', endpoint='admin/delete_user'),
        Rule('/uploads/', endpoint='admin/browse_uploads'),
        Rule('/uploads/new', endpoint='admin/new_upload'),
        Rule('/uploads/thumbnailer', endpoint='admin/upload_thumbnailer'),
        Rule('/options/', endpoint='admin/options'),
        Rule('/options/basic', endpoint='admin/basic_options'),
        Rule('/options/urls', endpoint='admin/urls'),
        Rule('/options/theme/', endpoint='admin/theme'),
        Rule('/options/theme/configure', endpoint='admin/configure_theme'),
        Rule('/options/uploads', endpoint='admin/upload_config'),
        Rule('/options/plugins/', endpoint='admin/plugins'),
        Rule('/options/plugins/<plugin>/remove', endpoint='admin/remove_plugin'),
        Rule('/options/cache', endpoint='admin/cache'),
        Rule('/system/', endpoint='admin/information'),
        Rule('/system/maintenance/', endpoint='admin/maintenance'),
        Rule('/system/log', defaults={'page': 1}, endpoint='admin/log'),
        Rule('/system/log/page/<int:page>', endpoint='admin/log'),
        Rule('/system/import/', endpoint='admin/import'),
        Rule('/system/import/<int:id>', endpoint='admin/inspect_import'),
        Rule('/system/import/<int:id>/delete', endpoint='admin/delete_import'),
        Rule('/system/export', endpoint='admin/export'),
        Rule('/system/about', endpoint='admin/about_zine'),
        Rule('/system/help/', endpoint='admin/help'),
        Rule('/system/help/<path:page>', endpoint='admin/help'),
        Rule('/system/configuration', endpoint='admin/configuration'),
        Rule('/change_password', endpoint='admin/change_password')
    ]
    other_urls = [
        Rule('/_services/', endpoint='blog/service_rsd'),
        Rule('/_services/json/<path:identifier>', endpoint='blog/json_service'),
        Rule('/_services/xml/<path:identifier>', endpoint='blog/xml_service'),
        Rule('/_translations.js', endpoint='blog/serve_translations'),
        Rule('/_uploads/<filename>', endpoint='blog/get_uploaded_file'),
        Rule('/_uploads/<filename>/delete', endpoint='admin/delete_upload')
    ]

    # add the more complex url rule for archive and show post
    tmp = '/'
    for digits, part in [(4, 'year'), (2, 'month'), (2, 'day')]:
        tmp += '<int(fixed_digits=%d):%s>/' % (digits, part)
        blog_urls.extend([
            Rule(tmp, defaults={'page': 1}, endpoint='blog/archive'),
            Rule(tmp + 'page/<int:page>', endpoint='blog/archive'),
            Rule(tmp + 'feed.atom', endpoint='blog/atom_feed')
        ])

    return [
        Submount(app.cfg['blog_url_prefix'], blog_urls),
        Submount(app.cfg['admin_url_prefix'], admin_urls)
    ] + other_urls
