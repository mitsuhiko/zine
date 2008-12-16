# -*- coding: utf-8 -*-
"""
    zine.views.admin
    ~~~~~~~~~~~~~~~~

    This module implements the admin views. The admin interface is only
    available for admins, editors and authors but not for subscribers. For
    subscribers a simplified account management system exists at /account.

    :copyright: 2007-2008 by Armin Ronacher, Christopher Grebs, Pedro Algarvio,
                             Ali Afshar.
    :license: GNU GPL.
"""
from datetime import datetime
from os import remove, sep as pathsep
from os.path import exists
from urlparse import urlparse

from werkzeug import escape
from werkzeug.exceptions import NotFound, BadRequest

from zine.i18n import _
from zine.application import require_role, get_request, url_for, emit_event, \
     render_response, get_application
from zine.models import User, Post, Category, Comment, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, \
     STATUS_DRAFT, STATUS_PUBLISHED, COMMENT_MODERATED, COMMENT_UNMODERATED, \
     COMMENT_BLOCKED_USER, COMMENT_BLOCKED_SPAM
from zine.database import db, comments as comment_table, posts, \
     post_categories, post_links, secure_database_uri
from zine.utils import dump_json, load_json
from zine.utils.validators import is_valid_email, is_valid_url, check
from zine.utils.admin import flash, gen_slug, load_zine_reddit
from zine.utils.pagination import AdminPagination
from zine.utils.xxx import make_hidden_fields, CSRFProtector, \
     IntelligentRedirect, StreamReporter
from zine.utils.uploads import guess_mimetype, get_upload_folder, \
     list_files, list_images, get_im_version, get_im_path, \
     touch_upload_folder, upload_file, create_thumbnail, file_exists, \
     get_filename
from zine.utils.http import redirect_back, redirect_to, redirect
from zine.i18n import parse_datetime, format_system_datetime, \
     list_timezones, has_timezone, list_languages, has_language
from zine.importers import list_import_queue, load_import_dump, \
     delete_import_dump, perform_import
from zine.pluginsystem import install_package, InstallationError, \
     SetupError, get_object_name
from zine.pingback import pingback, PingbackError
from zine.forms import LoginForm, ChangePasswordForm, PluginForm, \
     LogOptionsForm, EntryForm, PageForm, BasicOptionsForm, URLOptionsForm, \
     PostDeleteForm, EditCommentForm, DeleteCommentForm, \
     ApproveCommentForm, BlockCommentForm, EditCategoryForm, \
     DeleteCategoryForm, EditUserForm, DeleteUserForm, \
     CommentMassModerateForm, CacheOptionsForm


#: how many posts / comments should be displayed per page?
PER_PAGE = 20


