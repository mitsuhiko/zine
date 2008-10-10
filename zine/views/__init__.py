# -*- coding: utf-8 -*-
"""
    zine.views
    ~~~~~~~~~~

    This module binds all the endpoints specified in `zine.urls` to
    python functions in the view modules.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: GNU GPL.
"""
from zine.views import blog, admin
from zine import i18n


#: bind the views to url endpoints
all_views = {
    # blog views
    'blog/index':               blog.do_index,
    'blog/archive':             blog.do_archive,
    'blog/show_category':       blog.do_show_category,
    'blog/show_author':         blog.do_show_author,
    'blog/authors':             blog.do_authors,
    'blog/service_rsd':         blog.do_service_rsd,
    'blog/json_service':        blog.do_json_service,
    'blog/xml_service':         blog.do_xml_service,
    'blog/atom_feed':           blog.do_atom_feed,
    'blog/get_uploaded_file':   blog.do_get_upload,
    'blog/serve_translations':  i18n.serve_javascript,

    # admin views
    'admin/index':              admin.do_index,
    'admin/bookmarklet':        admin.do_bookmarklet,
    'admin/show_posts':         admin.do_show_posts,
    'admin/new_post':           admin.do_edit_post,
    'admin/edit_post':          admin.do_edit_post,
    'admin/delete_post':        admin.do_delete_post,
    'admin/show_comments':      admin.do_show_comments,
    'admin/show_unmoderated_comments': admin.do_show_unmoderated_comments,
    'admin/show_spam_comments': admin.do_show_spam_comments,
    'admin/show_post_comments': admin.do_show_post_comments,
    'admin/edit_comment':       admin.do_edit_comment,
    'admin/delete_comment':     admin.do_delete_comment,
    'admin/approve_comment':    admin.do_approve_comment,
    'admin/block_comment':      admin.do_block_comment,
    'admin/show_categories':    admin.do_show_categories,
    'admin/new_category':       admin.do_edit_category,
    'admin/edit_category':      admin.do_edit_category,
    'admin/delete_category':    admin.do_delete_category,
    'admin/show_users':         admin.do_show_users,
    'admin/new_user':           admin.do_edit_user,
    'admin/edit_user':          admin.do_edit_user,
    'admin/delete_user':        admin.do_delete_user,
    'admin/browse_uploads':     admin.do_browse_uploads,
    'admin/new_upload':         admin.do_upload,
    'admin/delete_upload':      admin.do_delete_upload,
    'admin/upload_thumbnailer': admin.do_thumbnailer,
    'admin/upload_config':      admin.do_upload_config,
    'admin/options':            admin.do_options,
    'admin/basic_options':      admin.do_basic_options,
    'admin/urls':               admin.do_urls,
    'admin/theme':              admin.do_theme,
    'admin/configure_theme':    admin.do_configure_theme,
    'admin/plugins':            admin.do_plugins,
    'admin/remove_plugin':      admin.do_remove_plugin,
    'admin/cache':              admin.do_cache,
    'admin/configuration':      admin.do_configuration,
    'admin/maintenance':        admin.do_maintenance,
    'admin/import':             admin.do_import,
    'admin/inspect_import':     admin.do_inspect_import,
    'admin/delete_import':      admin.do_delete_import,
    'admin/export':             admin.do_export,
    'admin/information':        admin.do_information,
    'admin/log':                admin.do_log,
    'admin/about_zine':         admin.do_about_zine,
    'admin/change_password':    admin.do_change_password,
    'admin/help':               admin.do_help,
    'admin/login':              admin.do_login,
    'admin/logout':             admin.do_logout
}


all_handlers = {
    'entry':                    blog.show_entry,
    'page':                     blog.show_page
}
