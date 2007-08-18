# -*- coding: utf-8 -*-
"""
    textpress.urls
    ~~~~~~~~~~~~~~

    The core url rules.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from werkzeug.routing import Rule, Submount

all_urls = [
    Rule('/', defaults={'page': 1}, endpoint='blog/index'),
    Rule('/feed.atom', endpoint='blog/atom_feed'),
    Rule('/page/<int:page>', endpoint='blog/index'),
    Submount('/authors', [
        Rule('/', endpoint='blog/authors'),
        Rule('/<string:username>', defaults={'page': 1}, endpoint='blog/show_author'),
        Rule('/<string:username>/page/<int:page>', endpoint='blog/show_author'),
        Rule('/<string:author>/feed.atom', endpoint='blog/atom_feed'),
    ]),
    Submount('/tags', [
        Rule('/', endpoint='blog/tag_cloud'),
        Rule('/<string:slug>', defaults={'page': 1}, endpoint='blog/show_tag'),
        Rule('/<string:slug>/page/<int:page>', endpoint='blog/show_tag'),
        Rule('/<string:tag>/feed.atom', endpoint='blog/atom_feed'),
    ]),
    Rule('/_services/', endpoint='blog/service_rsd'),
    Rule('/_services/json/<path:identifier>', endpoint='blog/json_service'),
    Rule('/_services/xml/<path:identifier>', endpoint='blog/xml_service'),
    Submount('/admin', [
        Rule('/', endpoint='admin/index'),
        Rule('/login', endpoint='admin/login'),
        Rule('/logout', endpoint='admin/logout'),
        Rule('/posts/', endpoint='admin/show_posts'),
        Rule('/posts/new', endpoint='admin/new_post'),
        Rule('/posts/<int:post_id>', endpoint='admin/edit_post'),
        Rule('/posts/<int:post_id>/delete', endpoint='admin/delete_post'),
        Rule('/posts/<int:post_id>/comments', endpoint='admin/show_comments'),
        Rule('/comments/', endpoint='admin/show_comments'),
        Rule('/comments/<int:comment_id>', endpoint='admin/edit_comment'),
        Rule('/comments/<int:comment_id>/delete', endpoint='admin/delete_comment'),
        Rule('/tags/', endpoint='admin/show_tags'),
        Rule('/tags/new', endpoint='admin/new_tag'),
        Rule('/tags/<int:tag_id>', endpoint='admin/edit_tag'),
        Rule('/tags/<int:tag_id>/delete', endpoint='admin/delete_tag'),
        Rule('/users/', endpoint='admin/show_users'),
        Rule('/users/new', endpoint='admin/new_user'),
        Rule('/users/<int:user_id>', endpoint='admin/edit_user'),
        Rule('/users/<int:user_id>/delete', endpoint='admin/delete_user'),
        Rule('/options/', endpoint='admin/options'),
        Rule('/options/basic', endpoint='admin/basic_options'),
        Rule('/options/theme', endpoint='admin/theme'),
        Rule('/options/plugins', endpoint='admin/plugins'),
        Rule('/options/configuration', endpoint='admin/configuration'),
        Rule('/about/', endpoint='admin/about'),
        Rule('/about/eventmap', endpoint='admin/eventmap'),
        Rule('/about/textpress', endpoint='admin/about_textpress'),
        Rule('/change_password', endpoint='admin/change_password')
    ])
]

# add the more complex url rule for archive and show post
tmp = '/'
for digits, part in [(4, 'year'), (2, 'month'), (2, 'day')]:
    tmp += '<int(fixed_digits=%d):%s>/' % (digits, part)
    all_urls.extend([
        Rule(tmp, defaults={'page': 1}, endpoint='blog/archive'),
        Rule(tmp + 'page/<int:page>', endpoint='blog/archive'),
        Rule(tmp + 'feed.atom', endpoint='blog/atom_feed')
    ])
all_urls.extend([
    Rule(tmp + '<slug>', endpoint='blog/show_post'),
    Rule(tmp + '<post_slug>/feed.atom', endpoint='blog/atom_feed')
])

del tmp, part