def render_admin_response(template_name, _active_menu_item=None, **values):
    """Works pretty much like the normal `render_response` function but
    it emits some events to collect navigation items and injects that
    into the template context. This also gets the flashes messages from
    the user session and injects them into the template context after the
    plugins have provided theirs in the `before-admin-response-rendered`
    event.

    The second parameter can be the active menu item if wanted. For example
    ``'options.overview'`` would show the overview button in the options
    submenu. If the menu is a standalone menu like the dashboard (no
    child items) you can also just use ``'dashboard'`` to highlight that.
    """
    request = get_request()

    # set up the core navigation bar
    navigation_bar = [
        ('dashboard', url_for('admin/index'), _(u'Dashboard'), []),
        ('write', url_for('admin/new_entry'), _(u'Write'), [
            ('entry', url_for('admin/new_entry'), _(u'Entry')),
            ('page', url_for('admin/new_page'), _(u'Page'))
        ]),
        ('manage', url_for('admin/manage_entries'), _(u'Manage'), [
            ('entries', url_for('admin/manage_entries'), _(u'Entries')),
            ('pages', url_for('admin/manage_pages'), _(u'Pages')),
            ('categories', url_for('admin/manage_categories'), _(u'Categories'))
        ]),
        ('comments', url_for('admin/manage_comments'), _(u'Comments'), [
            ('overview', url_for('admin/manage_comments'), _(u'Overview')),
            ('unmoderated', url_for('admin/show_unmoderated_comments'),
             _(u'Awaiting Moderation (%d)') %
             Comment.query.unmoderated().count()),
            ('spam', url_for('admin/show_spam_comments'),
             _(u'Spam (%d)') % Comment.query.spam().count())
        ])
    ]

    # set up the administration menu bar
    if request.user.role == ROLE_ADMIN:
        navigation_bar += [
            ('users', url_for('admin/manage_users'), _(u'Users'), [
                ('overview', url_for('admin/manage_users'), _(u'Overview')),
                ('edit', url_for('admin/new_user'), _(u'Edit User'))
            ]),
            ('options', url_for('admin/options'), _(u'Options'), [
                ('basic', url_for('admin/basic_options'), _(u'Basic')),
                ('urls', url_for('admin/urls'), _(u'URLs')),
                ('theme', url_for('admin/theme'), _(u'Theme')),
                ('uploads', url_for('admin/upload_config'), _(u'Uploads')),
                ('plugins', url_for('admin/plugins'), _(u'Plugins')),
                ('cache', url_for('admin/cache'), _(u'Cache'))
            ])
        ]

    # add the about items to the navigation bar
    system_items = [
        ('information', url_for('admin/information'), _(u'Information')),
        ('help', url_for('admin/help'), _(u'Help')),
        ('about', url_for('admin/about_zine'), _(u'About'))
    ]
    if request.user.role == ROLE_ADMIN:
        system_items[1:1] = [
             ('maintenance', url_for('admin/maintenance'),
             _(u'Maintenance')),
             ('import', url_for('admin/import'), _(u'Import')),
             ('export', url_for('admin/export'), _(u'Export')),
             ('log', url_for('admin/log'), _('Log')),
             ('configuration', url_for('admin/configuration'),
              _(u'Configuration Editor'))
        ]

    navigation_bar.append(('system', url_for('admin/information'), _(u'System'),
                          system_items))

    #! allow plugins to extend the navigation bar
    emit_event('modify-admin-navigation-bar', request, navigation_bar)

    # find out which is the correct menu and submenu bar
    active_menu = active_submenu = None
    if _active_menu_item is not None:
        p = _active_menu_item.split('.')
        if len(p) == 1:
            active_menu = p[0]
        else:
            active_menu, active_submenu = p
    for id, url, title, subnavigation_bar in navigation_bar:
        if id == active_menu:
            break
    else:
        subnavigation_bar = []

    # if we are in maintenance_mode the user should know that, no matter
    # on which page he is.
    if request.app.cfg['maintenance_mode']:
        flash(_(u'Zine is in maintenance mode. Don\'t forget to '
                u'<a href="%s">turn it off again</a> once you finish your '
                u'changes.') % url_for('admin/maintenance'))

    # check for broken plugins if we have the plugin guard enabled
    if request.app.cfg['plugin_guard']:
        plugins_to_deactivate = []
        for plugin in request.app.plugins.itervalues():
            if plugin.active and plugin.setup_error is not None:
                plugins_to_deactivate.append(plugin.name)
                exc_type, exc_value, tb = plugin.setup_error
                if exc_type is SetupError:
                    msg = _(u'Could not activate plugin “%(name)s”: %(error)s') % {
                        'name': plugin.html_display_name,
                        'error': exc_value.message
                    }
                else:
                    msg =_(u'The plugin guard detected that the plugin '
                           u'“%(name)s” causes problems (%(error)s in '
                           u'%(file)s, line %(line)s) and deactivated it.  If '
                           u'you want to debug it, disable the plugin guard.') % {
                        'name': plugin.html_display_name,
                        'error': escape(str(plugin.setup_error[1]).
                                        decode('utf-8', 'ignore')),
                        'file': plugin.setup_error[2].tb_frame.
                                    f_globals.get('__file__', _(u'unknown file')),
                        'line': plugin.setup_error[2].tb_lineno
                    }
                flash(msg, 'error')

        if plugins_to_deactivate:
            #TODO: it's quite tricky – it needs at least two reloads to
            #      deactivate the plugin (which is in fact a application reload)
            cfg = request.app.cfg.edit()
            cfg['plugins'] = u', '.join(sorted(set(request.app.cfg['plugins']) - \
                                               set(plugins_to_deactivate)))
            cfg.commit()
            # we change the plugins inline so that the user get somewhat more
            # informations
            request.app.cfg.touch()


    #! used to flash messages, add links to stylesheets, modify the admin
    #! context etc.
    emit_event('before-admin-response-rendered', request, values)

    # the admin variables is pushed into the context after the event was
    # sent so that plugins can flash their messages. If we would emit the
    # event afterwards all flashes messages would appear in the request
    # after the current request.
    values['admin'] = {
        'navbar': [{
            'id':       id,
            'url':      url,
            'title':    title,
            'active':   active_menu == id
        } for id, url, title, children in navigation_bar],
        'ctxnavbar': [{
            'id':       id,
            'url':      url,
            'title':    title,
            'active':   active_submenu == id
        } for id, url, title in subnavigation_bar],
        'messages': [{
            'type':     type,
            'msg':      msg
        } for type, msg in request.session.pop('admin/flashed_messages', [])]
    }
    return render_response(template_name, **values)


def ping_post_links(request, post):
    """A helper that pings the links in a post."""
    if request.app.cfg['maintenance_mode'] or not post.is_published:
        flash(_(u'No URLs pinged so far because the post is not '
                u'publicly available'))
    elif post.parser_missing:
        flash(_(u'Could not ping URLs because the parser for the '
                u'post is not available any longer.'), 'error')
    else:
        this_url = url_for(post, _external=True)
        for url in post.find_urls():
            host = urlparse(url)[1].decode('utf-8', 'ignore')
            html_url = '<a href="%s">%s</a>' % (
                escape(url, True),
                escape(host)
            )
            try:
                pingback(this_url, url)
            except PingbackError, e:
                if not e.ignore_silently:
                    flash(_(u'Could not ping %(url)s: %(error)s') % {
                        'url': html_url,
                        'error': e.description
                    }, 'error')
            else:
                flash(_(u'%s was pinged successfully.') %
                        html_url)


@require_role(ROLE_AUTHOR)
def index(request):
    """Show the admin interface index page which is a wordpress inspired
    dashboard (doesn't exist right now).

    Once it's finished it should show the links to the most useful pages
    such as "new post", etc. and the recent blog activity (unmoderated
    comments etc.)
    """
    # the template loads the reddit with a separate http request via
    # javascript to not slow down the page loading
    if request.args.get('load') == 'reddit':
        return render_response('admin/reddit.html', items=load_zine_reddit())

    return render_admin_response('admin/index.html', 'dashboard',
        drafts=Post.query.drafts().all(),
        unmoderated_comments=Comment.query.unmoderated().all(),
        your_posts=Post.query.filter(
            Post.author_id == request.user.id
        ).count(),
        last_posts=Post.query.published(ignore_role=True)
            .order_by(Post.pub_date.desc()).limit(5).all()
    )


def bookmarklet(request):
    """Requests to this view are usually triggered by the bookmarklet
    from the edit-post page.  Currently this is a redirect to the new-post
    page with some small modifications but in the future this could be
    expanded to add a wizard or something.
    """
    if request.args['mode'] != 'newpost':
        raise BadRequest()
    body = '%s\n\n<a href="%s">%s</a>' % (
        request.args.get('text', _(u'Text here...')),
        request.args['url'],
        request.args.get('title', _(u'Untitled Page'))
    )
    return redirect_to('admin/new_entry',
        title=request.args.get('title'),
        body=body
    )


