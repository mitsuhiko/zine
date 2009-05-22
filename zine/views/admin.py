# -*- coding: utf-8 -*-
"""
    zine.views.admin
    ~~~~~~~~~~~~~~~~

    This module implements the admin views. The admin interface is only
    available for admins, editors and authors but not for subscribers. For
    subscribers a simplified account management system exists at /account.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime
from os import remove, sep as pathsep
from os.path import exists
from urlparse import urlparse

from werkzeug import escape
from werkzeug.exceptions import NotFound, BadRequest, Forbidden

from zine.privileges import assert_privilege, require_privilege, \
     CREATE_ENTRIES, EDIT_OWN_ENTRIES, EDIT_OTHER_ENTRIES, \
     CREATE_PAGES, EDIT_OWN_PAGES, EDIT_OTHER_PAGES, MODERATE_COMMENTS, \
     MANAGE_CATEGORIES, BLOG_ADMIN
from zine.i18n import _, ngettext
from zine.application import get_request, url_for, emit_event, \
     render_response, get_application
from zine.models import User, Group, Post, Category, Comment, \
     STATUS_DRAFT, STATUS_PUBLISHED, COMMENT_MODERATED, COMMENT_UNMODERATED, \
     COMMENT_BLOCKED_USER, COMMENT_BLOCKED_SPAM
from zine.database import db, comments as comment_table, posts, \
     post_categories, post_links, secure_database_uri
from zine.utils import dump_json, load_json
from zine.utils.validators import is_valid_email, is_valid_url, check
from zine.utils.admin import flash, load_zine_reddit, require_admin_privilege
from zine.utils.text import gen_slug
from zine.utils.pagination import AdminPagination
from zine.utils.http import redirect_back, redirect_to, redirect
from zine.i18n import parse_datetime, format_system_datetime, \
     list_timezones, has_timezone, list_languages, has_language
from zine.importers import list_import_queue, load_import_dump, \
     delete_import_dump
from zine.parsers import parse
from zine.pluginsystem import install_package, InstallationError, \
     SetupError, get_object_name
from zine.pingback import pingback, PingbackError
from zine.forms import LoginForm, ChangePasswordForm, PluginForm, \
     LogOptionsForm, EntryForm, PageForm, BasicOptionsForm, URLOptionsForm, \
     PostDeleteForm, EditCommentForm, DeleteCommentForm, \
     ApproveCommentForm, BlockCommentForm, EditCategoryForm, \
     DeleteCategoryForm, EditUserForm, DeleteUserForm, \
     CommentMassModerateForm, CacheOptionsForm, EditGroupForm, \
     DeleteGroupForm, ThemeOptionsForm, DeleteImportForm, ExportForm, \
     MaintenanceModeForm, MarkCommentForm, make_config_form, make_import_form


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

    manage_items = [
        ('entries', url_for('admin/manage_entries'), _(u'Entries')),
        ('pages', url_for('admin/manage_pages'), _(u'Pages')),
        ('categories', url_for('admin/manage_categories'), _(u'Categories'))
    ]

    # set up the core navigation bar
    navigation_bar = [
        ('dashboard', url_for('admin/index'), _(u'Dashboard'), []),
        ('write', url_for('admin/new_entry'), _(u'Write'), [
            ('entry', url_for('admin/new_entry'), _(u'Entry')),
            ('page', url_for('admin/new_page'), _(u'Page'))
        ]),
        ('manage', url_for('admin/manage_entries'), _(u'Manage'), manage_items),
        ('comments', url_for('admin/manage_comments'), _(u'Comments'), [
            ('overview', url_for('admin/manage_comments'), _(u'Overview')),
            ('unmoderated', url_for('admin/show_unmoderated_comments'),
             _(u'Awaiting Moderation (%d)') %
             Comment.query.unmoderated().count()),
            ('approved', url_for('admin/show_approved_comments'),
             _(u'Approved (%d)') % Comment.query.approved().count()),
            ('blocked', url_for('admin/show_blocked_comments'),
             _(u'Blocked (%d)') % Comment.query.blocked().count()),
            ('spam', url_for('admin/show_spam_comments'),
             _(u'Spam (%d)') % Comment.query.spam().count())
        ])
    ]

    # set up the administration menu bar
    if request.user.has_privilege(BLOG_ADMIN):
        navigation_bar.extend([
            ('options', url_for('admin/options'), _(u'Options'), [
                ('basic', url_for('admin/basic_options'), _(u'Basic')),
                ('urls', url_for('admin/urls'), _(u'URLs')),
                ('theme', url_for('admin/theme'), _(u'Theme')),
                ('plugins', url_for('admin/plugins'), _(u'Plugins')),
                ('cache', url_for('admin/cache'), _(u'Cache'))
            ])
        ])
        manage_items.extend([
            ('users', url_for('admin/manage_users'), _(u'Users')),
            ('groups', url_for('admin/manage_groups'), _(u'Groups'))
        ])

    # add the about items to the navigation bar
    system_items = [
        ('help', url_for('admin/help'), _(u'Help')),
        ('about', url_for('admin/about_zine'), _(u'About'))
    ]
    if request.user.has_privilege(BLOG_ADMIN):
        system_items[0:0] = [
            ('information', url_for('admin/information'),
             _(u'Information')),
            ('maintenance', url_for('admin/maintenance'),
             _(u'Maintenance')),
            ('import', url_for('admin/import'), _(u'Import')),
            ('export', url_for('admin/export'), _(u'Export')),
            ('log', url_for('admin/log'), _('Log')),
            ('configuration', url_for('admin/configuration'),
             _(u'Configuration Editor'))
        ]

    navigation_bar.append(('system', system_items[0][1], _(u'System'),
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
                flash(_(u'Could not activate plugin “%(name)s”: %(error)s') % {
                    'name':     plugin.html_display_name,
                    'error':    plugin.setup_error
                })
                plugins_to_deactivate.append(plugin.name)

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
        } for type, msg in request.session.pop('admin/flashed_messages', [])],
        'active_pane': _active_menu_item
    }
    return render_response(template_name, **values)


def ping_post_links(form):
    """A helper that pings the links in a post."""
    pinged_successfully = []
    if form.request.app.cfg['maintenance_mode'] or \
       not form.post.is_published:
        flash(_(u'No URLs pinged so far because the post is not '
                u'publicly available'))
    elif form.post.parser_missing:
        flash(_(u'Could not ping URLs because the parser for the '
                u'post is not available any longer.'), 'error')
    else:
        this_url = url_for(form.post, _external=True)
        for url in form.find_new_links():
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
                        'error': e.message
                    }, 'error')
            else:
                pinged_successfully.append(html_url)
    if pinged_successfully:
        flash(ngettext(u'The following link was pinged successfully: %s',
                       u'The following links where pinged successfully: %s',
                       len(pinged_successfully)) %
              u', '.join(pinged_successfully))


@require_admin_privilege()
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
        last_posts=Post.query.published(ignore_privileges=True)
            .order_by(Post.pub_date.desc()).limit(5).all(),
        show_reddit = request.app.cfg['dashboard_reddit']
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


@require_admin_privilege(CREATE_ENTRIES | EDIT_OWN_ENTRIES | EDIT_OTHER_ENTRIES)
def manage_entries(request, page):
    """Show a list of entries."""
    entry_query = Post.query.type('entry')
    entries = entry_query.order_by([Post.status, Post.pub_date.desc()]) \
                         .limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_entries', page, PER_PAGE,
                                 entry_query.count())
    if not entries and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_entries.html', 'manage.entries',
                                 entries=entries, pagination=pagination)


def _make_post_dispatcher(action):
    """Creates a new dispatcher for the given content type action.  This
    already checks if the user can enter the admin panel but not if the
    user has the required privileges.
    """
    @require_admin_privilege()
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


def edit_entry(request, post=None):
    """Edit an existing entry or create a new one."""
    active_tab = post and 'manage.entries' or 'write.entry'
    initial = None
    body = request.args.get('body')
    if body:
        initial = {'text': body}
    form = EntryForm(post, initial)

    if post is None:
        assert_privilege(CREATE_ENTRIES)
    else:
        if not post.can_edit(request.user):
            raise Forbidden()

    if request.method == 'POST':
        if 'cancel' in request.form:
            return form.redirect('admin/manage_entries')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_post', post_id=post.id)
        elif 'preview' in request.form:
            if form.validate(request.form):
                text = form['text']
                parser = form['parser']
                try:
                    text = parse(text, parser=parser)
                except ValueError:
                    flash(_('Parser "%s" does not exist. Displaying raw text instead.' % escape(parser)), type='error')

                return render_admin_response('admin/edit_entry.html', active_tab,
                                             form=form.as_widget(True),
                                             text=text, taglist=form.taglist)
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
                ping_post_links(form)
            if 'save_and_continue' in request.form:
                return redirect_to('admin/edit_post', post_id=post.id)
            return form.redirect('admin/new_entry')
    return render_admin_response('admin/edit_entry.html', active_tab,
                                 form=form.as_widget(), taglist=form.taglist())


@require_admin_privilege()
def delete_entry(request, post):
    """This dialog deletes an entry.  Usually users are redirected here from the
    edit post view or the post index page.  If the entry was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.
    """
    form = PostDeleteForm(post)
    if not post.can_edit():
        raise Forbidden()

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


@require_admin_privilege(CREATE_PAGES | EDIT_OWN_PAGES | EDIT_OTHER_PAGES)
def manage_pages(request, page):
    """Show a list of pages."""
    page_query = Post.query.type('page')
    pages = page_query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_pages', page, PER_PAGE,
                                 page_query.count())
    if not pages and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_pages.html', 'manage.pages',
                                 pages=pages, pagination=pagination)


@require_admin_privilege()
def edit_page(request, post=None):
    """Edit an existing entry or create a new one."""
    active_tab = post and 'manage.pages' or 'write.page'
    form = PageForm(post)

    if post is None:
        assert_privilege(CREATE_PAGES)
    else:
        if not post.can_edit(request.user):
            raise Forbidden()

    if request.method == 'POST':
        if 'cancel' in request.form:
            return form.redirect('admin/manage_pages')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_post', post_id=post.id)
        elif 'preview' in request.form:
            if form.validate(request.form):
                text = form['text']
                parser = form['parser']
                try:
                    text = parse(text, parser=parser)
                except ValueError:
                    flash(_('Parser "%s" does not exist. Displaying raw text instead.' % escape(parser)), type='error')

                return render_admin_response('admin/edit_entry.html', active_tab,
                                             form=form.as_widget(True),
                                             text=text, taglist=form.taglist())
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
                ping_post_links(form)
            if 'save_and_continue' in request.form:
                return redirect_to('admin/edit_post', post_id=post.id)
            return form.redirect('admin/new_page')
    return render_admin_response('admin/edit_page.html', active_tab,
                                 form=form.as_widget(), taglist=form.taglist())


@require_admin_privilege()
def delete_page(request, post):
    """This dialog deletes a page.  Usually users are redirected here from the
    edit post view or the page indexpage.  If the page was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.
    """
    form = PostDeleteForm(post)
    if not post.can_edit():
        raise Forbidden()

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


def _handle_comments(identifier, title, query, page,
                     endpoint='admin/manage_comments'):
    request = get_request()
    comments = query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination(endpoint, page, PER_PAGE, query.count())
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

            # or block them all
            elif 'block' in request.form:
                if 'confirm' in request.form:
                    form.block_selection()
                    db.commit()
                    flash(_(u'Blocked all the selected comments.'))
                    return redirect_to('admin/manage_comments')
                return render_admin_response('admin/block_comments.html',
                                             form=form.as_widget())

            # or mark them all as spam
            elif 'spam' in request.form:
                if 'confirm' in request.form:
                    form.mark_selection_as_spam()
                    db.commit()
                    flash(_(u'Reported all the selected comments as SPAM.'))
                    return redirect_to('admin/manage_comments')
                return render_admin_response('admin/mark_spam_comments.html',
                                             form=form.as_widget())
            # or mark them all as ham
            elif 'ham' in request.form:
                if 'confirm' in request.form:
                    form.mark_selection_as_ham()
                    db.commit()
                    flash(_(u'Reported all the selected comments as NOT SPAM.'))
                    return redirect_to('admin/manage_comments')
                return render_admin_response('admin/mark_ham_comments.html',
                                             form=form.as_widget())
    tab = 'comments'
    if identifier is not None:
        tab += '.' + identifier
    return render_admin_response('admin/manage_comments.html', tab,
                                 comments_title=title, form=form.as_widget(),
                                 pagination=pagination)


@require_admin_privilege(MODERATE_COMMENTS)
def manage_comments(request, page):
    """Show all the comments."""
    return _handle_comments('overview', _(u'All Comments'),
                            Comment.query, page)

@require_admin_privilege(MODERATE_COMMENTS)
def show_unmoderated_comments(request, page):
    """Show all unmoderated and user-blocked comments."""
    return _handle_comments('unmoderated', _(u'Comments Awaiting Moderation'),
                            Comment.query.unmoderated(), page,
                            endpoint='admin/show_unmoderated_comments')

@require_admin_privilege(MODERATE_COMMENTS)
def show_approved_comments(request, page):
    """Show all moderated comments."""
    return _handle_comments('approved', _(u'Approved Commments'),
                            Comment.query.approved(), page,
                            endpoint='admin/show_approved_comments')

@require_admin_privilege(MODERATE_COMMENTS)
def show_blocked_comments(request, page):
    """Show all spam comments."""
    return _handle_comments('blocked', _(u'Blocked'),
                            Comment.query.blocked(), page,
                            endpoint='admin/show_blocked_comments')

@require_admin_privilege(MODERATE_COMMENTS)
def show_spam_comments(request, page):
    """Show all spam comments."""
    return _handle_comments('spam', _(u'Spam'), Comment.query.spam(), page,
                            endpoint='admin/show_spam_comments')


@require_admin_privilege(MODERATE_COMMENTS)
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


@require_admin_privilege(MODERATE_COMMENTS)
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


@require_admin_privilege(MODERATE_COMMENTS)
def delete_comment(request, comment_id):
    """This dialog delets a comment.  Usually users are redirected here from the
    comment moderation page or the comment edit page.  If the comment was not
    deleted, the user is taken back to the page he's coming from or back to
    the edit page if the information is invalid.  The same happens if the post
    was deleted but if the referrer is the edit page. Then the user is taken
    back to the index so that he doesn't end up an a "page not found" error page.
    """
    comment = Comment.query.get(comment_id)
    if comment is None or comment.is_deleted:
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


@require_admin_privilege(MODERATE_COMMENTS)
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


@require_admin_privilege(MODERATE_COMMENTS)
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

@require_admin_privilege(MODERATE_COMMENTS)
def report_comment_spam(request, comment_id):
    """Block a comment."""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise NotFound()
    form = MarkCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('confirm'):
            form.mark_as_spam()
            db.commit()
            flash(_(u'Comment by %s reported as Spam successfully.') %
                  escape(comment.author), 'configure')
        return form.redirect('admin/manage_comments')

    return render_admin_response('admin/mark_comment.html',
                                 'comments.overview', form=form.as_widget(),
                                 form_action=_('Spam'))

@require_admin_privilege(MODERATE_COMMENTS)
def report_comment_ham(request, comment_id):
    """Block a comment."""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise NotFound()
    form = MarkCommentForm(comment)

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('confirm'):
            form.mark_as_ham()
            db.commit()
            flash(_(u'Comment by %s reported as NOT Spam successfully.') %
                  escape(comment.author), 'configure')
        return form.redirect('admin/manage_comments')

    return render_admin_response('admin/mark_comment.html',
                                 'comments.overview', form=form.as_widget(),
                                 form_action=_(u'NOT Spam'))

@require_admin_privilege(MANAGE_CATEGORIES)
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


@require_admin_privilege(MANAGE_CATEGORIES)
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


@require_admin_privilege(MANAGE_CATEGORIES)
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
            form.add_invalid_redirect_target('admin/edit_category',
                                             category_id=category.id)
            form.delete_category()
            flash(_(u'Category %s deleted successfully.') % escape(category.name))
            db.commit()
            return form.redirect('admin/manage_categories')

    return render_admin_response('admin/delete_category.html', 'manage.categories',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
def manage_users(request, page):
    """Show all users in a list."""
    users = User.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/manage_users', page, PER_PAGE,
                                 User.query.count())
    if not users and page != 1:
        raise NotFound()
    return render_admin_response('admin/manage_users.html', 'manage.users',
                                 users=users, pagination=pagination)


@require_admin_privilege(BLOG_ADMIN)
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

    return render_admin_response('admin/edit_user.html', 'manage.users',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
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

    return render_admin_response('admin/delete_user.html', 'manage.users',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
def manage_groups(request):
    groups = Group.query.all()
    return render_admin_response('admin/manage_groups.html', 'manage.groups',
                                 groups=groups)

@require_admin_privilege(BLOG_ADMIN)
def edit_group(request, group_id=None):
    """Edit a Group.  This is used to create a group as well."""
    group = None
    if group_id is not None:
        group = Group.query.get(group_id)
        if group is None:
            raise NotFound()
    form = EditGroupForm(group)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/manage_groups')
        elif request.form.get('delete') and group:
            return redirect_to('admin/delete_group', group_id=group.id)
        elif form.validate(request.form):
            if group is None:
                group = form.make_group()
                msg = _(u'Group %s created successfully.')
                icon = 'add'
            else:
                form.save_changes()
                msg = _(u'Group %s edited successfully.')
                icon = 'info'
            db.commit()
            html_group_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(group)),
                escape(group.name))
            flash(msg % html_group_detail, icon)

            if request.form.get('save'):
                return form.redirect('admin/manage_groups')
            return redirect_to('admin/edit_group', group_id=group.id)

    return render_admin_response('admin/edit_group.html', 'manage.groups',
                                 form=form.as_widget())

@require_admin_privilege(BLOG_ADMIN)
def delete_group(request, group_id):
    """Like all other delete screens just that it deletes a group."""
    group = Group.query.get(group_id)
    if group is None:
        raise NotFound()
    form = DeleteGroupForm(group)

    if request.method == 'POST':
        if request.form.get('cancel'):
            return form.redirect('admin/edit_group', group_id=group.id)
        elif request.form.get('confirm') and form.validate(request.form):
            form.add_invalid_redirect_target('admin/edit_group', group_id=group.id)
            form.delete_group()
            db.commit()
            return form.redirect('admin/manage_groups')

    return render_admin_response('admin/delete_group.html', 'manage.groups',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
def options(request):
    """So far just a redirect page, later it would be a good idea to have
    a page that shows all the links to configuration things in form of
    a simple table.
    """
    return redirect_to('admin/basic_options')


@require_admin_privilege(BLOG_ADMIN)
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


@require_admin_privilege(BLOG_ADMIN)
def urls(request):
    """A config page for URL depending settings."""
    form = URLOptionsForm()

    if request.method == 'POST' and form.validate(request.form):
        form.apply()
        db.commit()
        flash(_(u'URL configuration changed.'), 'configure')
        # because the next request could reload the application and move
        # the admin interface we construct the URL to this page by hand.
        return redirect(form['admin_url_prefix'][1:] + '/options/urls')

    return render_admin_response('admin/url_options.html', 'options.urls',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
def theme(request):
    """Allow the user to select one of the themes that are available."""
    form = ThemeOptionsForm()

    if request.method == 'GET':
        if 'configure' in request.args:
            return redirect_to('admin/configure_theme')
        elif form.validate(request.args):
            new_theme = request.args.get('select')
            if new_theme in request.app.themes:
                request.app.cfg.change_single('theme', new_theme)
                flash(_(u'Theme changed successfully.'), 'configure')
                return redirect_to('admin/theme')

    return render_admin_response('admin/theme.html', 'options.theme',
        themes=sorted(request.app.themes.values(),
                      key=lambda x: x.name == 'default' or x.display_name.lower()),
        current_theme=request.app.theme,
        form=form.as_widget()
    )


@require_admin_privilege(BLOG_ADMIN)
def configure_theme(request):
    if not request.app.theme.configurable:
        flash(_(u'This theme is not configurable'), 'error')
        return redirect_to('admin/theme')
    return request.app.theme.configuration_page(request)


@require_admin_privilege(BLOG_ADMIN)
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
                flash(_(u'Plugin “%s” added successfully. You can now '
                        u'enable it in the plugin list.') %
                      plugin.html_display_name, 'add')

        return redirect_to('admin/plugins')

    return render_admin_response('admin/plugins.html', 'options.plugins',
        form=form.as_widget(),
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name)
    )


@require_admin_privilege(BLOG_ADMIN)
def remove_plugin(request, plugin):
    """Remove an inactive, instance installed plugin completely."""
    plugin = request.app.plugins.get(plugin)
    if plugin is None or \
       not plugin.instance_plugin or \
       plugin.active:
        raise NotFound()
    form = RemovePluginForm()

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('confirm'):
            try:
                plugin.remove()
            except IOError:
                flash(_(u'Could not remove the plugin “%s” because an '
                        u'IO error occurred. Wrong permissions?') %
                      plugin.html_display_name)
            flash(_(u'The plugin “%s” was removed from the instance '
                    u'successfully.') % escape(plugin.display_name), 'remove')
        return form.redirect('admin/plugins')

    return render_admin_response('admin/remove_plugin.html', 'options.plugins',
        plugin=plugin,
        form=form.as_widget()
    )


@require_admin_privilege(BLOG_ADMIN)
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

    return render_admin_response('admin/cache.html', 'options.cache',
                                 form=form.as_widget())


@require_admin_privilege(BLOG_ADMIN)
def configuration(request):
    """Advanced configuration editor.  This is useful for development or if a
    plugin doesn't ship an editor for the configuration values.  Because all
    the values are not further checked it could easily be that Zine is
    left in an unusable state if a variable is set to something bad.  Because
    of this the editor shows a warning and must be enabled by hand.
    """
    form = make_config_form()

    if request.method == 'POST':
        if request.form.get('enable_editor'):
            request.session['ace_on'] = True
        elif request.form.get('disable_editor'):
            request.session['ace_on'] = False
        elif form.validate(request.form):
            form.apply()
            return redirect_to('admin/configuration')

    return render_admin_response('admin/configuration.html',
                                 'system.configuration',
                                 form=form.as_widget(), editor_enabled=
                                 request.session.get('ace_on', False))


@require_admin_privilege(BLOG_ADMIN)
def maintenance(request):
    """Enable / Disable maintenance mode."""
    cfg = request.app.cfg
    form = MaintenanceModeForm()
    if request.method == 'POST' and form.validate(request.form):
        cfg.change_single('maintenance_mode', not cfg['maintenance_mode'])
        if not cfg['maintenance_mode']:
            flash(_(u'Maintenance mode disabled.  The blog is now '
                    u'publicly available.'), 'configure')
        return redirect_to('admin/maintenance')

    return render_admin_response('admin/maintenance.html',
                                 'system.maintenance',
        maintenance_mode=cfg['maintenance_mode'],
        form=form.as_widget()
    )


@require_admin_privilege(BLOG_ADMIN)
def import_dump(request):
    """Show the current import queue or add new items."""
    return render_admin_response('admin/import.html', 'system.import',
        importers=sorted(request.app.importers.values(),
                         key=lambda x: x.title.lower()),
        queue=list_import_queue(request.app)
    )


@require_admin_privilege(BLOG_ADMIN)
def inspect_import(request, id):
    """Inspect a database dump."""
    blog = load_import_dump(request.app, id)
    if blog is None:
        raise NotFound()
    form = make_import_form(blog)

    # perform the actual import here
    if request.method == 'POST':
        if 'cancel' in request.form:
            return redirect_to('admin/maintenance')
        elif 'delete' in request.form:
            return redirect_to('admin/delete_import', id=id)
        elif form.validate(request.form):
            return render_admin_response('admin/perform_import.html',
                                         'system.import',
                live_log=form.perform_import(),
                _stream=True
            )

    return render_admin_response('admin/inspect_import.html',
                                 'system.import', blog=blog,
                                 form=form.as_widget(), dump_id=id)


@require_admin_privilege(BLOG_ADMIN)
def delete_import(request, id):
    """Delete an imported file."""
    dump = load_import_dump(request.app, id)
    if dump is None:
        raise NotFound()
    form = DeleteImportForm()

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('cancel'):
            return form.redirect('admin/inspect_import', id=id)
        elif request.form.get('confirm'):
            form.add_invalid_redirect_target('admin/inspect_import', id=id)
            delete_import_dump(request.app, id)
            flash(_(u'The imported dump “%s” was deleted successfully.') %
                  escape(dump.title), 'remove')
            return form.redirect('admin/import')

    return render_admin_response('admin/delete_import.html',
                                 'system.import',
        dump=dump,
        form=form.as_widget()
    )


@require_admin_privilege(BLOG_ADMIN)
def export(request):
    """Export the blog to the ZXA format."""
    form = ExportForm()

    if request.method == 'POST' and form.validate(request.form):
        if request.form.get('format') == 'zxa':
            from zine.zxa import export
            response = export(request.app)
            response.headers['Content-Disposition'] = 'attachment; ' \
                'filename="%s.zxa"' % '_'.join(request.app.cfg['blog_title'].split())
            return response
    return render_admin_response('admin/export.html', 'system.export',
        form=form.as_widget()
    )


@require_admin_privilege(BLOG_ADMIN)
def information(request):
    """Shows some details about this Zine installation.  It's useful for
    debugging and checking configurations.  If severe errors in a Zine
    installation occur it's a good idea to dump this page and attach it to
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
        privileges=request.app.list_privileges(),
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
            'filename="zine-environment.html"'

    return response


@require_admin_privilege(BLOG_ADMIN)
def log(request, page):
    page = request.app.log.view().get_page(page)
    form = LogOptionsForm()
    if request.method == 'POST' and form.validate(request.form):
        form.apply()
        flash(_('Log changes saved.'), 'configure')
        return redirect_to('admin/log', page=page.number)
    return render_admin_response('admin/log.html', 'system.log',
                                 page=page, form=form.as_widget())


@require_admin_privilege()
def about_zine(request):
    """Just show the zine license and some other legal stuff."""
    return render_admin_response('admin/about_zine.html',
                                 'system.about')


@require_admin_privilege()
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


@require_admin_privilege()
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
