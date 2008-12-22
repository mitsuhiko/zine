# -*- coding: utf-8 -*-
"""
    zine.views
    ~~~~~~~~~~

    This module binds all the endpoints specified in `zine.urls` to
    python functions in the view modules.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: BSD, see LICENSE for more details.
"""
from zine.views import blog, admin
from zine import i18n


#: bind the views to url endpoints
all_views = {
    # blog views
    'blog/index':               blog.index,
    'blog/archive':             blog.archive,
    'blog/show_category':       blog.show_category,
    'blog/show_tag':            blog.show_tag,
    'blog/show_author':         blog.show_author,
    'blog/authors':             blog.authors,
    'blog/service_rsd':         blog.service_rsd,
    'blog/json_service':        blog.json_service,
    'blog/xml_service':         blog.xml_service,
    'blog/atom_feed':           blog.atom_feed,
    'blog/serve_translations':  i18n.serve_javascript,

    # admin views
    'admin/index':              admin.index,
    'admin/bookmarklet':        admin.bookmarklet,
    'admin/new_entry':          admin.edit_entry,
    'admin/manage_entries':     admin.manage_entries,
    'admin/new_page':           admin.edit_page,
    'admin/manage_pages':       admin.manage_pages,
    'admin/edit_post':          admin.dispatch_post_edit,
    'admin/delete_post':        admin.dispatch_post_delete,
    'admin/manage_comments':    admin.manage_comments,
    'admin/show_unmoderated_comments': admin.show_unmoderated_comments,
    'admin/show_spam_comments': admin.show_spam_comments,
    'admin/show_post_comments': admin.show_post_comments,
    'admin/edit_comment':       admin.edit_comment,
    'admin/delete_comment':     admin.delete_comment,
    'admin/approve_comment':    admin.approve_comment,
    'admin/block_comment':      admin.block_comment,
    'admin/manage_categories':  admin.manage_categories,
    'admin/new_category':       admin.edit_category,
    'admin/edit_category':      admin.edit_category,
    'admin/delete_category':    admin.delete_category,
    'admin/manage_users':       admin.manage_users,
    'admin/new_user':           admin.edit_user,
    'admin/edit_user':          admin.edit_user,
    'admin/delete_user':        admin.delete_user,
    'admin/manage_groups':      admin.manage_groups,
    'admin/new_group':          admin.edit_group,
    'admin/edit_group':         admin.edit_group,
    'admin/delete_group':       admin.delete_group,
    'admin/options':            admin.options,
    'admin/basic_options':      admin.basic_options,
    'admin/urls':               admin.urls,
    'admin/theme':              admin.theme,
    'admin/configure_theme':    admin.configure_theme,
    'admin/plugins':            admin.plugins,
    'admin/remove_plugin':      admin.remove_plugin,
    'admin/cache':              admin.cache,
    'admin/configuration':      admin.configuration,
    'admin/maintenance':        admin.maintenance,
    'admin/import':             admin.import_dump,
    'admin/inspect_import':     admin.inspect_import,
    'admin/delete_import':      admin.delete_import,
    'admin/export':             admin.export,
    'admin/information':        admin.information,
    'admin/log':                admin.log,
    'admin/about_zine':         admin.about_zine,
    'admin/change_password':    admin.change_password,
    'admin/help':               admin.help,
    'admin/login':              admin.login,
    'admin/logout':             admin.logout
}

content_type_handlers = {
    'entry':                    blog.show_entry,
    'page':                     blog.show_page
}

#: the privileges for these content types are defined in zine.privileges
admin_content_type_handlers = {
    'entry': {
        'edit':                 admin.edit_entry,
        'delete':               admin.delete_entry
    },
    'page': {
        'edit':                 admin.edit_page,
        'delete':               admin.delete_page
    }
}

absolute_url_handlers = [blog.dispatch_content_type, blog.handle_redirect]