@require_role(ROLE_AUTHOR)
def manage_entries(request, page):
    """Show a list of entries."""
    entry_query = Post.query.type('entry')
    entries = entry_query.order_by([Post.status, Post.pub_date.desc()]) \
                         .limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_entries', page, PER_PAGE,
                                 entry_query.count())
    if not posts and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_entries.html', 'manage.entries',
                                 entries=entries, pagination=pagination)


def _make_post_dispatcher(action):
    def func(request, post_id):
        """Dispatch to the request handler for a post."""
        post = Post.query.get(post_id)
        if post is None:
            raise NotFound()
        try:
            handler = request.app.admin_content_type_handlers \
                [post.content_type][action]
        except KeyError:
            raise NotFound()
        return handler(request, post)
    func.__name__ = 'dispatch_post_' + action
    return func


dispatch_post_edit = _make_post_dispatcher('edit')
dispatch_post_delete = _make_post_dispatcher('delete')


@require_role(ROLE_AUTHOR)
def edit_entry(request, post=None):
    """Edit an existing entry or create a new one."""
    active_tab = post and 'manage.entries' or 'write.entry'
    form = EntryForm(post)

    if request.method == 'POST':
        if 'cancel' in request.form:
            return form.redirect('admin/manage_entries')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_post', post_id=post.id)
        elif form.validate(request.form):
            if post is None:
                post = form.make_post()
                msg = _('The entry %s was created successfully.')
            else:
                form.save_changes()
                msg = _('The entry %s was updated successfully.')

            flash(msg % u'<a href="%s">%s</a>' % (escape(url_for(post)),
                                                  escape(post.title)))

            db.commit()
            emit_event('after-post-saved', post)
            if form['ping_links']:
                ping_post_links(request, post)
            if 'save_and_continue' in request.form:
                return redirect_to('admin/edit_post', post_id=post.id)
            return form.redirect('admin/new_entry')
    return render_admin_response('admin/edit_entry.html', active_tab,
                                 form=form.as_widget())


@require_role(ROLE_AUTHOR)
def delete_entry(request, post):
    """This dialog deletes an entry.  Usually users are redirected here from the
    edit post view or the post index page.  If the entry was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.
    """
    form = PostDeleteForm(post)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/edit_post', post_id=post.id)
        elif request.form.get('confirm') and form.validate(request.form):
            form.add_invalid_redirect_target('admin/edit_post', post_id=post.id)
            form.delete_post()
            flash(_(u'The entry %s was deleted successfully.') %
                  escape(post.title), 'remove')
            db.commit()
            return form.redirect('admin/manage_entries')

    return render_admin_response('admin/delete_entry.html', 'manage.entries',
                                 form=form.as_widget())


@require_role(ROLE_AUTHOR)
def manage_pages(request, page):
    """Show a list of pages."""
    page_query = Post.query.type('page')
    pages = page_query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_pages', page, PER_PAGE,
                                 page_query.count())
    if not posts and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_pages.html', 'manage.pages',
                                 pages=pages, pagination=pagination)


@require_role(ROLE_AUTHOR)
def edit_page(request, post=None):
    """Edit an existing entry or create a new one."""
    active_tab = post and 'manage.pages' or 'write.page'
    form = PageForm(post)

    if request.method == 'POST':
        if 'cancel' in request.form:
            return form.redirect('admin/manage_pages')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_post', post_id=post.id)
        elif form.validate(request.form):
            if post is None:
                post = form.make_post()
                msg = _('The page %s was created successfully.')
            else:
                form.save_changes()
                msg = _('The page %s was updated successfully.')

            flash(msg % u'<a href="%s">%s</a>' % (escape(url_for(post)),
                                                  escape(post.title)))

            db.commit()
            emit_event('after-post-saved', post)
            if form['ping_links']:
                ping_post_links(request, post)
            if 'save_and_continue' in request.form:
                return redirect_to('admin/edit_post', post_id=post.id)
            return form.redirect('admin/new_page')
    return render_admin_response('admin/edit_page.html', active_tab,
                                 form=form.as_widget())


@require_role(ROLE_AUTHOR)
def delete_page(request, post):
    """This dialog deletes a page.  Usually users are redirected here from the
    edit post view or the page indexpage.  If the page was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.
    """
    form = PostDeleteForm(post)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/edit_post', post_id=post.id)
        elif request.form.get('confirm') and form.validate(request.form):
            form.add_invalid_redirect_target('admin/edit_post', post_id=post.id)
            form.delete_post()
            flash(_(u'The page %s was deleted successfully.') %
                  escape(post.title), 'remove')
            db.commit()
            return form.redirect('admin/manage_pages')

    return render_admin_response('admin/delete_page.html', 'manage.pages',
                                 form=form.as_widget())


def _handle_comments(identifier, title, query, page):
    request = get_request()
    comments = query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_comments', page, PER_PAGE,
                                 query.count())
    if not comments and page != 1:
        raise NotFound()

    form = CommentMassModerateForm(comments)

    if request.method == 'POST':
        if 'cancel' not in request.form and form.validate(request.form):
            if 'delete' in request.form:
                if 'confirm' in request.form:
                    form.delete_selection()
                    db.commit()
                    return redirect_to('admin/manage_comments')
                return render_admin_response('admin/delete_comments.html',
                                             form=form.as_widget())

            # or approve them all
            elif 'approve' in request.form:
                form.approve_selection()
                db.commit()
                flash(_(u'Approved all the selected comments.'))
                return redirect_to('admin/manage_comments')

    tab = 'comments'
    if identifier is not None:
        tab += '.' + identifier
    return render_admin_response('admin/manage_comments.html', tab,
                                 comments_title=title, form=form.as_widget(),
                                 pagination=pagination)


