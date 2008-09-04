# -*- coding: utf-8 -*-
"""
    zine.views.admin
    ~~~~~~~~~~~~~~~~

    This module implements the admin views. The admin interface is only
    available for admins, editors and authors but not for subscribers. For
    subscribers a simplified account management system exists at /account.

    The admin panel tries it's best to avoid CSRF attacks and some similar
    problems by using the hidden form fields from the utils package.  For
    more details see the docstrings of the `CSRFProtector` and
    `IntelligentRedirect` classes located there.  Do this before you try to
    add your own admin panel pages!

    :copyright: 2007-2008 by Armin Ronacher, Christopher Grebs, Pedro Algarvio,
                             Ali Afshar.
    :license: GNU GPL.
"""
from datetime import datetime
from os import remove, sep as pathsep
from os.path import exists
from zine.api import *
from zine.models import User, Post, Tag, Comment, Page, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED, COMMENT_MODERATED, COMMENT_UNMODERATED, \
     COMMENT_BLOCKED_USER, COMMENT_BLOCKED_SPAM
from zine.database import comments as comment_table, posts, \
     post_tags, post_links
from zine.utils import dump_json, load_json
from zine.utils.validators import is_valid_email, is_valid_url
from zine.utils.admin import flash, gen_slug, commit_config_change
from zine.utils.pagination import AdminPagination
from zine.utils.xxx import make_hidden_fields, CSRFProtector, \
     IntelligentRedirect, StreamReporter
from zine.utils.uploads import guess_mimetype, get_upload_folder, \
     list_files, list_images, get_im_version, get_im_path, \
     touch_upload_folder, upload_file, create_thumbnail, file_exists, \
     get_filename
from zine.i18n import parse_datetime, format_system_datetime, \
     list_timezones, has_timezone, list_languages, has_language
from zine.importers import list_import_queue, load_import_dump, \
     delete_import_dump, perform_import
from zine.pluginsystem import install_package, InstallationError, \
     SetupError
from zine.pingback import pingback, PingbackError
from urlparse import urlparse
from werkzeug import escape
from werkzeug.exceptions import NotFound, BadRequest


#: how many posts / comments should be displayed per page?
PER_PAGE = 20


def simple_redirect(*args, **kwargs):
    """A function "simple redirect" that works like the redirect function
    in the views, just that it doesn't use the `IntelligentRedirect` which
    sometimes doesn't do what we want. (like redirecting to target pages
    and not using backredirects)
    """
    return redirect(url_for(*args, **kwargs))


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
        ('dashboard', url_for('admin/index'), _('Dashboard'), []),
        ('posts', url_for('admin/show_posts'), _('Posts'), [
            ('overview', url_for('admin/show_posts'), _('Overview')),
            ('write', url_for('admin/new_post'), _('Write Post')),
            ('tags', url_for('admin/show_tags'), _('Tags'))
        ]),
        ('comments', url_for('admin/show_comments'), _('Comments'), [
            ('overview', url_for('admin/show_comments'), _('Overview')),
            ('unmoderated', url_for('admin/show_unmoderated_comments'),
             _('Awaiting Moderation (%d)') %
             Comment.objects.unmoderated().count()),
            ('spam', url_for('admin/show_spam_comments'),
             _('Spam (%d)') % Comment.objects.spam().count())
        ]),
        ('file_uploads', url_for('admin/browse_uploads'), _('Uploads'), [
            ('browse', url_for('admin/browse_uploads'), _('Browse')),
            ('upload', url_for('admin/new_upload'), _('Upload')),
            ('thumbnailer', url_for('admin/upload_thumbnailer'),
             _('Create Thumbnails'))
        ])
    ]

    # set up the administration menu bar
    if request.user.role == ROLE_ADMIN:
        navigation_bar.insert(3,
            ('pages', url_for('admin/show_pages'), _('Pages'), [
                ('overview', url_for('admin/show_pages'), _('Overview')),
                ('write', url_for('admin/write_page'), _('Write Page')),
        ]))
        navigation_bar += [
            ('users', url_for('admin/show_users'), _('Users'), [
                ('overview', url_for('admin/show_users'), _('Overview')),
                ('edit', url_for('admin/new_user'), _('Edit User'))
            ]),
            ('options', url_for('admin/options'), _('Options'), [
                ('basic', url_for('admin/basic_options'), _('Basic')),
                ('urls', url_for('admin/urls'), _('URLs')),
                ('theme', url_for('admin/theme'), _('Theme')),
                ('pages', url_for('admin/pages_config'), _('Pages')),
                ('uploads', url_for('admin/upload_config'), _('Uploads')),
                ('plugins', url_for('admin/plugins'), _('Plugins')),
                ('cache', url_for('admin/cache'), _('Cache'))
            ])
        ]

    # add the about items to the navigation bar
    system_items = [
        ('information', url_for('admin/information'), _('Information')),
        ('help', url_for('admin/help'), _('Help')),
        ('about', url_for('admin/about_zine'), _('About'))
    ]
    if request.user.role == ROLE_ADMIN:
        system_items[1:1] = [
             ('maintenance', url_for('admin/maintenance'),
             _('Maintenance')),
             ('import', url_for('admin/import'), _('Import')),
             ('export', url_for('admin/export'), _('Export')),
             ('configuration', url_for('admin/configuration'),
              _('Configuration Editor'))
        ]

    navigation_bar.append(('system', url_for('admin/information'), _('System'),
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
        flash(_('Zine is in maintenance mode. Don\'t forget to '
                '<a href="%s">turn it off again</a> once you finish your '
                'changes.') % url_for('admin/maintenance'))

    # check for broken plugins if we have the plugin guard enabled
    if request.app.cfg['plugin_guard']:
        for plugin in request.app.plugins.itervalues():
            if plugin.active and plugin.setup_error is not None:
                plugin.deactivate()
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
                                    f_globals.get('__file__', _('unknown file')),
                        'line': plugin.setup_error[2].tb_lineno
                    }
                flash(msg, 'error')

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


@require_role(ROLE_AUTHOR)
def do_index(request):
    """Show the admin interface index page which is a wordpress inspired
    dashboard (doesn't exist right now).

    Once it's finished it should show the links to the most useful pages
    such as "new post", etc. and the recent blog activity (unmoderated
    comments etc.)
    """
    # the template loads the planet with a separate http request via
    # javascript to not slow down the page loading
    if request.args.get('load') == 'planet':
        return Response('<p>XXX: not supported yet :-(</p>')

    return render_admin_response('admin/index.html', 'dashboard',
        drafts=Post.objects.drafts().all(),
        unmoderated_comments=Comment.objects.unmoderated().all(),
        your_posts=Post.objects.filter(
            Post.author_id == request.user.user_id
        ).count(),
        last_posts=Post.objects.published(ignore_role=True)
            .order_by(Post.pub_date.desc()).limit(5).all()
    )


def do_bookmarklet(request):
    """Requests to this view are usually triggered by the bookmarklet
    from the edit-post page.  Currently this is a redirect to the new-post
    page with some small modifications but in the future this could be
    expanded to add a wizard or something.
    """
    if request.args['mode'] != 'newpost':
        raise BadRequest()
    body = '%s\n\n<a href="%s">%s</a>' % (
        request.args.get('text', _('Text here...')),
        request.args['url'],
        request.args.get('title', _('Untitled Page'))
    )
    return simple_redirect('admin/new_post',
        title=request.args.get('title'),
        body=body
    )


@require_role(ROLE_AUTHOR)
def do_show_posts(request, page):
    """Show a list of posts for post moderation."""
    posts = Post.objects.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/show_posts', page, PER_PAGE,
                                 Post.objects.count())
    if not posts and page != 1:
        raise NotFound()
    return render_admin_response('admin/show_posts.html', 'posts.overview',
                                 drafts=Post.objects.drafts().all(),
                                 posts=posts,
                                 pagination=pagination)


