# -*- coding: utf-8 -*-
"""
    textpress.views
    ~~~~~~~~~~~~~~~

    This module binds all the endpoints specified in `textpress.urls` to
    python functions in the view modules.


    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio.
    :license: GNU GPL.
"""
from textpress.views import blog, admin


#: bind the views to url endpoints
all_views = {
    # blog views
    'blog/index':               blog.do_index,
    'blog/archive':             blog.do_archive,
    'blog/show_tag':            blog.do_show_tag,
    'blog/tag_cloud':           blog.do_show_tag_cloud,
    'blog/show_post':           blog.do_show_post,
    'blog/show_author':         blog.do_show_author,
    'blog/show_page':           blog.do_show_page,
    'blog/authors':             blog.do_authors,
    'blog/service_rsd':         blog.do_service_rsd,
    'blog/json_service':        blog.do_json_service,
    'blog/xml_service':         blog.do_xml_service,
    'blog/atom_feed':           blog.do_atom_feed,
    'blog/get_uploaded_file':   blog.do_get_upload,

    # admin views
    'admin/index':              admin.do_index,
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
    'admin/show_pages':         admin.do_show_pages,
    'admin/write_page':         admin.do_write_page,
    'admin/delete_page':        admin.do_delete_page,
    'admin/show_tags':          admin.do_show_tags,
    'admin/new_tag':            admin.do_edit_tag,
    'admin/edit_tag':           admin.do_edit_tag,
    'admin/delete_tag':         admin.do_delete_tag,
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
    'admin/overlays':           admin.do_overlays,
    'admin/pages_config':       admin.do_pages_config,
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
    'admin/eventmap':           admin.do_eventmap,
    'admin/about_textpress':    admin.do_about_textpress,
    'admin/change_password':    admin.do_change_password,
    'admin/login':              admin.do_login,
    'admin/logout':             admin.do_logout
}