@require_role(ROLE_AUTHOR)
def manage_comments(request, page):
    """Show all the comments."""
    return _handle_comments('overview', _(u'All Comments'),
                            Comment.query, page)


@require_role(ROLE_AUTHOR)
def show_unmoderated_comments(request, page):
    """Show all unmoderated and user-blocked comments."""
    return _handle_comments('unmoderated', _(u'Comments Awaiting Moderation'),
                            Comment.query.unmoderated(), page)


@require_role(ROLE_AUTHOR)
def show_spam_comments(request, page):
    """Show all spam comments."""
    return _handle_comments('spam', _(u'Spam'), Comment.query.spam(), page)


@require_role(ROLE_AUTHOR)
def show_post_comments(request, page, post_id):
    """Show all comments for a single post."""
    post = Post.query.get(post_id)
    if post is None:
        raise NotFound()
    link = '<a href="%s">%s</a>' % (
        url_for('admin/edit_post', post_id=post.id),
        escape(post.title)
    )
    return _handle_comments(None, _(u'Comments for “%s”') % link,
                            Comment.query.comments_for_post(post), page)


@require_role(ROLE_AUTHOR)
def edit_comment(request, comment_id):
    """Edit a comment.  Unlike the post edit screen it's not possible to
    create new comments from here, that has to happen from the post page.
    """
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise NotFound()
    form = EditCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('cancel'):
            return form.redirect('admin/manage_comments')
        elif request.form.get('delete'):
            return redirect_to('admin/delete_comment', comment_id=comment_id)
        form.save_changes()
        db.commit()
        flash(_(u'Comment by %s moderated successfully.') %
              escape(comment.author))
        return form.redirect('admin/manage_comments')

    return render_admin_response('admin/edit_comment.html',
                                 'comments.overview', form=form.as_widget())


@require_role(ROLE_AUTHOR)
def delete_comment(request, comment_id):
    """This dialog delets a comment.  Usually users are redirected here from the
    comment moderation page or the comment edit page.  If the comment was not
    deleted, the user is taken back to the page he's coming from or back to
    the edit page if the information is invalid.  The same happens if the post
    was deleted but if the referrer is the edit page. Then the user is taken
    back to the index so that he doesn't end up an a "page not found" error page.
    """
    comment = Comment.query.get(comment_id)
    if comment is None:
        return redirect_to('admin/manage_comments')

    form = DeleteCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('cancel'):
            return form.redirect('admin/edit_comment', comment_id=comment.id)
        elif request.form.get('confirm'):
            form.add_invalid_redirect_target('admin/edit_comment',
                                             comment_id=comment.id)
            form.delete_comment()
            db.commit()
            return form.redirect('admin/manage_comments')

    return render_admin_response('admin/delete_comment.html',
                                 'comments.overview', form=form.as_widget())


@require_role(ROLE_AUTHOR)
def approve_comment(request, comment_id):
    """Approve a comment"""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise NotFound()
    form = ApproveCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('confirm'):
            form.approve_comment()
            db.commit()
            flash(_(u'Comment by %s approved successfully.') %
                  escape(comment.author), 'configure')
        return form.redirect('admin/manage_comments')

    return render_admin_response('admin/approve_comment.html',
                                 'comments.overview', form=form.as_widget())


@require_role(ROLE_AUTHOR)
def block_comment(request, comment_id):
    """Block a comment."""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise NotFound()
    form = BlockCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('confirm'):
            form.block_comment()
            db.commit()
            flash(_(u'Comment by %s blocked successfully.') %
                  escape(comment.author), 'configure')
        return form.redirect('admin/manage_comments')

    return render_admin_response('admin/block_comment.html',
                                 'comments.overview', form=form.as_widget())


@require_role(ROLE_AUTHOR)
def manage_categories(request, page):
    """Show a list of used post categories."""
    categories = Category.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_categories', page, PER_PAGE,
                                 Category.query.count())
    if not categories and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_categories.html', 'manage.categories',
                                 categories=categories,
                                 pagination=pagination)


@require_role(ROLE_AUTHOR)
def edit_category(request, category_id=None):
    """Edit a category."""
    category = None
    if category_id is not None:
        category = Category.query.get(category_id)
        if category is None:
            raise NotFound()

    form = EditCategoryForm(category)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/manage_categories')
        if request.form.get('delete'):
            return redirect_to('admin/delete_category', category_id=category.id)
        elif form.validate(request.form):
            if category is None:
                category = form.make_category()
                msg = _(u'Category %s created successfully.')
                msg_type = 'add'
            else:
                form.save_changes()
                msg = _(u'Category %s updated successfully.')
                msg_type = 'info'
            db.commit()
            html_category_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(category)),
                escape(category.name)
            )
            flash(msg % html_category_detail, msg_type)
            return redirect_to('admin/manage_categories')

    return render_admin_response('admin/edit_category.html', 'manage.categories',
                                 form=form.as_widget())


@require_role(ROLE_AUTHOR)
def delete_category(request, category_id):
    """Works like the other delete pages, just that it deletes categories."""
    category = Category.query.get(category_id)
    if category is None:
        return redirect_to('admin/manage_categories')
    form = DeleteCategoryForm(category)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return redirect('admin/edit_category', category_id=category.id)
        elif request.form.get('confirm') and form.validate(request.form):
            redirect.add_invalid('admin/edit_category', category_id=category.id)
            form.delete_category()
            flash(_(u'Category %s deleted successfully.') % escape(category.name))
            db.commit()
            return form.redirect('admin/manage_categories')

    return render_admin_response('admin/delete_category.html', 'manage.categories',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def manage_users(request, page):
    """Show all users in a list."""
    users = User.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_users', page, PER_PAGE,
                                 User.query.count())
    if not posts and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_users.html', 'users.overview',
                                 users=users,
                                 pagination=pagination)