@require_role(ROLE_AUTHOR)
def do_edit_post(request, post_id=None):
    """Edit or create a new post.  So far this dialog doesn't emit any events
    although it would be a good idea to allow plugins to add custom fields
    into the template.
    """
    tags = []
    errors = []
    form = {}
    post = exclude = None
    missing_parser = None
    keep_post_texts = False
    parsers = request.app.list_parsers()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()
    old_texts = None

    # edit existing post
    if post_id is not None:
        new_post = False
        post = Post.objects.get(post_id)
        exclude = post.post_id
        if post is None:
            raise NotFound()
        form.update(
            title=post.title,
            body=post.raw_body,
            intro=post.raw_intro,
            tags=[t.slug for t in post.tags],
            post_status=post.status,
            comments_enabled=post.comments_enabled,
            pings_enabled=post.pings_enabled,
            pub_date=format_system_datetime(post.pub_date),
            slug=post.slug,
            author=post.author.username,
            parser=post.parser
        )
        old_texts = (form['intro'], form['body'])
        if post.parser_missing:
            missing_parser = post.parser

    # create new post
    else:
        new_post = True
        form.update(
            title=request.args.get('title', ''),
            body=request.args.get('body', ''),
            intro='',
            tags=[],
            post_status=STATUS_DRAFT,
            comments_enabled=request.app.cfg['comments_enabled'],
            pings_enabled=request.app.cfg['pings_enabled'],
            pub_date=_('now'),
            slug='',
            author=request.user.username,
            parser=request.app.cfg['default_parser']
        )

    # tick the "ping urls from text" checkbox if either we have a
    # new post or we edit an old post and the parser is available
    if request.method != 'POST':
        form['ping_from_text'] = not post or not post.parser_missing

    # handle incoming data and create/update the post
    else:
        csrf_protector.assert_safe()

        # handle cancel
        if request.form.get('cancel'):
            return redirect('admin/show_posts')

        # handle delete, redirect to confirmation page
        if request.form.get('delete') and post_id is not None:
            return simple_redirect('admin/delete_post', post_id=post_id)

        form['title'] = title = request.form.get('title')
        if not title:
            errors.append(_('You have to provide a title.'))
        elif len(title) > 150:
            errors.append(_('Your title is too long.'))
        form['body'] = body = request.form.get('body')
        if not body:
            errors.append(_('You have to provide a body.'))
        form['intro'] = intro = request.form.get('intro') or u''
        try:
            form['post_status'] = post_status = int(request.form['post_status'])
            if post_status < 0 or post_status > 2:
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            errors.append(_('Invalid post status'))
        form['comments_enabled'] = 'comments_enabled' in request.form
        form['pings_enabled'] = 'pings_enabled' in request.form
        form['ping_from_text'] = 'ping_from_text' in request.form
        form['parser'] = parser = request.form.get('parser')
        if missing_parser and parser == post.parser:
            if old_texts != (intro, body):
                errors.append(_('You cannot change the text of a post which '
                                'parser does not exist any longer.'))
            else:
                keep_post_texts = True
        elif parser not in request.app.parsers:
            errors.append(_(u'Unknown parser “%s”.') % parser)
        try:
            pub_date = parse_datetime(request.form.get('pub_date') or _('now'))
        except ValueError:
            errors.append(_('Invalid publication date.'))

        username = request.form.get('author')
        if not username:
            author = post and post.author or request.user
            username = author.username
        else:
            author = User.objects.filter_by(username=username).first()
            if author is None:
                errors.append(_(u'Unknown author “%s”.') % username)
        form['author'] = username
        form['slug'] = slug = request.form.get('slug') or None
        if slug:
            if '/' in slug:
                errors.append(_('A slug cannot contain a slash.'))
            elif len(slug) > 150:
                errors.append(_('Your slug is too long'))
        form['tags'] = []
        tags = []
        for tag in request.form.getlist('tags'):
            t = Tag.objects.filter_by(slug=tag).first()
            if t is not None:
                tags.append(t)
                form['tags'].append(tag)
            else:
                errors.append(_(u'Unknown tag “%s”.') % tag)

        # if someone adds a tag we don't save the post but just add
        # a tag to the list and assign it to the post list.
        add_tag = request.form.get('add_tag')
        if add_tag:
            # XXX: what happens if the slug is empty or the slug
            #      exists already?
            form['tags'].append(Tag(add_tag).slug)
            db.commit()
            del errors[:]

        # if there is no need tag and there are no errors we save the post
        elif not errors:
            if new_post:
                post = Post(title, author, body, intro, slug,
                            pub_date, parser=parser)
            else:
                post.title = title
                post.author_id = author.user_id
                if not keep_post_texts:
                    # Always set parser before raw_body and raw_intro because
                    # those require the correct parser to be defined.
                    post.parser = parser
                    post.raw_body = body
                    post.raw_intro = intro
                if slug:
                    post.slug = slug
                else:
                    post.auto_slug()
                post.pub_date = pub_date
            post.tags[:] = tags
            post.comments_enabled = form['comments_enabled']
            post.pings_enabled = form['pings_enabled']
            post.status = post_status
            post.last_update = max(datetime.utcnow(), pub_date)
            db.commit()
            #! a after-post-saved event is always extremely useful. plugins can
            #! use it to update search indexes / feeds or whatever
            emit_event('after-post-saved', post)

            html_post_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(post)),
                escape(post.title)
            )

            # do automatic pingbacking if we can get all the links
            # by parsing the post, that is wanted and the post is
            # published.
            if form['ping_from_text']:
                if request.app.cfg['maintenance_mode'] or not post.is_published:
                    flash(_('No URLs pinged so far because the post is not '
                            'publicly available'))
                elif post.parser_missing:
                    flash(_('Could not ping URLs because the parser for the '
                            'post is not available any longer.'), 'error')
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
                                flash(_('Could not ping %(url)s: %(error)s') % {
                                    'url': html_url,
                                    'error': e.description
                                }, 'error')
                        else:
                            flash(_('%s was pinged successfully.') %
                                    html_url)

            if new_post:
                flash(_('The post %s was created successfully.') %
                      html_post_detail, 'add')
            else:
                flash(_('The post %s was updated successfully.') %
                      html_post_detail)

            if request.form.get('save'):
                return redirect('admin/new_post')
            return simple_redirect('admin/edit_post', post_id=post.post_id)

    for error in errors:
        flash(error, 'error')

    # tell the user if the parser is missing and we reinsert the
    # parser into the list.
    if missing_parser:
        parsers.insert(0, (missing_parser, _(u'Missing Parser “%s”') %
                           missing_parser))
        flash(_(u'This post was created with the parser “%(parser)s” that is '
                u'not installed any longer.  Because of that Zine '
                u'doesn\'t allow modifcations on the text until you either '
                u'change the parser or reinstall/activate the plugin that '
                u'provided that parser.') % {'parser': escape(missing_parser)},
              'error')

    return render_admin_response('admin/edit_post.html', 'posts.write',
        new_post=new_post,
        form=form,
        tags=Tag.objects.all(),
        post=post,
        drafts=list(Post.objects.drafts(exclude=exclude).all()),
        can_change_author=request.user.role >= ROLE_EDITOR,
        post_status_choices=[
            (STATUS_PUBLISHED, _('Published')),
            (STATUS_DRAFT, _('Draft')),
            (STATUS_PRIVATE, _('Private'))
        ],
        parsers=parsers,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_post(request, post_id):
    """This dialog deletes a post.  Usually users are redirected here from the
    edit post view or the post index page.  If the post was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.  The same happens if the post was
    deleted but if the referrer is the edit page. Then the user is taken back to
    the index so that he doesn't end up an a "page not found" error page.
    """
    post = Post.objects.get(post_id)
    if post is None:
        raise NotFound()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect('admin/edit_post', post_id=post.post_id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/edit_post', post_id=post.post_id)
            #! plugins can use this to react to post deletes.  They can't stop
            #! the deleting of the post but they can delete information in
            #! their own tables so that the database is consistent afterwards.
            emit_event('before-post-deleted', post)
            db.delete(post)
            flash(_('The post %s was deleted successfully.') %
                  escape(post.title), 'remove')
            db.commit()
            return redirect('admin/show_posts')

    return render_admin_response('admin/delete_post.html', 'posts.write',
        post=post,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


def _handle_comments(identifier, title, query, page):
    request = get_request()
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()

        if 'comment_list' in request.form:
            comments = map(int, request.form['comment_list'].split())
        else:
            comments = request.form.getlist('comment', type=int)

        if comments and not 'cancel' in request.form:
            query = comment_table.c.comment_id.in_(comments)

            # delete the comments in the list
            if 'delete' in request.form:
                if 'confirm' in request.form:
                    db.execute(comment_table.delete(query))
                    db.commit()
                    return simple_redirect('admin/show_comments')
                return render_admin_response('admin/delete_comments.html',
                                             hidden_form_data=csrf_protector,
                                             comment_list=comments)

            # or approve them all
            elif 'approve' in request.form:
                db.execute(comment_table.update(query), dict(
                    status=COMMENT_MODERATED,
                    blocked_msg=''
                ))
                db.commit()
                flash(_('Approved all the selected comments.'))
                return simple_redirect('admin/show_comments')

    comments = query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/show_comments', page, PER_PAGE,
                                 query.count())
    if not comments and page != 1:
        raise NotFound()
    tab = 'comments'
    if identifier is not None:
        tab += '.' + identifier
    return render_admin_response('admin/show_comments.html', tab,
                                 comments_title=title,
                                 comments=comments,
                                 pagination=pagination,
                                 hidden_form_data=csrf_protector)


@require_role(ROLE_AUTHOR)
def do_show_comments(request, page):
    """Show all the comments."""
    return _handle_comments('overview', _('All Comments'),
                            Comment.objects.query, page)


@require_role(ROLE_AUTHOR)
def do_show_unmoderated_comments(request, page):
    """Show all unmoderated and user-blocked comments."""
    return _handle_comments('unmoderated', _('Comments Awaiting Moderation'),
                            Comment.objects.unmoderated(), page)


@require_role(ROLE_AUTHOR)
def do_show_spam_comments(request, page):
    """Show all spam comments."""
    return _handle_comments('spam', _('Spam'), Comment.objects.spam(), page)


@require_role(ROLE_AUTHOR)
def do_show_post_comments(request, page, post_id):
    """Show all comments for a single post."""
    post = Post.objects.get(post_id)
    if post is None:
        raise NotFound()
    link = '<a href="%s">%s</a>' % (
        url_for('admin/edit_post', post_id=post_id),
        escape(post.title)
    )
    return _handle_comments(None, _(u'Comments for “%s”') % link,
                            Comment.objects.comments_for_post(post_id), page)


@require_role(ROLE_AUTHOR)
def do_edit_comment(request, comment_id):
    """Edit a comment.  Unlike the post edit screen it's not possible to
    create new comments from here, that has to happen from the post page.
    """
    comment = Comment.objects.get(comment_id)
    if comment is None:
        raise NotFound()

    errors = []
    form = {
        'author':       comment.author,
        'email':        comment.email,
        'www':          comment.www,
        'body':         comment.raw_body,
        'parser':       comment.parser,
        'pub_date':     format_system_datetime(comment.pub_date),
        'blocked':      comment.blocked,
        'blocked_msg':  comment.blocked_msg
    }
    old_text = comment.raw_body
    missing_parser = None
    keep_comment_text = False
    if comment.parser_missing:
        missing_parser = comment.parser

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        www = None

        # cancel
        if request.form.get('cancel'):
            return redirect('admin/show_comments')

        # delete
        if request.form.get('delete'):
            return simple_redirect('admin/delete_comment', comment_id=comment_id)

        if comment.anonymous:
            form['author'] = author = request.form.get('author')
            if not author:
                errors.append(_('You have to give the comment an author.'))
            form['email'] = email = request.form.get('email', '')
            if email and not is_valid_email(email):
                errors.append(_('You have to provide a valid mail address for '
                                'the author.'))
            form['www'] = www = request.form.get('www')
        form['body'] = body = request.form.get('body')
        form['parser'] = parser = request.form.get('parser')
        if missing_parser and parser == comment.parser:
            if old_text != body:
                errors.append(_('You cannot change the text of a comment '
                                'if the parser is missing.'))
            else:
                keep_comment_text = True
        elif parser not in request.app.parsers:
            errors.append(_(u'Unknown parser “%s”.') % parser)
        if not body:
            errors.append(_('Need a text for this comment.'))
        if www and not is_valid_url(www):
            errors.append(_('You have to ommitt the url or provide a '
                            'valid one.'))
        form['pub_date'] = pub_date = request.form.get('pub_date')
        try:
            pub_date = parse_datetime(pub_date)
        except ValueError:
            errors.append(_('Invalid date for comment.'))
        form['blocked'] = blocked = bool(request.form.get('blocked'))
        form['blocked_msg'] = blocked_msg = \
            request.form.get('blocked_msg', '')

        if not errors:
            if comment.anonymous:
                comment.author = author
                comment.email = email
                comment.www = www
            comment.pub_date = pub_date
            if not keep_comment_text:
                # always set parser before raw body because of callbacks.
                comment.parser = parser
                comment.raw_body = body
            if not blocked:
                comment.status = COMMENT_MODERATED
                comment.blocked_msg = ''
            else:
                comment.status = COMMENT_BLOCKED_USER
                if not blocked_msg:
                    blocked_msg = _('blocked by %s') % \
                        request.user.display_name
                comment.blocked_msg = blocked_msg
            db.commit()
            flash(_('Comment by %s moderated successfully.') %
                  escape(comment.author))
            return redirect('admin/show_comments')

    for error in errors:
        flash(error, 'error')

    parsers = request.app.list_parsers()
    if missing_parser:
        parsers.insert(0, (missing_parser, _(u'Missing Parser “%s”') %
                           missing_parser))
        flash(_(u'This comment was submitted when the parser “%(parser)s” was '
                u'the comment parser. Because it is not available any longer '
                u'Zine doesn\'t allow modifcations on the text until you '
                u'reinstall/activate the plugin that provided that parser.') %
              {'parser': escape(missing_parser)}, 'error')

    return render_admin_response('admin/edit_comment.html',
                                 'comments.overview',
        comment=comment,
        form=form,
        parsers=parsers,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_comment(request, comment_id):
    """This dialog delets a comment.  Usually users are redirected here from the
    comment moderation page or the comment edit page.  If the comment was not
    deleted, the user is taken back to the page he's coming from or back to
    the edit page if the information is invalid.  The same happens if the post
    was deleted but if the referrer is the edit page. Then the user is taken
    back to the index so that he doesn't end up an a "page not found" error page.
    """
    comment = Comment.objects.get(comment_id)
    if comment is None:
        return redirect(url_for('admin/show_comments'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect('admin/edit_comment', comment_id=comment.comment_id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/edit_comment',
                                 comment_id=comment.comment_id)
            #! plugins can use this to react to comment deletes.  They can't
            #! stop the deleting of the comment but they can delete information
            #! in their own tables so that the database is consistent
            #! afterwards.
            emit_event('before-comment-deleted', comment)
            db.delete(comment)
            flash(_('Comment by %s deleted successfully.' %
                    escape(comment.author)), 'remove')
            db.commit()
            return redirect('admin/show_comments')

    return render_admin_response('admin/delete_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_approve_comment(request, comment_id):
    """Approve a comment"""
    comment = Comment.objects.get(comment_id)
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()
    if comment is None:
        raise NotFound()

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        if request.form.get('confirm'):
            csrf_protector.assert_safe()
            comment.status = COMMENT_MODERATED
            comment.blocked_msg = ''
            db.commit()
            flash(_('Comment by %s approved successfully.') %
                  escape(comment.author), 'configure')
        return redirect('admin/show_comments')

    return render_admin_response('admin/approve_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_block_comment(request, comment_id):
    """Block a comment."""
    comment = Comment.objects.get(comment_id)
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()
    if comment is None:
        raise NotFound()

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        if request.form.get('confirm'):
            msg = request.form.get('message')
            if not msg:
                msg = _('blocked by %s') % request.user.display_name
            csrf_protector.assert_safe()
            comment.status = COMMENT_BLOCKED_USER
            comment.blocked_msg = msg
            db.commit()
            flash(_('Comment by %s blocked successfully.') %
                  escape(comment.author), 'configure')
        return redirect('admin/show_comments')

    return render_admin_response('admin/block_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_show_tags(request, page):
    """Show a list of used post tag.  Tags can be used as web2.0 like tags or
    normal comments.
    """
    tags = Tag.objects.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/show_tags', page, PER_PAGE,
                                 Tag.objects.count())
    if not tags and page != 1:
        raise NotFound()
    return render_admin_response('admin/show_tags.html', 'posts.tags',
                                 tags=tags,
                                 pagination=pagination)


@require_role(ROLE_AUTHOR)
def do_edit_tag(request, tag_id=None):
    """Edit a tag."""
    errors = []
    form = dict.fromkeys(['slug', 'name', 'description'], u'')
    new_tag = True
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if tag_id is not None:
        tag = Tag.objects.get(tag_id)
        if tag is None:
            raise NotFound()
        form.update(
            slug=tag.slug,
            name=tag.name,
            description=tag.description
        )
        new_tag = False

    old_slug = form['slug']

    if request.method == 'POST':
        csrf_protector.assert_safe()

        # cancel
        if request.form.get('cancel'):
            return redirect('admin/show_tags')

        # delete
        if request.form.get('delete'):
            return simple_redirect('admin/delete_tag', tag_id=tag.tag_id)

        form['slug'] = slug = request.form.get('slug')
        form['name'] = name = request.form.get('name')
        form['description'] = description = request.form.get('description')

        if not name:
            errors.append(_('You have to give the tag a name.'))
        elif old_slug != slug and Tag.objects.filter_by(slug=slug).first() is not None:
            errors.append(_('The slug "%s" is not unique.') % slug)

        if not errors:
            if new_tag:
                tag = Tag(name, description, slug or None)
                msg = _('Tag %s created successfully.')
                msg_type = 'add'
            else:
                if tag.slug is not None:
                    tag.slug = slug
                tag.name = name
                tag.description = description
                msg = _('Tag %s updated successfully.')
                msg_type = 'info'

            db.commit()
            html_tag_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(tag)),
                escape(tag.name)
            )
            flash(msg % html_tag_detail, msg_type)
            return redirect('admin/show_tags')

    for error in errors:
        flash(error, 'error')

    return render_admin_response('admin/edit_tag.html', 'posts.tags',
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_tag(request, tag_id):
    """Works like the other delete pages, just that it deletes tags."""
    tag = Tag.objects.get(tag_id)
    if tag is None:
        return redirect(url_for('admin/show_tags'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect('admin/edit_tag', tag_id=tag.tag_id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/edit_tag', tag_id=tag.tag_id)
            #! plugins can use this to react to tag deletes.  They can't stop
            #! the deleting of the tag but they can delete information in
            #! their own tables so that the database is consistent afterwards.
            emit_event('before-tag-deleted', tag)
            db.delete(tag)
            flash(_('Tag %s deleted successfully.') % escape(tag.name))
            db.commit()
            return redirect('admin/show_tags')

    return render_admin_response('admin/delete_tag.html', 'posts.tags',
        tag=tag,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_show_users(request, page):
    """Show all users in a list."""
    users = User.objects.query.limit(PER_PAGE).offset(PER_PAGE * (page - 1)).all()
    pagination = AdminPagination('admin/show_users', page, PER_PAGE,
                                 User.objects.count())
    if not posts and page != 1:
        raise NotFound()
    return render_admin_response('admin/show_users.html', 'users.overview',
                                 users=users,
                                 pagination=pagination)


@require_role(ROLE_ADMIN)
def do_edit_user(request, user_id=None):
    """Edit a user.  This can also create a user.  If a new user is created
    the dialog is simplified, some unimportant details are left out.
    """
    user = None
    errors = []
    form = dict.fromkeys(['username', 'first_name', 'last_name',
                          'display_name', 'description', 'email', 'www'], u'')
    form['role'] = ROLE_AUTHOR
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if user_id is not None:
        user = User.objects.get(user_id)
        if user is None:
            raise NotFound()
        form.update(
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user._display_name,
            description=user.description,
            email=user.email,
            www=user.www,
            role=user.role
        )
    new_user = user is None

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('cancel'):
            return redirect('admin/show_users')
        elif request.form.get('delete') and user:
            return simple_redirect('admin/delete_user', user_id=user.user_id)

        username = form['username'] = request.form.get('username')
        if not username:
            errors.append(_('Username is required.'))
        elif new_user and User.objects.filter_by(username=username).first() \
             is not None:
            errors.append(_(u'Username “%s” is taken.') % username)
        password = form['password'] = request.form.get('password')
        if new_user and not password:
            errors.append(_('You have to provide a password.'))
        first_name = form['first_name'] = request.form.get('first_name')
        last_name = form['last_name'] = request.form.get('last_name')
        display_name = form['display_name'] = request.form.get('display_name')
        description = form['description'] = request.form.get('description')
        email = form['email'] = request.form.get('email', '')
        if not is_valid_email(email):
            errors.append(_('The user needs a valid mail address.'))
        www = form['www'] = request.form.get('www', '')
        try:
            role = form['role'] = int(request.form.get('role', ''))
            if role not in xrange(ROLE_ADMIN + 1):
                raise ValueError()
        except ValueError:
            errors.append(_('Invalid user role.'))

        if not errors:
            if new_user:
                user = User(username, password, email, first_name,
                            last_name, description, www, role)
                user.display_name = display_name or '$username'
                msg = _('User %s created successfully.')
                icon = 'add'
            else:
                user.username = username
                if password:
                    user.set_password(password)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.display_name = display_name or '$username'
                user.description = description
                user.www = www
                user.role = role
                msg = _('User %s edited successfully.')
                icon = 'info'
            db.commit()
            html_user_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(user)),
                escape(user.username)
            )
            flash(msg % html_user_detail, icon)
            if request.form.get('save'):
                return redirect('admin/show_users')
            return simple_redirect('admin/edit_user', user_id=user.user_id)

    if not new_user:
        display_names = [
            ('$nick', user.username),
        ]
        if user.first_name:
            display_names.append(('$first', user.first_name))
        if user.last_name:
            display_names.append(('$last', user.last_name))
        if user.first_name and user.last_name:
            display_names.extend([
                ('$first $last', u'%s %s' % (user.first_name, user.last_name)),
                ('$last $first', u'%s %s' % (user.last_name, user.first_name)),
                (u'$first “$nick” $last', u'%s “%s” %s' % (
                    user.first_name,
                    user.username,
                    user.last_name
                ))
            ])
    else:
        display_names = None

    for error in errors:
        flash(error, 'error')

    return render_admin_response('admin/edit_user.html', 'users.edit',
        new_user=user is None,
        user=user,
        form=form,
        display_names=display_names,
        roles=[
            (ROLE_ADMIN, _('Administrator')),
            (ROLE_EDITOR, _('Editor')),
            (ROLE_AUTHOR, _('Author')),
            (ROLE_SUBSCRIBER, _('Subscriber'))
        ],
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_delete_user(request, user_id):
    """Like all other delete screens just that it deletes a user."""
    user = User.objects.get(user_id)
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if user is None:
        return redirect('admin/show_users')
    elif user == request.user:
        flash(_('You cannot delete yourself.'), 'error')
        return redirect('admin/show_users')

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('cancel'):
            return redirect('admin/edit_user', user_id=user.user_id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/edit_user', user_id=user.user_id)
            action = request.form.get('action')
            action_val = None
            if action == 'reassign':
                action_val = request.form.get('reassign_user', type=int)
                db.execute(posts.update(posts.c.author_id == user_id), dict(
                    author_id=action_val
                ))
            #! plugins can use this to react to user deletes.  They can't stop
            #! the deleting of the user but they can delete information in
            #! their own tables so that the database is consistent afterwards.
            #! Additional to the user object an action and action val is
            #! provided.  The action can be one of the following values:
            #!  "reassign":     Reassign the objects to the user with the
            #!                  user_id of "action_val".
            #!  "delete":       Delete related objects.
            #! More actions might be added in the future so plugins should
            #! ignore unknown actions.  If an unknown action is provided
            #! the plugin should treat is as "delete".
            emit_event('before-user-deleted', user, action, action_val)
            db.delete(user)
            flash(_('User %s deleted successfully.') %
                  escape(user.username), 'remove')
            db.commit()
            return redirect('admin/show_users')

    return render_admin_response('admin/delete_user.html', 'users.edit',
        user=user,
        other_users=User.objects.filter(User.user_id != user_id).all(),
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_options(request):
    """So far just a redirect page, later it would be a good idea to have
    a page that shows all the links to configuration things in form of
    a simple table.
    """
    return simple_redirect('admin/basic_options')


@require_role(ROLE_ADMIN)
def do_basic_options(request):
    """The dialog for basic options such as the blog title etc."""
    # flash an altered message if the url is ?altered=true.  For more information
    # see the comment that redirects to the url below.
    if request.args.get('altered') == 'true':
        flash(_('Configuration altered successfully.'), 'configure')
        return simple_redirect('admin/basic_options')

    cfg = request.app.cfg
    form = {
        'blog_title':           cfg['blog_title'],
        'blog_tagline':         cfg['blog_tagline'],
        'blog_email':           cfg['blog_email'],
        'language':             cfg['language'],
        'timezone':             cfg['timezone'],
        'session_cookie_name':  cfg['session_cookie_name'],
        'comments_enabled':     cfg['comments_enabled'],
        'moderate_comments':    cfg['moderate_comments'],
        'pings_enabled':        cfg['pings_enabled'],
        'default_parser':       cfg['default_parser'],
        'comment_parser':       cfg['comment_parser'],
        'posts_per_page':       cfg['posts_per_page'],
        'use_flat_comments':    cfg['use_flat_comments']
    }
    errors = []
    csrf_protector = CSRFProtector()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        form['blog_title'] = blog_title = request.form.get('blog_title')
        if not blog_title:
            errors.append(_('You have to provide a blog title'))
        form['blog_tagline'] = blog_tagline = request.form.get('blog_tagline')
        form['blog_email'] = blog_email = request.form.get('blog_email', '')
        if blog_email and not is_valid_email(blog_email):
            errors.append(_('You have to provide a valid e-mail address '
                            'for the blog e-mail field.'))
        form['language'] = language = request.form.get('language')
        if not has_language(language):
            raise BadRequest()
        form['timezone'] = timezone = request.form.get('timezone')
        if not has_timezone(timezone):
            raise BadRequest()
        form['session_cookie_name'] = session_cookie_name = \
            request.form.get('session_cookie_name')
        form['comments_enabled'] = comments_enabled = \
            'comments_enabled' in request.form
        form['moderate_comments'] = moderate_comments = \
            request.form.get('moderate_comments', type=int)
        if moderate_comments not in (0, 1, 2):
            raise BadRequest()
        form['pings_enabled'] = pings_enabled = \
            'pings_enabled' in request.form
        form['default_parser'] = default_parser = \
            request.form.get('default_parser')
        if default_parser not in request.app.parsers:
            errors.append(_('Unknown parser %s.') % default_parser)
        form['comment_parser'] = comment_parser = \
            request.form.get('comment_parser')
        if comment_parser not in request.app.parsers:
            errors.append(_('Unknown parser %s.') % comment_parser)
        form['posts_per_page'] = request.form.get('posts_per_page', '')
        try:
            posts_per_page = int(form['posts_per_page'])
            if posts_per_page < 1:
                errors.append(_('Posts per page must be at least 1'))
        except ValueError:
            errors.append(_('Posts per page must be a valid integer'))
        form['use_flat_comments'] = use_flat_comments = \
            'use_flat_comments' in request.form
        if not errors:
            t = cfg.edit()
            if blog_title != cfg['blog_title']:
                t['blog_title'] = blog_title
            if blog_tagline != cfg['blog_tagline']:
                t['blog_tagline'] = blog_tagline
            if language != cfg['language']:
                t['language'] = language
            if timezone != cfg['timezone']:
                t['timezone'] = timezone
            if session_cookie_name != cfg['session_cookie_name']:
                t['session_cookie_name'] = session_cookie_name
            if comments_enabled != cfg['comments_enabled']:
                t['comments_enabled'] = comments_enabled
            if pings_enabled != cfg['pings_enabled']:
                t['pings_enabled'] = pings_enabled
            if moderate_comments != cfg['moderate_comments']:
                t['moderate_comments'] = moderate_comments
            if default_parser != cfg['default_parser']:
                t['default_parser'] = default_parser
            if comment_parser != cfg['comment_parser']:
                t['comment_parser'] = comment_parser
            if posts_per_page != cfg['posts_per_page']:
                t['posts_per_page'] = posts_per_page
            if use_flat_comments != cfg['use_flat_comments']:
                t['use_flat_comments'] = use_flat_comments

            if commit_config_change(t):
                # because the configuration page could change the language and
                # we want to flash the message "configuration changed" in the
                # new language rather than the old.  As a matter of fact we have
                # to wait for Zine to reload first which is why we do the
                # actual flashing after one reload.
                return simple_redirect('admin/basic_options', altered='true')

        for error in errors:
            flash(error, 'error')

    return render_admin_response('admin/basic_options.html', 'options.basic',
        form=form,
        timezones=list_timezones(),
        languages=list_languages(),
        parsers=request.app.list_parsers(),
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_ADMIN)
def do_urls(request):
    """A config page for URL depending settings."""
    form = {
        'blog_url_prefix':      request.app.cfg['blog_url_prefix'],
        'admin_url_prefix':     request.app.cfg['admin_url_prefix'],
        'tags_url_prefix':      request.app.cfg['tags_url_prefix'],
        'profiles_url_prefix':  request.app.cfg['profiles_url_prefix']
    }
    errors = []
    csrf_protector = CSRFProtector()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        for key in form:
            form[key] = value = request.form.get(key, '')
            if '<' in value or '>' in value:
                errors.append(_('URL prefix may not contain greater than or '
                                'smaller than signs.'))
            elif value and not value.startswith('/'):
                errors.append(_('URL prefixes have to start with a slash.'))
            elif value.endswith('/'):
                errors.append(_('URL prefixes may not end with a slash.'))

        if not errors:
            changed = False
            for key, value in form.iteritems():
                if value != request.app.cfg[key]:
                    if request.app.cfg.change_single(key, value):
                        changed = True
                    else:
                        flash(_('URL configuration could not be changed.'),
                              'error')
            if changed:
                flash(_('URL configuration changed.'), 'configure')

            # because the next request could reload the application and move
            # the admin interface we construct the URL to this page by hand.
            return redirect(form['admin_url_prefix'][1:] + '/options/urls')
        else:
            flash(errors[0], 'error')

    return render_admin_response('admin/url_options.html', 'options.urls',
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_ADMIN)
def do_theme(request):
    """Allow the user to select one of the themes that are available."""
    csrf_protector = CSRFProtector()
    if 'configure' in request.args:
        return simple_redirect('admin/configure_theme')
    new_theme = request.args.get('select')
    if new_theme in request.app.themes:
        csrf_protector.assert_safe()
        if request.app.cfg.change_single('theme', new_theme):
            flash(_('Theme changed successfully.'), 'configure')
        else:
            flash(_('Theme could not be changed.'), 'error')
        return simple_redirect('admin/theme')

    return render_admin_response('admin/theme.html', 'options.theme',
        themes=sorted(request.app.themes.values(),
                      key=lambda x: x.name == 'default' or x.display_name.lower()),
        current_theme=request.app.theme,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_configure_theme(request):
    if not request.app.theme.configurable:
        flash(_('This theme is not configurable'), 'error')
        return simple_redirect('admin/theme')
    return request.app.theme.configuration_page(request)


@require_role(ROLE_ADMIN)
def do_plugins(request):
    """Load and unload plugins and reload Zine if required."""
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('enable_guard'):
            if request.app.cfg.change_single('plugin_guard', True):
                flash(_('Plugin guard enabled successfully. Errors '
                        'occuring in plugins during setup are catched now.'))
            else:
                flash(_('Plugin guard could not be enabled.'), 'error')
        elif request.form.get('disable_guard'):
            if request.app.cfg.change_single('plugin_guard', False):
                flash(_('Plugin guard disabled successfully.'))
            else:
                flash(_('Plugin guard could not be disabled.'), 'error')

        for name, plugin in request.app.plugins.iteritems():
            active = 'plugin_' + name in request.form

            # XXX: correct pluralization in the dependency loading message
            # XXX: dependency tracking on plugin deactivating

            if active and not plugin.active:
                loaded, loaded_dep, missing_dep = plugin.activate()
                if loaded:
                    if loaded_dep:
                        flash(_(u'The Plugins %(dependencies)s are '
                                u'loaded as a dependency of “%(plugin)s”') % {
                                    'dependencies': u', '.join(loaded_dep),
                                    'plugin': plugin.html_display_name})
                    flash(_(u'Plugin “%s” activated.') % plugin.html_display_name,
                         'configure')

                else:
                    if missing_dep:
                        flash(_(u'Plugin “%(plugin)s” has unresolved '
                                u'dependencies.  Please install %(dependency)s.')
                                % {'plugin': plugin.html_display_name,
                                   'dependency': u', '.join(missing_dep)}, 'error')
                    else:
                        flash(_(u'Plugin “%s” could not be loaded')
                                % plugin.html_display_name)

            elif not active and plugin.active:
                plugin.deactivate()
                flash(_(u'Plugin “%s” deactivated.') %
                      plugin.html_display_name, 'configure')
            else:
                continue

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

        return simple_redirect('admin/plugins')

    return render_admin_response('admin/plugins.html', 'options.plugins',
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name),
        csrf_protector=csrf_protector,
        guard_enabled=request.app.cfg['plugin_guard']
    )


@require_role(ROLE_ADMIN)
def do_remove_plugin(request, plugin):
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
def do_cache(request):
    """Configure the cache."""
    csrf_protector = CSRFProtector()
    cfg = request.app.cfg
    form = {
        'cache_system':             cfg['cache_system'],
        'cache_timeout':            cfg['cache_timeout'],
        'enable_eager_caching':     cfg['enable_eager_caching'],
        'memcached_servers':        cfg['memcached_servers'],
        'filesystem_cache_path':    cfg['filesystem_cache_path']
    }
    errors = []

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if 'clear_cache' in request.form:
            request.app.cache.clear()
            flash(_('The cache was cleared successfully.'), 'configure')
            return redirect(url_for('admin/cache'))

        form['cache_system'] = cache_system = \
            request.form.get('cache_system')
        if cache_system not in cache.systems:
            errors.append(_('Invalid cache system selected.'))
        form['cache_timeout'] = cache_timeout = \
            request.form.get('cache_timeout', '')
        if not cache_timeout.isdigit():
            errors.append(_('Cache timeout must be positive integer.'))
        else:
            cache_timeout = int(cache_timeout)
            if cache_timeout < 10:
                errors.append(_('Cache timeout must be greater than 10 '
                                'seconds.'))
        form['enable_eager_caching'] = enable_eager_caching = \
            'enable_eager_caching' in request.form
        form['memcached_servers'] = memcached_servers = \
            request.form.get('memcached_servers', '')
        form['filesystem_cache_path'] = filesystem_cache_path = \
            request.form.get('filesystem_cache_path', '')

        if not errors:
            t = cfg.edit()
            if cache_system != cfg['cache_system']:
                t['cache_system'] = cache_system
            if cache_timeout != cfg['cache_timeout']:
                t['cache_timeout'] = cache_timeout
            if enable_eager_caching != cfg['enable_eager_caching']:
                t['enable_eager_caching'] = enable_eager_caching
            if memcached_servers != cfg['memcached_servers']:
                t['memcached_servers'] = memcached_servers
            if filesystem_cache_path != cfg['filesystem_cache_path']:
                t['filesystem_cache_path'] = filesystem_cache_path
            if commit_config_change(t):
                flash(_('Updated cache settings.'), 'configure')
        else:
            flash(errors[0], 'error')

    return render_admin_response('admin/cache.html', 'options.cache',
        hidden_form_data=make_hidden_fields(csrf_protector),
        form=form,
        cache_systems=[
            ('simple', _('Simple Cache')),
            ('memcached', _('memcached')),
            ('filesystem', _('Filesystem')),
            ('null', _('No Cache'))
        ]
    )


@require_role(ROLE_ADMIN)
def do_configuration(request):
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
            commit_config_change(t)
        return simple_redirect('admin/configuration')

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
def do_maintenance(request):
    """Enable / Disable maintenance mode."""
    cfg = request.app.cfg
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()
        cfg.change_single('maintenance_mode', not cfg['maintenance_mode'])
        if not cfg['maintenance_mode']:
            flash(_('Maintenance mode disabled.  The blog is now '
                    'publicly available.'), 'configure')
        return simple_redirect('admin/maintenance')

    return render_admin_response('admin/maintenance.html',
                                 'system.maintenance',
        hidden_form_data=make_hidden_fields(csrf_protector),
        maintenance_mode=cfg['maintenance_mode']
    )


@require_role(ROLE_ADMIN)
def do_import(request):
    """Show the current import queue or add new items."""
    return render_admin_response('admin/import.html', 'system.import',
        importers=sorted(request.app.importers.values(),
                         key=lambda x: x.title.lower()),
        queue=list_import_queue(request.app)
    )


@require_role(ROLE_ADMIN)
def do_inspect_import(request, id):
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
            return simple_redirect('admin/maintenance')
        elif 'delete' in request.form:
            return simple_redirect('admin/delete_import', id=id)
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
        users=User.objects.order_by('username').all(),
        hidden_form_data=make_hidden_fields(csrf_protector),
        dump_id=id
    )


@require_role(ROLE_ADMIN)
def do_delete_import(request, id):
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
def do_export(request):
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
def do_information(request):
    """Shows some details about this Zine installation.  It's useful for
    debugging and checking configurations.  If severe errors in a Zine
    installation occour it's a good idea to dump this page and attach it to
    a bug report mail.
    """
    from sys import version as python_version
    from threading import activeCount
    from jinja2.defaults import DEFAULT_NAMESPACE, DEFAULT_FILTERS
    from zine import environment, __version__ as zine_version

    thread_count = activeCount()

    return render_admin_response('admin/information.html', 'system.information',
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
        servicepoints=sorted(request.app._services.keys()),
        configuration=[{
            'key':          key,
            'default':      default,
            'value':        request.app.cfg[key]
        } for key, (_, default) in sorted(request.app.cfg.config_vars.iteritems())],
        hosting_env={
            'persistent':       not request.is_run_once,
            'multithreaded':    request.is_multithread,
            'thread_count':     thread_count,
            'multiprocess':     request.is_multiprocess,
            'wsgi_version':     '.'.join(map(str, request.environ['wsgi.version']))
        },
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name),
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
        database_uri=request.app.cfg['database_uri']
    )


@require_role(ROLE_AUTHOR)
def do_about_zine(request):
    """Just show the zine license and some other legal stuff."""
    return render_admin_response('admin/about_zine.html',
                                 'system.about')


@require_role(ROLE_AUTHOR)
def do_change_password(request):
    """Allow the current user to change his password."""
    errors = []
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('cancel'):
            return redirect('admin/index')
        old_password = request.form.get('old_password')
        if not old_password:
            errors.append(_('You have to enter your old password.'))
        if not request.user.check_password(old_password):
            errors.append(_('Your old password is wrong.'))
        new_password = request.form.get('new_password')
        if not new_password:
            errors.append(_('Your new password cannot be empty.'))
        check_password = request.form.get('check_password')
        if new_password != check_password:
            errors.append(_('The passwords do not match.'))
        if not errors:
            request.user.set_password(new_password)
            db.commit()
            flash(_('Password changed successfully.'), 'configure')
            return redirect('admin/index')

    # just flash the first error, that's enough for the user
    if errors:
        flash(errors[0], 'error')

    return render_admin_response('admin/change_password.html',
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_pages_config(request):
    """Show the configuration page for pages"""
    cfg = get_application().cfg
    csrf_protector = CSRFProtector()
    form = {
        'show_title': cfg['show_page_title'],
        'show_children': cfg['show_page_children'],
    }
    if request.method == 'POST':
        csrf_protector.assert_safe()
        rform = request.form
        form['show_title'] = show_title = 'show_title' in request.form
        form['show_children'] = show_children = 'show_children' in request.form

        # update the configuration
        t = cfg.edit()
        if show_title != cfg['show_page_title']:
            t['show_page_title'] = show_title
        if show_children != cfg['show_page_children']:
            t['show_page_children'] = show_children
        if commit_config_change(t):
            flash(u'Pages configuration updated successfull.')

    return render_admin_response(
        'admin/pages_config.html',
        'options.pages',
        form=form,
        csrf_protector=csrf_protector,
    )


@require_role(ROLE_ADMIN)
def do_show_pages(request):
    """Shows all saved pages"""
    return render_admin_response(
        'admin/show_pages.html',
        'pages.overview',
        pages=Page.objects.all()
    )


@require_role(ROLE_ADMIN)
def do_write_page(request, page_id=None):
    """Show the "write page" dialog.

    If `page_id` is given the form is updated with already saved data so that
    you can edit a page.
    """
    csrf_protector = CSRFProtector()
    form = {}
    errors = []

    if page_id is None:
        # new page
        new_page = True
        page = None
        form.update(
            key=u'', title=u'',
            raw_body=u'',
            navigation_pos=u'',
            parser=request.app.cfg['default_parser'],
        )
    else:
        # edit a page
        new_page = False
        page = Page.objects.get(page_id)
        if page is None:
            raise NotFound()
        old_key = page.key
        form.update(
            key=page.key,
            title=page.title,
            raw_body=page.raw_body,
            navigation_pos=page.navigation_pos,
            parser=page.extra['parser'],
            parent_id=page.parent_id or 0,
        )

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect(url_for('admin/show_pages'))
        if request.form.get('delete') and not new_page:
            return redirect(url_for('admin/delete_page', page_id=page_id))

        form['title'] = title = request.form.get('title')
        if not title:
            errors.append(_('You have to provide a title'))

        form['key'] = key = request.form.get('key') or None
        if key is None:
            key = gen_slug(title)
        key = key.lstrip('/')
        if not key:
            errors.append(_('You have to provide a key'))

        form['navigation_pos'] = navigation_pos = \
            request.form.get('navigation_pos') or None

        form['raw_body'] = raw_body = request.form.get('raw_body')
        if not raw_body:
            errors.append(_('You have to provide some content'))

        form['parser'] = parser = request.form.get('parser')
        if not parser:
            parser = request.app.cfg['default_parser']

        form['parent_id'] = parent_id = request.form.get('parent_id')

        if new_page or old_key != key:
            if Page.objects.filter_by(key=key).first() is not None:
                errors.append(_('This key is already in use'))

        try:
            parent_id = int(parent_id)
        except (ValueError, TypeError):
            parent_id = None
        if parent_id == 0:
            parent_id = None

        if not errors:
            if new_page:
                page = Page(key, title, raw_body, parser, navigation_pos,
                            parent_id)
            else:
                page.key = key
                page.title = title
                page.parser = parser
                page.raw_body = raw_body
                page.navigation_pos = navigation_pos
                page.parent_id = parent_id

            db.commit()
            html_detail = '<a href="%s">%s</a>' % (
                escape(url_for(page)),
                escape(title)
            )
            if new_page:
                flash('The page %s was created successfully.' % html_detail)
            else:
                flash('The page %s was updated successfully.' % html_detail)
            return redirect(url_for('admin/show_pages'))
        else:
            for error in errors:
                flash(error, 'error')

    all_pages = [(0, 'No Parent')] + [(p.page_id, p.title) for p in
                                      Page.objects.all()]

    return render_admin_response(
        'admin/write_page.html',
        'pages.write',
        parsers=request.app.list_parsers(),
        form=form,
        page=page,
        new_page=new_page,
        csrf_protector=csrf_protector,
        all_pages=all_pages
    )


@require_role(ROLE_ADMIN)
def do_delete_page(request, page_id):
    """Shows the confirm dialog if the user deletes a page"""
    page = Page.objects.get(page_id)
    if page is None:
        raise NotFound()
    csrf_protector = CSRFProtector()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect(url_for('admin/write_page', page_id=page.page_id))
        elif request.form.get('confirm'):
            db.delete(page)
            flash(_('The page %s was deleted successfully.') %
                  escape(page.title), 'remove')
            db.commit()
            return redirect(url_for('admin/show_pages'))

    return render_admin_response('admin/delete_page.html', 'page.write',
        page=page,
        csrf_protector=csrf_protector,
    )


@require_role(ROLE_AUTHOR)
def do_upload(req):
    csrf_protector = CSRFProtector()
    reporter = StreamReporter()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        f = req.files['file']
        if not touch_upload_folder():
            flash(_('Could not create upload target folder %s.') %
                  escape(get_upload_folder()), 'error')
            return redirect(url_for('admin/new_upload'))

        filename = req.form.get('filename') or f.filename

        if not f:
            flash(_('No file uploaded.'))
        elif pathsep in filename:
            flash(_('Invalid filename requested.'))
        elif file_exists(filename) and not req.form.get('overwrite'):
            flash(_('A file with the filename %s exists already.') % (
                u'<a href="%s">%s</a>' % (
                    escape(url_for('blog/get_uploaded_file',
                                   filename=filename)),
                    escape(filename)
                )))
        else:
            if upload_file(f, filename):
                flash(_('File %s uploaded successfully.') % (
                      u'<a href="%s">%s</a>' % (
                          escape(url_for('blog/get_uploaded_file',
                                         filename=filename)),
                          escape(filename))))
            else:
                flash(_(u'Could not write file %s.') % escape(filename), 'error')
        return redirect(url_for('admin/new_upload'))

    return render_admin_response('admin/file_uploads/upload.html',
                                 'file_uploads.upload',
        csrf_protector=csrf_protector,
        reporter=reporter
    )


@require_role(ROLE_AUTHOR)
def do_thumbnailer(req):
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
            extra = _('If you don\'t have ImageMagick installed system wide '
                      'but in a different folder, you can defined that in '
                      'the <a href="%(config)s">configuration</a>.')
        else:
            extra = _('There is no ImageMagick in the path defined '
                      'installed. (<a href="%(config)s">check the '
                      'configuration</a>)')
        flash((_('Cannot find <a href="%(im)s">ImageMagick</a>.') + ' ' +
               extra) % {
                   'im':        'http://www.imagemagick.org/',
                   'config':    url_for('admin/upload_config')
               }, 'error')

    elif req.method == 'POST':
        errors = []
        csrf_protector.assert_safe()
        form['src_image'] = src_image = req.form.get('src_image')
        if not src_image:
            errors.append(_('You have to specify a source image'))
        else:
            try:
                src = file(get_filename(src_image), 'rb')
            except IOError:
                errors.append(_('The image %s does not exist.') %
                              escape(src_image))
        form['thumb_width'] = thumb_width = req.form.get('thumb_width', '')
        form['thumb_height'] = thumb_height = req.form.get('thumb_height', '')
        if not thumb_width:
            errors.append(_('You have to define at least the width of the '
                            'thumbnail.'))
        elif not thumb_width.isdigit() or \
                (thumb_height and not thumb_height.isdigit()):
            errors.append(_('Thumbnail dimensions must be integers.'))
        form['keep_aspect_ratio'] = keep_aspect_ratio = \
                'keep_aspect_ratio' in req.form
        form['thumb_filename'] = thumb_filename = \
                req.form.get('thumb_filename')
        if not thumb_filename:
            errors.append(_('You have to specify a filename for the '
                            'thumbnail.'))
        elif pathsep in thumb_filename:
            errors.append(_('Invalid filename for thumbnail.'))
        elif file_exists(thumb_filename):
            errors.append(_('An file with this name exists already.'))
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
                flash(_('Thumbnail %s was created successfully.') % (
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
def do_browse_uploads(req):
    return render_admin_response('admin/file_uploads/browse.html',
                                 'file_uploads.browse',
        files=list_files()
    )


@require_role(ROLE_ADMIN)
def do_upload_config(req):
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
                flash(_('Upload folder changed successfully.'))
            else:
                flash(_('Upload folder could not be changed.'), 'error')
        im_path = form['im_path'] = req.form.get('im_path', '')
        if im_path != req.app.cfg['im_path']:
            if req.app.cfg.change_single('im_path', im_path):
                if im_path:
                    flash(_('Changed path to ImageMagick'))
                else:
                    flash(_('ImageMagick is searched on the system path now.'))
            else:
                flash(_('Path to ImageMagick could not be changed.'), 'error')
        mimetypes = form['mimetypes'] = req.form.get('mimetypes', '')
        mimetypes = ';'.join(mimetypes.splitlines())
        if mimetypes != req.app.cfg['upload_mimetypes']:
            if req.app.cfg.change_single('upload_mimetypes', mimetypes):
                flash(_('Upload mimetype mapping altered successfully.'))
            else:
                flash(_('Upload mimetype mapping could not be altered.'), 'error')
        return redirect(url_for('admin/upload_config'))

    return render_admin_response('admin/file_uploads/config.html',
                                 'options.uploads',
        im_version=get_im_version(),
        form=form,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_delete_upload(req, filename):
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
                flash(_('Could not delete file %s.') %
                      escape(filename), 'error')
            else:
                flash(_('File %s deleted successfully.') %
                      escape(filename), 'remove')
        return redirect('admin/browse_uploads')

    return render_admin_response('admin/file_uploads/delete.html',
                                 'file_uploads.browse',
        hidden_form_data=make_hidden_fields(csrf_protector, redirect),
        filename=filename
    )


@require_role(ROLE_AUTHOR)
def do_help(req, page=''):
    """Show help page."""
    from zine.docs import load_page, get_resource

    rv = load_page(req.app, page)
    if rv is None:
        resource = get_resource(req.app, page)
        if resource is None:
            raise NotFound()
        return resource

    parts, is_index = rv
    ends_with_slash = not page or page.endswith('/')
    if is_index and not ends_with_slash:
        return simple_redirect('admin/help', page=page + '/')
    elif not is_index and ends_with_slash:
        raise NotFound()

    return render_admin_response('admin/help.html', 'system.help', **parts)


def do_login(request):
    """Show a login page."""
    if request.user.is_somebody:
        return simple_redirect('admin/index')
    error = None
    username = ''
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password', '')
        if username:
            user = User.objects.filter_by(username=username).first()
            if user is None:
                error = _('User %s does not exist.') % escape(username)
            elif user.check_password(password):
                request.login(user, 'permanent' in request.form)
                return redirect('admin/index')
            else:
                error = _('Incorrect password.')
        else:
            error = _('You have to enter a username.')

    return render_response('admin/login.html', error=error,
                           username=username,
                           logged_out=request.values.get('logout') == 'yes',
                           hidden_redirect_field=redirect)


def do_logout(request):
    """Just logout and redirect to the login screen."""
    request.logout()
    return IntelligentRedirect()('admin/login', logout='yes')