@require_role(ROLE_ADMIN)
def edit_user(request, user_id=None):
    """Edit a user.  This can also create a user.  If a new user is created
    the dialog is simplified, some unimportant details are left out.
    """
    user = None
    if user_id is not None:
        user = User.query.get(user_id)
        if user is None:
            raise NotFound()
    form = EditUserForm(user)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/manage_users')
        elif request.form.get('delete') and user:
            return redirect_to('admin/delete_user', user_id=user.id)
        elif form.validate(request.form):
            if user is None:
                user = form.make_user()
                msg = _(u'User %s created successfully.')
                icon = 'add'
            else:
                form.save_changes()
                msg = _(u'User %s edited successfully.')
                icon = 'info'
            db.commit()
            html_user_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(user)),
                escape(user.username)
            )
            flash(msg % html_user_detail, icon)
            if request.form.get('save'):
                return form.redirect('admin/manage_users')
            return redirect_to('admin/edit_user', user_id=user.id)

    return render_admin_response('admin/edit_user.html', 'users.edit',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def delete_user(request, user_id):
    """Like all other delete screens just that it deletes a user."""
    user = User.query.get(user_id)
    if user is None:
        raise NotFound()
    form = DeleteUserForm(user)
    if user == request.user:
        flash(_(u'You cannot delete yourself.'), 'error')
        return form.redirect('admin/manage_users')

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/edit_user', user_id=user.id)
        elif request.form.get('confirm') and form.validate(request.form):
            form.add_invalid_redirect_target('admin/edit_user', user_id=user.id)
            form.delete_user()
            db.commit()
            return form.redirect('admin/manage_users')

    return render_admin_response('admin/delete_user.html', 'users.edit',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def options(request):
    """So far just a redirect page, later it would be a good idea to have
    a page that shows all the links to configuration things in form of
    a simple table.
    """
    return redirect_to('admin/basic_options')


@require_role(ROLE_ADMIN)
def basic_options(request):
    """The dialog for basic options such as the blog title etc."""
    # flash an altered message if the url is ?altered=true.  For more information
    # see the comment that redirects to the url below.
    if request.args.get('altered') == 'true':
        flash(_(u'Configuration altered successfully.'), 'configure')
        return redirect_to('admin/basic_options')

    form = BasicOptionsForm()

    if request.method == 'POST' and form.validate(request.form):
        form.apply()

        # because the configuration page could change the language and
        # we want to flash the message "configuration changed" in the
        # new language rather than the old.  As a matter of fact we have
        # to wait for Zine to reload first which is why we do the
        # actual flashing after one reload.
        return redirect_to('admin/basic_options', altered='true')

    return render_admin_response('admin/basic_options.html', 'options.basic',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def urls(request):
    """A config page for URL depending settings."""
    form = URLOptionsForm()

    if request.method == 'POST' and form.validate(request.form):
        form.apply()
        flash(_(u'URL configuration changed.'), 'configure')
        # because the next request could reload the application and move
        # the admin interface we construct the URL to this page by hand.
        return redirect(form['admin_url_prefix'][1:] + '/options/urls')

    return render_admin_response('admin/url_options.html', 'options.urls',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def theme(request):
    """Allow the user to select one of the themes that are available."""
    csrf_protector = CSRFProtector()
    if 'configure' in request.args:
        return redirect_to('admin/configure_theme')
    new_theme = request.args.get('select')
    if new_theme in request.app.themes:
        csrf_protector.assert_safe()
        request.app.cfg.change_single('theme', new_theme)
        flash(_(u'Theme changed successfully.'), 'configure')
        return redirect_to('admin/theme')

    return render_admin_response('admin/theme.html', 'options.theme',
        themes=sorted(request.app.themes.values(),
                      key=lambda x: x.name == 'default' or x.display_name.lower()),
        current_theme=request.app.theme,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def configure_theme(request):
    if not request.app.theme.configurable:
        flash(_(u'This theme is not configurable'), 'error')
        return redirect_to('admin/theme')
    return request.app.theme.configuration_page(request)


@require_role(ROLE_ADMIN)
def plugins(request):
    """Load and unload plugins and reload Zine if required."""
    form = PluginForm()

    if request.method == 'POST' and form.validate(request.form):
        form.apply()
        flash(_('Plugin configuration changed'), 'configure')

        new_plugin = request.files.get('new_plugin')
        if new_plugin:
            try:
                plugin = install_package(request.app, new_plugin)
            except InstallationError, e:
                flash(e.message, 'error')
            else:
                flash(_(u'Plugin “%s” added succesfully. You can now '
                        u'enable it in the plugin list.') %
                      plugin.html_display_name, 'add')

        return redirect_to('admin/plugins')

    return render_admin_response('admin/plugins.html', 'options.plugins',
        form=form.as_widget(),
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name)
    )


@require_role(ROLE_ADMIN)
def remove_plugin(request, plugin):
    """Remove an inactive, instance installed plugin completely."""
    plugin = request.app.plugins.get(plugin)
    if plugin is None or \
       not plugin.instance_plugin or \
       plugin.active:
        raise NotFound()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('confirm'):
            try:
                plugin.remove()
            except IOError:
                flash(_(u'Could not remove the plugin “%s” because an '
                        u'IO error occoured. Wrong permissions?') %
                      plugin.html_display_name)
            flash(_(u'The plugin “%s” was removed from the instance '
                    u'successfully.') % escape(plugin.display_name), 'remove')
        return redirect('admin/plugins')

    return render_admin_response('admin/remove_plugin.html', 'options.plugins',
        plugin=plugin,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def cache(request):
    """Configure the cache."""
    form = CacheOptionsForm()

    if request.method == 'POST':
        if 'clear_cache' in request.form:
            request.app.cache.clear()
            flash(_(u'The cache was cleared successfully.'), 'configure')
            return redirect_to('admin/cache')
        elif form.validate(request.form):
            form.apply()
            flash(_(u'Cache settings were changed successfully.'), 'configure')
            return redirect_to('admin/cache')

    print form.errors

    return render_admin_response('admin/cache.html', 'options.cache',
                                 form=form.as_widget())


@require_role(ROLE_ADMIN)
def configuration(request):
    """Advanced configuration editor.  This is useful for development or if a
    plugin doesn't ship an editor for the configuration values.  Because all
    the values are not further checked it could easily be that Zine is
    left in an unusable state if a variable is set to something bad.  Because
    of this the editor shows a warning and must be enabled by hand.
    """
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('enable_editor'):
            request.session['ace_on'] = True
        elif request.form.get('disable_editor'):
            request.session['ace_on'] = False
        else:
            already_default = set()
            t = request.app.cfg.edit()
            for key, value in request.form.iteritems():
                key = key.replace('.', '/')
                if key.endswith('__DEFAULT'):
                    key = key[:-9]
                    t.revert_to_default(key)
                    already_default.add(key)
                elif key in request.app.cfg and key not in already_default:
                    t.set_from_string(key, value)
            t.commit()
        return redirect_to('admin/configuration')

    # html does not allow slashes.  Convert them to dots
    categories = []
    for category in request.app.cfg.get_detail_list():
        for item in category['items']:
            item['key'] = item['key'].replace('/', '.')
        categories.append(category)

    return render_admin_response('admin/configuration.html',
                                 'system.configuration',
        categories=categories,
        editor_enabled=request.session.get('ace_on', False),
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def maintenance(request):
    """Enable / Disable maintenance mode."""
    cfg = request.app.cfg
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()
        cfg.change_single('maintenance_mode', not cfg['maintenance_mode'])
        if not cfg['maintenance_mode']:
            flash(_(u'Maintenance mode disabled.  The blog is now '
                    u'publicly available.'), 'configure')
        return redirect_to('admin/maintenance')

    return render_admin_response('admin/maintenance.html',
                                 'system.maintenance',
        hidden_form_data=make_hidden_fields(csrf_protector),
        maintenance_mode=cfg['maintenance_mode']
    )


@require_role(ROLE_ADMIN)
def import_dump(request):
    """Show the current import queue or add new items."""
    return render_admin_response('admin/import.html', 'system.import',
        importers=sorted(request.app.importers.values(),
                         key=lambda x: x.title.lower()),
        queue=list_import_queue(request.app)
    )


@require_role(ROLE_ADMIN)
def inspect_import(request, id):
    """Inspect a database dump."""
    blog = load_import_dump(request.app, id)
    if blog is None:
        raise NotFound()
    csrf_protector = CSRFProtector()

    # assemble initial dict
    form = {}
    for author in blog.authors:
        form['import_author_%s' % author.id] = True
    for post in blog.posts:
        form.update({
            'import_post_%s' % post.id:     True,
            'import_comments_%s' % post.id: True
        })

    # perform the actual import here
    if request.method == 'POST':
        csrf_protector.assert_safe()
        if 'cancel' in request.form:
            return redirect_to('admin/maintenance')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_import', id=id)
        return render_admin_response('admin/perform_import.html',
                                     'system.import',
            live_log=perform_import(request.app, blog, request.form,
                                    stream=True),
            _stream=True
        )

    return render_admin_response('admin/inspect_import.html',
                                 'system.import',
        form=form,
        blog=blog,
        users=User.query.order_by('username').all(),
        hidden_form_data=make_hidden_fields(csrf_protector),
        dump_id=id
    )


@require_role(ROLE_ADMIN)
def delete_import(request, id):
    """Delete an imported file."""
    dump = load_import_dump(request.app, id)
    if dump is None:
        raise NotFound()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('cancel'):
            return redirect('admin/inspect_import', id=id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/inspect_import', id=id)
            delete_import_dump(request.app, id)
            flash(_(u'The imported dump “%s” was deleted successfully.') %
                  escape(dump.title), 'remove')
            return redirect('admin/import')

    return render_admin_response('admin/delete_import.html',
                                 'system.import',
        dump=dump,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def export(request):
    """Not yet implemented."""
    csrf_protector = CSRFProtector()
    if request.args.get('format') == 'zxa':
        csrf_protector.assert_safe()
        from zine.zxa import export
        response = export(request.app)
        response.headers['Content-Disposition'] = 'attachment; ' \
            'filename="%s.zxa"' % '_'.join(request.app.cfg['blog_title'].split())
        return response
    return render_admin_response('admin/export.html', 'system.export',
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_AUTHOR)
def information(request):
    """Shows some details about this Zine installation.  It's useful for
    debugging and checking configurations.  If severe errors in a Zine
    installation occour it's a good idea to dump this page and attach it to
    a bug report mail.
    """
    from platform import platform
    from sys import version as python_version
    from threading import activeCount
    from jinja2.defaults import DEFAULT_NAMESPACE, DEFAULT_FILTERS
    from zine import environment, __version__ as zine_version

    export = request.args.get('do') == 'export'
    database_uri = request.app.cfg['database_uri']
    if export:
        database_uri = secure_database_uri(database_uri)

    content_types = {}
    for name, func in request.app.content_type_handlers.iteritems():
        content_types[name] = {'name': name, 'show': get_object_name(func)}
    for name, funcs in request.app.admin_content_type_handlers.iteritems():
        if name in content_types:
            for action, func in funcs.iteritems():
                content_types[name][action] = get_object_name(func)
    content_types = sorted(content_types.values(), key=lambda x: x['name'])

    response = render_admin_response('admin/information.html', 'system.information',
        apis=[{
            'name':         name,
            'blog_id':      blog_id,
            'preferred':    preferred,
            'endpoint':     endpoint
        } for name, (blog_id, preferred, endpoint) in request.app.apis.iteritems()],
        endpoints=[{
            'name':         rule.endpoint,
            'rule':         unicode(rule)
        } for rule in sorted(request.app.url_map._rules, key=lambda x: x.endpoint)],
        views=sorted([{
            'endpoint':     endpoint,
            'handler':      get_object_name(view)
        } for endpoint, view
            in request.app.views.iteritems()], key=lambda x: x['endpoint']),
        zeml_element_handlers=[{
            'tag':          handler.tag,
            'name':         get_object_name(handler)
        } for handler in sorted(request.app.zeml_element_handlers,
                                key=lambda x: x.tag)],
        parsers=[{
            'key':          key,
            'name':         parser.name,
            'id':           get_object_name(parser)
        } for key, parser in request.app.parsers.iteritems()],
        absolute_url_handlers=[get_object_name(handler) for handler
                               in request.app._absolute_url_handlers],
        content_types=content_types,
        servicepoints=sorted([{
            'name':         name,
            'handler':      get_object_name(service)
        } for name, service in request.app._services.iteritems()],
            key=lambda x: x['name']),
        configuration=request.app.cfg.get_public_list(export),
        hosting_env={
            'persistent':       not request.is_run_once,
            'multithreaded':    request.is_multithread,
            'thread_count':     activeCount(),
            'multiprocess':     request.is_multiprocess,
            'wsgi_version':     '.'.join(map(str, request.environ['wsgi.version']))
        },
        plugins=sorted(request.app.plugins.values(), key=lambda x: not x.active and x.name),
        python_version='<br>'.join(map(escape, python_version.splitlines())),
        zine_env=environment,
        zine_version=zine_version,
        template_globals=[name for name, obj in
                          sorted(request.app.template_env.globals.items())
                          if name not in DEFAULT_NAMESPACE],
        template_filters=[name for name, obj in
                          sorted(request.app.template_env.filters.items())
                          if name not in DEFAULT_FILTERS],
        instance_path=request.app.instance_folder,
        database_uri=database_uri,
        platform=platform(),
        export=export
    )

    if export:
        response.headers['Content-Disposition'] = 'attachment; ' \
            'filename="textpress-environment.html"'

    return response


@require_role(ROLE_ADMIN)
def log(request, page):
    page = request.app.log.view().get_page(page)
    form = LogOptionsForm()
    if request.method == 'POST' and form.validate(request.form):
        form.apply()
        flash(_('Log changes saved.'), 'configure')
        return redirect_to('admin/log', page=page.number)
    return render_admin_response('admin/log.html', 'system.log',
                                 page=page, form=form.as_widget())


@require_role(ROLE_AUTHOR)
def about_zine(request):
    """Just show the zine license and some other legal stuff."""
    return render_admin_response('admin/about_zine.html',
                                 'system.about')


@require_role(ROLE_AUTHOR)
def change_password(request):
    """Allow the current user to change his password."""
    form = ChangePasswordForm(request.user)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/index')
        if form.validate(request.form):
            form.user.set_password(form['new_password'])
            db.commit()
            flash(_(u'Password changed successfully.'), 'configure')
            return form.redirect('admin/index')

    return render_admin_response('admin/change_password.html',
        form=form.as_widget()
    )


@require_role(ROLE_AUTHOR)
def upload(req):
    csrf_protector = CSRFProtector()
    reporter = StreamReporter()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        f = req.files['file']
        if not touch_upload_folder():
            flash(_(u'Could not create upload target folder %s.') %
                  escape(get_upload_folder()), 'error')
            return redirect_to('admin/new_upload')

        filename = req.form.get('filename') or f.filename

        if not f:
            flash(_(u'No file uploaded.'))
        elif pathsep in filename:
            flash(_(u'Invalid filename requested.'))
        elif file_exists(filename) and not req.form.get('overwrite'):
            flash(_(u'A file with the filename %s exists already.') % (
                u'<a href="%s">%s</a>' % (
                    escape(url_for('blog/get_uploaded_file',
                                   filename=filename)),
                    escape(filename)
                )))
        else:
            if upload_file(f, filename):
                flash(_(u'File %s uploaded successfully.') % (
                        u'<a href="%s">%s</a>' % (
                          escape(url_for('blog/get_uploaded_file',
                                         filename=filename)),
                          escape(filename))))
            else:
                flash(_(u'Could not write file %s.') % escape(filename), 'error')
        return redirect_to('admin/new_upload')

    return render_admin_response('admin/file_uploads/upload.html',
                                 'file_uploads.upload',
        csrf_protector=csrf_protector,
        reporter=reporter
    )


@require_role(ROLE_AUTHOR)
def thumbnailer(req):
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()
    form = {
        'src_image':            '',
        'thumb_width':          '320',
        'thumb_height':         '240',
        'keep_aspect_ratio':    True,
        'thumb_filename':       ''
    }

    im_version = get_im_version()
    if im_version is None:
        path = get_im_path()
        if not path:
            extra = _(u'If you don\'t have ImageMagick installed system wide '
                      u'but in a different folder, you can defined that in '
                      u'the <a href="%(config)s">configuration</a>.')
        else:
            extra = _(u'There is no ImageMagick in the path defined '
                      u'installed. (<a href="%(config)s">check the '
                      u'configuration</a>)')
        flash((_(u'Cannot find <a href="%(im)s">ImageMagick</a>.') + ' ' +
               extra) % {
                   'im':        'http://www.imagemagick.org/',
                   'config':    url_for('admin/upload_config')
               }, 'error')

    elif req.method == 'POST':
        errors = []
        csrf_protector.assert_safe()
        form['src_image'] = src_image = req.form.get('src_image')
        if not src_image:
            errors.append(_(u'You have to specify a source image'))
        else:
            try:
                src = file(get_filename(src_image), 'rb')
            except IOError:
                errors.append(_(u'The image %s does not exist.') %
                              escape(src_image))
        form['thumb_width'] = thumb_width = req.form.get('thumb_width', '')
        form['thumb_height'] = thumb_height = req.form.get('thumb_height', '')
        if not thumb_width:
            errors.append(_(u'You have to define at least the width of the '
                            u'thumbnail.'))
        elif not thumb_width.isdigit() or \
                (thumb_height and not thumb_height.isdigit()):
            errors.append(_(u'Thumbnail dimensions must be integers.'))
        form['keep_aspect_ratio'] = keep_aspect_ratio = \
                'keep_aspect_ratio' in req.form
        form['thumb_filename'] = thumb_filename = \
                req.form.get('thumb_filename')
        if not thumb_filename:
            errors.append(_(u'You have to specify a filename for the '
                            u'thumbnail.'))
        elif pathsep in thumb_filename:
            errors.append(_(u'Invalid filename for thumbnail.'))
        elif file_exists(thumb_filename):
            errors.append(_(u'An file with this name exists already.'))
        if errors:
            flash(errors[0], 'error')
        else:
            if guess_mimetype(thumb_filename) != 'image/jpeg':
                thumb_filename += '.jpg'
            try:
                dst = file(get_filename(thumb_filename), 'wb')
            except IOError:
                flash(_(u'Could not write file %s.') % escape(thumb_filename),
                      'error')
                return redirect('admin/browse_uploads')
            try:
                dst.write(create_thumbnail(src, thumb_width,
                                           thumb_height or None,
                                           keep_aspect_ratio and 'normal'
                                           or 'force', 90, True))
                dst.close()
                flash(_(u'Thumbnail %s was created successfully.') % (
                      u'<a href="%s">%s</a>' % (
                          escape(url_for('blog/get_uploaded_file',
                                         filename=thumb_filename)),
                          escape(thumb_filename))))
                return redirect('admin/browse_uploads')
            except Exception, e:
                flash('Error creating thumbnail: %s' % e, 'error')
                dst.close()


    return render_admin_response('admin/file_uploads/thumbnailer.html',
                                 'file_uploads.thumbnailer',
        im_version=im_version,
        images=list_images(),
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def browse_uploads(req):
    return render_admin_response('admin/file_uploads/browse.html',
                                 'file_uploads.browse',
        files=list_files()
    )


@require_role(ROLE_ADMIN)
def upload_config(req):
    csrf_protector = CSRFProtector()
    form = {
        'upload_dest':  req.app.cfg['upload_folder'],
        'im_path':      req.app.cfg['im_path'],
        'mimetypes':    u'\n'.join(req.app.cfg['upload_mimetypes'].
                                   split(';'))
    }
    if req.method == 'POST':
        csrf_protector.assert_safe()
        upload_dest = form['upload_dest'] = req.form.get('upload_dest', '')
        if upload_dest != req.app.cfg['upload_folder']:
            if req.app.cfg.change_single('upload_folder', upload_dest):
                flash(_(u'Upload folder changed successfully.'))
            else:
                flash(_(u'Upload folder could not be changed.'), 'error')
        im_path = form['im_path'] = req.form.get('im_path', '')
        if im_path != req.app.cfg['im_path']:
            if req.app.cfg.change_single('im_path', im_path):
                if im_path:
                    flash(_(u'Changed path to ImageMagick'))
                else:
                    flash(_(u'ImageMagick is searched on the system path now.'))
            else:
                flash(_(u'Path to ImageMagick could not be changed.'), 'error')
        mimetypes = form['mimetypes'] = req.form.get('mimetypes', '')
        mimetypes = ';'.join(mimetypes.splitlines())
        if mimetypes != req.app.cfg['upload_mimetypes']:
            if req.app.cfg.change_single('upload_mimetypes', mimetypes):
                flash(_(u'Upload mimetype mapping altered successfully.'))
            else:
                flash(_(u'Upload mimetype mapping could not be altered.'), 'error')
        return redirect_to('admin/upload_config')

    return render_admin_response('admin/file_uploads/config.html',
                                 'options.uploads',
        im_version=get_im_version(),
        form=form,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def delete_upload(req, filename):
    fs_filename = get_filename(filename)
    if not exists(fs_filename):
        raise NotFound()

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('confirm'):
            try:
                remove(fs_filename)
            except (OSError, IOError):
                flash(_(u'Could not delete file %s.') %
                      escape(filename), 'error')
            else:
                flash(_(u'File %s deleted successfully.') %
                      escape(filename), 'remove')
        return redirect('admin/browse_uploads')

    return render_admin_response('admin/file_uploads/delete.html',
                                 'file_uploads.browse',
        hidden_form_data=make_hidden_fields(csrf_protector, redirect),
        filename=filename
    )


@require_role(ROLE_AUTHOR)
def help(req, page=''):
    """Show help page."""
    from zine.docs import load_page, get_resource

    rv = load_page(req.app, page)
    if rv is None:
        resource = get_resource(req.app, page)
        if resource is None:
            return render_admin_response('admin/help_404.html', 'system.help')
        return resource

    parts, is_index = rv
    ends_with_slash = not page or page.endswith('/')
    if is_index and not ends_with_slash:
        return redirect_to('admin/help', page=page + '/')
    elif not is_index and ends_with_slash:
        raise NotFound()

    return render_admin_response('admin/help.html', 'system.help', **parts)


def login(request):
    """Show a login page."""
    if request.user.is_somebody:
        return redirect_to('admin/index')
    form = LoginForm()

    if request.method == 'POST' and form.validate(request.form):
        request.login(form['user'], form['permanent'])
        return form.redirect('admin/index')

    return render_response('admin/login.html', form=form.as_widget())


def logout(request):
    """Just logout and redirect to the login screen."""
    request.logout()
    return redirect_back('admin/login')
