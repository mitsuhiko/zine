# -*- coding: utf-8 -*-
"""
    textpress.views.admin
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements the admin views. The admin interface is only
    available for admins, editors and authors but not for subscribers. For
    subscribers a simplified account management system exists at /account.

    The admin panel tries it's best to avoid CSRF attacks and some similar
    problems by using the hidden form fields from the utils package.  For
    more details see the docstrings of the `CSRFProtector` and
    `IntelligentRedirect` classes located there.  Do this before you try to
    add your own admin panel pages!

    Todo:

    -   Dashboard
    -   Sane Deletes (deleting a tag with associated pages makes problems,
                      same for users and similar stuff. This shouldn't happen)
    -   Permanent Login

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime
from textpress.api import *
from textpress.models import User, Post, Tag, Comment, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED
from textpress.utils import parse_datetime, format_datetime, \
     is_valid_email, is_valid_url, get_version_info, can_build_eventmap, \
     escape, build_eventmap, make_hidden_fields, reload_textpress, \
     dump_json, load_json, CSRFProtector, IntelligentRedirect, TIMEZONES
from textpress.widgets import WidgetManager
from textpress.pluginsystem import install_package, InstallationError


def simple_redirect(*args, **kwargs):
    """
    A function "simple redirect" that works like the redirect function in
    the views, just that it doesn't use the `IntelligentRedirect` which
    sometimes doesn't do what we want. (like redirecting to target pages
    and not using backredirects)
    """
    redirect(url_for(*args, **kwargs))


def flash(msg, type='info'):
    """
    Add a message to the message flash buffer.

    The default message type is "info", other possible values are
    "add", "remove", "error", "ok" and "configure". The message type affects
    the icon and visual appearance.
    """
    assert type in ('info', 'add', 'remove', 'error', 'ok', 'configure')
    if type == 'error':
        msg = (u'<strong>%s:</strong> ' % _('Error')) + msg
    get_request().session.setdefault('admin/flashed_messages', []).\
            append((type, msg))


def render_admin_response(template_name, _active_menu_item=None, **values):
    """
    Works pretty much like the normal `render_response` function but
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
    req = get_request()

    # set up the core navigation bar
    navigation_bar = [
        ('dashboard', url_for('admin/index'), _('Dashboard'), []),
        ('posts', url_for('admin/show_posts'), _('Posts'), [
            ('overview', url_for('admin/show_posts'), _('Overview')),
            ('write', url_for('admin/new_post'), _('Write Post'))
        ]),
        ('comments', url_for('admin/show_comments'), _('Comments'), [
            ('overview', url_for('admin/show_comments'), _('Overview'))
        ]),
        ('tags', url_for('admin/show_tags'), _('Tags'), [
            ('overview', url_for('admin/show_tags'), _('Overview')),
            ('edit', url_for('admin/new_tag'), _('Edit Tag'))
        ])
    ]

    # set up the administration menu bar
    if req.user.role == ROLE_ADMIN:
        navigation_bar += [
            ('users', url_for('admin/show_users'), _('Users'), [
                ('overview', url_for('admin/show_users'), _('Overview')),
                ('edit', url_for('admin/new_user'), _('Edit User'))
            ]),
            ('options', url_for('admin/options'), _('Options'), [
                ('basic', url_for('admin/basic_options'), _('Basic')),
                ('theme', url_for('admin/theme'), _('Theme')),
                ('widgets', url_for('admin/widgets'), _('Widgets')),
                ('plugins', url_for('admin/plugins'), _('Plugins')),
                ('configuration', url_for('admin/configuration'),
                 _('Configuration Editor'))
            ])
        ]

    # add the about items to the navigation bar
    about_items = [
        ('system', url_for('admin/about'), _('System')),
        ('textpress', url_for('admin/about_textpress'), _('TextPress'))
    ]
    if can_build_eventmap:
        about_items.insert(1, ('eventmap', url_for('admin/eventmap'),
                               _('Event Map')))
    navigation_bar.append(('about', url_for('admin/about'), _('About'),
                          about_items))

    #! allow plugins to extend the navigation bar
    emit_event('modify-admin-navigation-bar', req, navigation_bar,
               buffered=True)

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
    if req.app.cfg['maintenance_mode']:
        flash(_('TextPress is in maintenance mode. Don\'t forget to '
                'turn it off again once you finished your changes.'))

    # check for broken plugins if we have the plugin guard enabled
    if req.app.cfg['plugin_guard']:
        for plugin in req.app.plugins.itervalues():
            if plugin.active and plugin.setup_error is not None:
                plugin.deactivate()
                flash(_('The plugin guard detected that the plugin "%s" '
                        'causes problems (%s in %s, line %s) and deactivated '
                        'it. If you want to debug it, disable the plugin '
                        'guard and enable the debugger.') % (
                            plugin.html_display_name,
                            escape(str(plugin.setup_error[1]).
                                   decode('utf-8', 'ignore')),
                            plugin.setup_error[2].tb_frame.
                                f_globals.get('__file__', _('unknown file')),
                            plugin.setup_error[2].tb_lineno
                        ), 'error')

    #! used to flash messages, add links to stylesheets, modify the admin
    #! context etc.
    emit_event('before-admin-response-rendered', req, values, buffered=True)

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
        } for type, msg in req.session.pop('admin/flashed_messages', [])]
    }
    return render_response(template_name, **values)


@require_role(ROLE_AUTHOR)
def do_index(req):
    """
    Show the admin interface index page which is a wordpress inspired
    dashboard (doesn't exist right now).

    Once it's finished it should show the links to the most useful pages
    such as "new post", etc. and the recent blog activity (unmoderated
    comments etc.)
    """
    return render_admin_response('admin/index.html', 'dashboard',
                                 drafts=Post.objects.get_drafts())


@require_role(ROLE_AUTHOR)
def do_show_posts(req):
    """
    Show a list of posts for post moderation.  So far the output is not
    paginated which makes it hard to manage if you have more posts.
    """
    return render_admin_response('admin/show_posts.html', 'posts.overview',
                                 drafts=Post.objects.get_drafts(),
                                 posts=Post.objects.all())


@require_role(ROLE_AUTHOR)
def do_edit_post(req, post_id=None):
    """
    Edit or create a new post.  So far this dialog doesn't emit any events
    although it would be a good idea to allow plugins to add custom fields
    into the template.
    """
    tags = []
    errors = []
    form = {}
    post = exclude = None
    missing_parser = None
    keep_post_texts = False
    parsers = req.app.list_parsers()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()
    old_texts = None

    # edit existing post
    if post_id is not None:
        new_post = False
        post = Post.objects.get(post_id)
        exclude = post.post_id
        if post is None:
            abort(404)
        form.update(
            title=post.title,
            body=post.raw_body,
            intro=post.raw_intro,
            tags=[t.slug for t in post.tags],
            post_status=post.status,
            comments_enabled=post.comments_enabled,
            pings_enabled=post.pings_enabled,
            pub_date=format_datetime(post.pub_date),
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
            title='',
            body='',
            intro='',
            tags=[],
            post_status=STATUS_DRAFT,
            comments_enabled=req.app.cfg['comments_enabled'],
            pings_enabled=req.app.cfg['pings_enabled'],
            pub_date='now', # XXX: i18n
            slug='',
            author=req.user.username,
            parser=req.app.cfg['default_parser']
        )


    # handle incoming data and create/update the post
    if req.method == 'POST':
        csrf_protector.assert_safe()

        # handle cancel
        if req.form.get('cancel'):
            redirect('admin/show_posts')

        # handle delete, redirect to confirmation page
        if req.form.get('delete') and post_id is not None:
            simple_redirect('admin/delete_post', post_id=post_id)

        form['title'] = title = req.form.get('title')
        if not title:
            errors.append(_('You have to provide a title.'))
        form['body'] = body = req.form.get('body')
        if not body:
            errors.append(_('You have to provide a body.'))
        form['intro'] = intro = req.form.get('intro') or ''
        try:
            form['post_status'] = post_status = int(req.form['post_status'])
            if post_status < 0 or post_status > 2:
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            errors.append(_('Invalid post status'))
        form['comments_enabled'] = bool(req.form.get('comments_enabled'))
        form['pings_enabled'] = bool(req.form.get('pings_enabled'))
        form['parser'] = parser = req.form.get('parser')
        if missing_parser and parser == post.parser:
            if old_texts != (intro, body):
                errors.append(_('You cannot change the text of a post which '
                                'parser does not exist any longer.'))
            else:
                keep_post_texts = True
        elif parser not in req.app.parsers:
            errors.append(_('Unknown parser "%s".') % parser)
        try:
            pub_date = parse_datetime(req.form.get('pub_date') or 'now')
        except ValueError:
            errors.append(_('Invalid publication date.'))

        username = req.form.get('author')
        if not username:
            author = req.user
            username = author.username
        else:
            author = User.objects.get_by(username=username)
            if author is None:
                errors.append(_('Unknown author "%s".') % username)
        form['author'] = author
        form['slug'] = slug = req.form.get('slug') or None
        form['tags'] = []
        tags = []
        for tag in req.form.getlist('tags'):
            t = Tag.objects.get_by(slug=tag)
            if t is not None:
                tags.append(t)
                form['tags'].append(tag)
            else:
                errors.append(_('Unknown tag "%s".') % tag)

        # if someone adds a tag we don't save the post but just add
        # a tag to the list and assign it to the post list.
        add_tag = req.form.get('add_tag')
        if add_tag:
            # XXX: what happens if the slug is empty or the slug
            #      exists already?
            form['tags'].append(Tag(add_tag).slug)
            db.flush()
            del errors[:]

        # if there is no need tag and there are no errors we save the post
        elif not errors:
            if new_post:
                post = Post(title, author.user_id, body, intro, slug,
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
            db.flush()

            html_post_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(post)),
                escape(post.title)
            )
            if new_post:
                flash(_('The post %s was created successfully.') %
                      html_post_detail, 'add')
            else:
                flash(_('The post %s was updated successfully.') %
                      html_post_detail)

            if req.form.get('save'):
                redirect('admin/new_post')
            else:
                simple_redirect('admin/edit_post', post_id=post.post_id)

    for error in errors:
        flash(error, 'error')

    # tell the user if the parser is missing and we reinsert the
    # parser into the list.
    if missing_parser:
        parsers.insert(0, (missing_parser, _('Missing Parser "%s"') %
                           missing_parser))
        flash(_('This post was created with the parser "%(parser)s" that is '
                'not installed any longer.  Because of that TextPress '
                'doesn\'t allow modifcations on the text until you either '
                'change the parser or reinstall/activate the plugin that '
                'provided that parser.') % {'parser': escape(missing_parser)},
              'error')

    return render_admin_response('admin/edit_post.html', 'posts.write',
        new_post=new_post,
        form=form,
        tags=Tag.objects.all(),
        post=post,
        drafts=list(Post.objects.get_drafts(exclude=exclude)),
        post_status_choices=[
            (STATUS_PUBLISHED, _('Published')),
            (STATUS_DRAFT, _('Draft')),
            (STATUS_PRIVATE, _('Private'))
        ],
        parsers=parsers,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_post(req, post_id):
    """
    This dialog delets a post.  Usually users are redirected here from the
    edit post view or the post index page.  If the post was not deleted the
    user is taken back to the page he's coming from or back to the edit
    page if the information is invalid.  The same happens if the post was
    deleted but if the referrer is the edit page. Then the user is taken back to
    the index so that he doesn't end up an a "page not found" error page.
    """
    post = Post.objects.get(post_id)
    if post is None:
        abort(404)
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect('admin/edit_post', post_id=post.post_id)
        elif req.form.get('confirm'):
            redirect.add_invalid('admin/edit_post', post_id=post.post_id)
            db.delete(post)
            flash(_('The post %s was deleted successfully.') %
                  escape(post.title), 'remove')
            db.flush()
            redirect('admin/show_posts')

    return render_admin_response('admin/delete_post.html', 'posts.write',
        post=post,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_show_comments(req, post_id=None):
    """
    Show all the comments for one post or all comments. This could use
    some pagination.
    """
    post = None
    if post_id is None:
        comments = Comment.objects.all()
    else:
        post = Post.objects.get(post_id)
        if post is None:
            abort(404)
        comments = Comment.objects.all(Comment.post_id == post_id)
    return render_admin_response('admin/show_comments.html',
                                 'comments.overview',
        post=post,
        comments=comments
    )


@require_role(ROLE_AUTHOR)
def do_edit_comment(req, comment_id):
    """
    Edit a comment.  Unlike the post edit screen it's not possible to create
    new comments from here, that has to happen from the post page.
    """
    # XXX: maybe we should give administrators the possibility to change
    # the parser associated with comments.
    comment = Comment.objects.get(comment_id)
    if comment is None:
        abort(404)

    errors = []
    form = {
        'author':       comment.author,
        'email':        comment.email,
        'www':          comment.www,
        'body':         comment.raw_body,
        'parser':       comment.parser,
        'pub_date':     format_datetime(comment.pub_date),
        'blocked':      comment.blocked
    }
    old_text = comment.raw_body
    missing_parser = None
    keep_comment_text = False
    if comment.parser_missing:
        missing_parser = post.parser

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        # cancel
        if req.form.get('cancel'):
            redirect('admin/show_comments')

        # delete
        if req.form.get('delete'):
            simple_redirect('admin/delete_comment', comment_id=comment_id)

        form['author'] = author = req.form.get('author')
        if not author:
            errors.append(_('You have to give the comment an author.'))
        form['email'] = email = req.form.get('email')
        if not email or not is_valid_email(email):
            errors.append(_('You have to provide a valid mail address for '
                            'the author.'))
        form['www'] = www = req.form.get('www')
        form['body'] = body = req.form.get('body')
        form['parser'] = parser = req.form.get('parser')
        if missing_parser and parser == comment.parser:
            if old_text != body:
                errors.append(_('You cannot change the text of a comment '
                                'if the parser is missing.'))
            else:
                keep_comment_text = True
        elif parser not in req.app.parsers:
            errors.append(_('Unknown parser "%s".') % parser)
        if not body:
            errors.append(_('Need a text for this comment.'))
        if www and not is_valid_url(www):
            errors.append(_('You have to ommitt the url or provide a '
                            'valid one.'))
        form['pub_date'] = pub_date = req.form.get('pub_date')
        try:
            pub_date = parse_datetime(pub_date)
        except ValueError:
            errors.append(_('Invalid date for comment.'))
        form['blocked'] = blocked = bool(req.form.get('blocked'))

        if not errors:
            comment.author = author
            comment.email = email
            comment.www = www
            comment.pub_date = pub_date
            if not keep_comment_text:
                # always set parser before raw body because of callbacks.
                comment.parser = parser
                comment.raw_body = body
            comment.blocked = blocked
            if not blocked:
                comment.blocked_msg = ''
            elif not comment.blocked_msg:
                comment.blocked_msg = _('blocked by %s') % req.user.display_name
            db.save(comment)
            db.flush()
            flash(_('Comment by %s moderated successfully.') %
                  escape(comment.author))
            redirect('admin/show_comments')

    for error in errors:
        flash(error, 'error')

    parsers = req.app.list_parsers()
    if missing_parser:
        parsers.insert(0, (missing_parser, _('Missing Parser "%s"') %
                           missing_parser))
        flash(_('This comment was submitted when the parser "%(parser)s" was '
                'the comment parser. Because it is not available any longer '
                'TextPress doesn\'t allow modifcations on the text until you '
                'reinstall/activate the plugin that provided that parser.') %
              {'parser': escape(missing_parser)}, 'error')

    return render_admin_response('admin/edit_comment.html',
                                 'comments.overview',
        comment=comment,
        form=form,
        parsers=parsers,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_comment(req, comment_id):
    """
    This dialog delets a comment.  Usually users are redirected here from the
    comment moderation page or the comment edit page.  If the comment was not
    deleted, the user is taken back to the page he's coming from or back to
    the edit page if the information is invalid.  The same happens if the post
    was deleted but if the referrer is the edit page. Then the user is taken
    back to the index so that he doesn't end up an a "page not found" error page.
    """
    comment = Comment.objects.get(comment_id)
    if comment is None:
        redirect(url_for('admin/show_comments'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect('admin/edit_comment', comment_id=comment.comment_id)
        elif req.form.get('confirm'):
            redirect.add_invalid('admin/edit_comment',
                                 comment_id=comment.comment_id)
            db.delete(comment)
            flash(_('Comment by %s deleted successfully.' %
                    escape(comment.author)), 'remove')
            db.flush()
            redirect('admin/show_comments')

    return render_admin_response('admin/delete_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_unblock_comment(req, comment_id):
    """
    Unblock a comment which was blocked by an antispam plugin or a user.
    Redirect rules are identical to the delete page, just that the exception
    for deleted comments is left out.
    """
    comment = Comment.objects.get(comment_id)
    if comment is None:
        redirect(url_for('admin/show_comments'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('confirm'):
            comment.blocked = False
            comment.blocked_msg = ''
            db.flush()
            flash(_('Comment by %s unblocked successfully.') %
                  escape(comment.author), 'configure')
        redirect('admin/show_comments')

    return render_admin_response('admin/unblock_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_show_tags(req):
    """
    Show a list of used post tag.  Tags can be used as web2.0 like tags or
    normal comments.
    """
    return render_admin_response('admin/show_tags.html', 'tags.overview',
                                 tags=Tag.objects.all())


@require_role(ROLE_AUTHOR)
def do_edit_tag(req, tag_id=None):
    """Edit a tag."""
    errors = []
    form = dict.fromkeys(['slug', 'name', 'description'], u'')
    new_tag = True
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if tag_id is not None:
        tag = Tag.objects.get(tag_id)
        if tag is None:
            abort(404)
        form.update(
            slug=tag.slug,
            name=tag.name,
            description=tag.description
        )
        new_tag = False

    old_slug = form['slug']

    if req.method == 'POST':
        csrf_protector.assert_safe()

        # cancel
        if req.form.get('cancel'):
            redirect('admin/show_tags')

        # delete
        if req.form.get('delete'):
            simple_redirect('admin/delete_tag', tag_id=tag.tag_id)

        form['slug'] = slug = req.form.get('slug')
        form['name'] = name = req.form.get('name')
        form['description'] = description = req.form.get('description')

        if not name:
            errors.append(_('You have to give the tag a name.'))
        elif old_slug != slug and Tag.objects.get_by(slug=slug) is not None:
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

            db.flush()
            html_tag_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(tag)),
                escape(tag.name)
            )
            flash(msg % html_tag_detail, msg_type)
            redirect('admin/show_tags')

    for error in errors:
        flash(error, 'error')

    return render_admin_response('admin/edit_tag.html', 'tags.edit',
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_tag(req, tag_id):
    """
    Works like the other delete pages, just that it deletes tags.
    """
    tag = Tag.objects.get(tag_id)
    if tag is None:
        redirect(url_for('admin/show_tags'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect('admin/edit_tag', tag_id=tag.tag_id)
        elif req.form.get('confirm'):
            redirect.add_invalid('admin/edit_tag', tag_id=tag.tag_id)
            db.delete(tag)
            flash(_('Tag %s deleted successfully.') % escape(tag.name))
            db.flush()
            redirect('admin/show_tags')

    return render_admin_response('admin/delete_tag.html', 'tags.edit',
        tag=tag,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_show_users(req):
    """
    Show all users in a list except of the nobody user that is used for
    anonymous visitor requests.
    """
    return render_admin_response('admin/show_users.html', 'users.overview',
        users=User.objects.get_all_but_nobody()
    )


@require_role(ROLE_ADMIN)
def do_edit_user(req, user_id=None):
    """
    Edit a user.  This can also create a user.  If a new user is created the
    dialog is simplified, some unimportant details are left out.
    """
    user = None
    errors = []
    form = dict.fromkeys(['username', 'first_name', 'last_name',
                          'display_name', 'description', 'email'], u'')
    form['role'] = ROLE_AUTHOR
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if user_id is not None:
        user = User.objects.get(user_id)
        if user is None:
            abort(404)
        form.update(
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user._display_name,
            description=user.description,
            email=user.email,
            role=user.role
        )
    new_user = user is None

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('cancel'):
            redirect('admin/show_users')
        elif req.form.get('delete') and user:
            simple_redirect('admin/delete_user', user_id=user.user_id)

        username = form['username'] = req.form.get('username')
        if not username:
            errors.append(_('Username is required.'))
        elif new_user and User.objects.get_by(username=username) is not None:
            errors.append(_('Username "%s" is taken.') % username)
        password = form['password'] = req.form.get('password')
        if new_user and not password:
            errors.append(_('You have to provide a password.'))
        first_name = form['first_name'] = req.form.get('first_name')
        last_name = form['last_name'] = req.form.get('last_name')
        display_name = form['display_name'] = req.form.get('display_name')
        description = form['description'] = req.form.get('description')
        email = form['email'] = req.form.get('email', '')
        if not is_valid_email(email):
            errors.append(_('The user needs a valid mail address.'))
        try:
            role = form['role'] = int(req.form.get('role', ''))
            if role not in xrange(ROLE_ADMIN + 1):
                raise ValueError()
        except ValueError:
            errors.append(_('Invalid user role.'))

        if not errors:
            if new_user:
                user = User(username, password, email, first_name,
                            last_name, description, role)
                user.display_name = display_name or '$username'
                msg = 'User %s created successfully.'
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
                user.role = role
                msg = 'User %s edited successfully.'
                icon = 'info'
            db.flush()
            html_user_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(user)),
                escape(user.username)
            )
            flash(msg % html_user_detail, icon)
            if req.form.get('save'):
                redirect('admin/show_users')
            else:
                simple_redirect('admin/edit_user', user_id=user.user_id)

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
                ('$first "$nick" $last', u'%s "%s" %s' % (
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
def do_delete_user(req, user_id):
    """
    Like all other delete screens just that it deletes a user.
    """
    user = User.objects.get(user_id)
    if user is None:
        redirect(url_for('admin/show_users'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('cancel'):
            redirect('admin/edit_user', user_id=user.user_id)
        elif req.form.get('confirm'):
            redirect.add_invalid('admin/edit_user', user_id=user.user_id)
            db.delete(user)
            flash(_('User %s deleted successfully.') %
                  escape(user.username), 'remove')
            db.flush()
            redirect('admin/show_users')

    return render_admin_response('admin/delete_user.html', 'users.edit',
        user=user,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_options(req):
    """
    So far just a redirect page, later it would be a good idea to have
    a page that shows all the links to configuration things in form of
    a simple table.
    """
    simple_redirect('admin/basic_options')


@require_role(ROLE_ADMIN)
def do_basic_options(req):
    """
    The dialog for basic options such as the blog title etc.
    """
    cfg = req.app.cfg
    form = {
        'blog_title':           cfg['blog_title'],
        'blog_tagline':         cfg['blog_tagline'],
        'blog_email':           cfg['blog_email'],
        'timezone':             cfg['timezone'],
        'datetime_format':      cfg['datetime_format'],
        'date_format':          cfg['date_format'],
        'sid_cookie_name':      cfg['sid_cookie_name'],
        'comments_enabled':     cfg['comments_enabled'],
        'pings_enabled':        cfg['pings_enabled'],
        'default_parser':       cfg['default_parser'],
        'comment_parser':       cfg['comment_parser'],
        'posts_per_page':       cfg['posts_per_page'],
        'use_flat_comments':    cfg['use_flat_comments'],
        'maintenance_mode':     cfg['maintenance_mode']
    }
    errors = []
    csrf_protector = CSRFProtector()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        form['blog_title'] = blog_title = req.form.get('blog_title')
        if not blog_title:
            errors.append(_('You have to provide a blog title'))
        form['blog_tagline'] = blog_tagline = req.form.get('blog_tagline')
        form['blog_email'] = blog_email = req.form.get('blog_email', '')
        if blog_email and not is_valid_email(blog_email):
            errors.append(_('You have to provide a valid e-mail address '
                            'for the blog e-mail field.'))
        form['timezone'] = timezone = req.form.get('timezone')
        if timezone not in TIMEZONES:
            errors.append(_('Unknown timezone "%s"') % timezone)
        form['datetime_format'] = datetime_format = \
            req.form.get('datetime_format')
        form['date_format'] = date_format = \
            req.form.get('date_format')
        form['sid_cookie_name'] = sid_cookie_name = \
            req.form.get('sid_cookie_name')
        form['comments_enabled'] = comments_enabled = \
            req.form.get('comments_enabled') == 'yes'
        form['pings_enabled'] = pings_enabled = \
            req.form.get('pings_enabled') == 'yes'
        form['default_parser'] = default_parser = \
            req.form.get('default_parser')
        if default_parser not in req.app.parsers:
            errors.append(_('Unknown parser %s.') % default_parser)
        form['comment_parser'] = comment_parser = \
            req.form.get('comment_parser')
        if comment_parser not in req.app.parsers:
            errors.append(_('Unknown parser %s.') % comment_parser)
        form['posts_per_page'] = req.form.get('posts_per_page', '')
        try:
            posts_per_page = int(form['posts_per_page'])
            if posts_per_page < 1:
                errors.append(_('Posts per page must be at least 1'))
        except ValueError:
            errors.append(_('Posts per page must be a valid integer'))
        form['use_flat_comments'] = use_flat_comments = \
            req.form.get('use_flat_comments') == 'yes'
        form['maintenance_mode'] = maintenance_mode = \
            req.form.get('maintenance_mode') == 'yes'
        if not errors:
            if blog_title != cfg['blog_title']:
                cfg['blog_title'] = blog_title
            if blog_tagline != cfg['blog_tagline']:
                cfg['blog_tagline'] = blog_tagline
            if timezone != cfg['timezone']:
                cfg['timezone'] = timezone
            if datetime_format != cfg['datetime_format']:
                cfg['datetime_format'] = datetime_format
            if date_format != cfg['date_format']:
                cfg['date_format'] = date_format
            if sid_cookie_name != cfg['sid_cookie_name']:
                cfg['sid_cookie_name'] = sid_cookie_name
            if comments_enabled != cfg['comments_enabled']:
                cfg['comments_enabled'] = comments_enabled
            if pings_enabled != cfg['pings_enabled']:
                cfg['pings_enabled'] = pings_enabled
            if default_parser != cfg['default_parser']:
                cfg['default_parser'] = default_parser
            if comment_parser != cfg['comment_parser']:
                cfg['comment_parser'] = comment_parser
            if posts_per_page != cfg['posts_per_page']:
                cfg['posts_per_page'] = posts_per_page
            if use_flat_comments != cfg['use_flat_comments']:
                cfg['use_flat_comments'] = use_flat_comments
            if maintenance_mode != cfg['maintenance_mode']:
                cfg['maintenance_mode'] = maintenance_mode
            flash(_('Configuration altered successfully.'), 'configure')
            simple_redirect('admin/basic_options')

        for error in errors:
            flash(error, 'error')

    return render_admin_response('admin/basic_options.html', 'options.basic',
        form=form,
        timezones=sorted(TIMEZONES),
        parsers=req.app.list_parsers(),
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_ADMIN)
def do_theme(req):
    """
    Allow the user to select one of the themes that are available.
    """
    csrf_protector = CSRFProtector()
    new_theme = req.args.get('select')
    if new_theme in req.app.themes:
        csrf_protector.assert_safe()
        req.app.cfg['theme'] = new_theme
        flash(_('Theme changed successfully.'), 'configure')
        simple_redirect('admin/theme')

    current = req.app.cfg['theme']
    return render_admin_response('admin/theme.html', 'options.theme',
        themes=[{
            'uid':          theme.name,
            'name':         theme.detail_name,
            'author':       theme.metadata.get('author'),
            'description':  theme.metadata.get('description'),
            'has_preview':  theme.has_preview,
            'preview_url':  theme.preview_url,
            'current':      name == current
        } for name, theme in sorted(req.app.themes.items())],
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_overlays(req, template=None):
    """
    Edit the theme overlays.
    """
    if not template:
        redirect(url_for('admin/overlays', template='layout.html'))
    elif req.form.get('edit'):
        redirect(url_for('admin/overlays',
                         template=req.form.get('template', '')))
    has_overlay=req.app.theme.overlay_exists(template)
    source = req.app.theme.get_source(template)
    if source is None:
        abort(404)
    elif source.endswith('\n'):
        source = source[:-1]

    if req.method == 'POST':
        if req.form.get('delete'):
            req.app.theme.remove_overlay(template)
            flash(_('Overlay %s removed.') % escape(template),
                  'remove')
        else:
            req.app.theme.set_overlay(template,
                                      req.form.get('source', ''))
            if has_overlay:
                flash(_('Updated overlay %s.') % escape(template))
            else:
                flash(_('Created overlay %s.') % escape(template),
                      'add')
        redirect(url_for('admin/overlays', template=template))

    templates = [x for x in req.app.theme.list_templates()
                 if not x.startswith('admin/')]
    return render_admin_response('admin/overlays.html', 'options.theme',
        templates=templates,
        active_template=template,
        source=source,
        has_overlay=has_overlay
    )


@require_role(ROLE_ADMIN)
def do_widgets(req):
    """
    Configure the widgets.
    """
    # configure one widget
    configure = req.args.get('configure')
    if configure in req.app.widgets:
        widget = req.app.widgets[configure]
        if widget.CONFIGURABLE:
            args = widget.list_arguments(True)
            old_args = req.value.get('old_args')
            if old_args:
                try:
                    args.update(load_json(old_args))
                except:
                    pass
            body = None
            rv = widget.configure_widget(args, req)
            if rv is None:
                finished = True
            elif isinstance(rv, basestring):
                finished = False
                body = rv
            elif isinstance(rv, dict):
                finished = True
                args = rv
            return Response(dump_json({
                'finished': finished,
                'body':     body,
                'args':     args
            }), mimetype='text/javascript')

    # or save all changes
    if req.method == 'POST':
        try:
            widgets = load_json(req.value.get('widgets', ''))
            if not isinstance(widgets, list):
                raise TypeError()
        except:
            flash(_('invalid data submitted.'), 'error')
        else:
            manager.widgets[:] = widgets
            manager.save()
            flash(_('Widgets updated successfully.'))
        redirect(url_for('admin/widgets'))

    # display all widgets in the admin panel
    all_widgets = dict((i, (w.get_display_name(), w.list_arguments()))
                       for i, w in req.app.widgets.iteritems())
    manager = WidgetManager(req.app, '_widgets.html')
    if manager.manageable:
        pass

    add_script(url_for('core/shared', filename='js/JSON.js'))
    return render_admin_response('admin/widgets.html', 'options.widgets',
        widgets=sorted(all_widgets, key=lambda x: x[1]),
        manageable=manager.manageable,
        all_widgets=all_widgets,
        active_widgets=manager.widgets
    )


@require_role(ROLE_ADMIN)
def do_plugins(req):
    """
    Load and unload plugins and reload TextPress if required.
    """
    csrf_protector = CSRFProtector()
    want_reload = False
    if req.method == 'POST':
        csrf_protector.assert_safe()

        if req.form.get('trigger_reload'):
            flash(_('Plugins reloaded successfully.'))
            want_reload = True
        else:
            want_reload = False

        if req.form.get('enable_guard'):
            req.app.cfg['plugin_guard'] = True
            flash(_('Plugin guard enabled successfully. Errors '
                    'occuring in plugins during setup are catched now.'))
        elif req.form.get('disable_guard'):
            req.app.cfg['plugin_guard'] = False
            flash(_('Plugin guard disabled successfully.'))

        for name, plugin in req.app.plugins.iteritems():
            active = req.form.get('plugin_' + name) == 'yes'
            if active and not plugin.active:
                plugin.activate()
                want_reload = True
                flash(_('Plugin "%s" activated.') % plugin.html_display_name,
                      'configure')
            elif not active and plugin.active:
                plugin.deactivate()
                want_reload = True
                flash(_('Plugin "%s" deactivated.') %
                      plugin.html_display_name, 'configure')
            else:
                continue

        new_plugin = req.files.get('new_plugin')
        if new_plugin:
            try:
                plugin = install_package(req.app, new_plugin)
            except InstallationError, e:
                if e.code == 'invalid':
                    flash(_('Could not install the plugin because the '
                            'file uploaded is not a valid plugin file.'),
                          'error')
                elif e.code == 'version':
                    flash(_('The plugin uploaded has a newer package '
                            'version than this TextPress installation '
                            'can handle.'), 'error')
                elif e.code == 'exists':
                    flash(_('A plugin with the same UID is already '
                            'installed. Aborted.'), 'error')
                elif e.code == 'ioerror':
                    flash(_('Could not install the package because the '
                            'installer wasn\'t able to write the package '
                            'information. Wrong permissions?'), 'error')
                else:
                    flash(_('An unknown error occoured'), 'error')
            else:
                flash(_('Plugin "%s" added succesfully. You can now '
                        'enable it in the plugin list.') %
                      plugin.html_display_name, 'add')

        if want_reload:
            reload_textpress()
        simple_redirect('admin/plugins')

    return render_admin_response('admin/plugins.html', 'options.plugins',
        plugins=sorted(req.app.plugins.values(), key=lambda x: x.name),
        csrf_protector=csrf_protector,
        show_reload_button=not req.environ.get('wsgi.run_once'),
        guard_enabled=req.app.cfg['plugin_guard']
    )


@require_role(ROLE_ADMIN)
def do_remove_plugin(req, plugin):
    """
    Remove an inactive, instance installed plugin completely.
    """
    plugin = req.app.plugins.get(plugin)
    if plugin is None or \
       plugin.builtin_plugin or \
       plugin.active:
        abort(404)
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('confirm'):
            try:
                plugin.remove()
            except IOError:
                flash(_('Could not remove the plugin %s because an '
                        'IO error occoured. Wrong permissions?') %
                      plugin.html_display_name)
            flash(_('The plugin "%s" was removed from the instance '
                    'successfully.') % escape(plugin.display_name), 'remove')
        redirect('admin/plugins')

    return render_admin_response('admin/remove_plugin.html', 'options.plugins',
        plugin=plugin,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_configuration(req):
    """
    Advanced configuration editor.  This is useful for development or if a
    plugin doesn't ship an editor for the configuration values.  Because all
    the values are not further checked it could easily be that TextPress is
    left in an unusable state if a variable is set to something bad.  Because
    of this the editor shows a warning and must be enabled by hand.
    """
    csrf_protector = CSRFProtector()
    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('enable_editor'):
            req.session['configuration_editor_enabled'] = True
        elif req.form.get('disable_editor'):
            req.session['configuration_editor_enabled'] = False
        else:
            already_default = set()
            for key, value in req.form.iteritems():
                if key.endswith('__DEFAULT'):
                    key = key[:-9]
                    req.app.cfg.revert_to_default(key)
                    already_default.add(key)
                elif key in req.app.cfg and key not in already_default:
                    req.app.cfg.set_from_string(key, value)
        simple_redirect('admin/configuration')

    return render_admin_response('admin/configuration.html',
                                 'options.configuration',
        categories=req.app.cfg.get_detail_list(),
        editor_enabled=req.session.get('configuration_editor_enabled', False),
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_about(req):
    """
    Shows some details about this TextPress installation.  It's useful for
    debugging and checking configurations.  If severe errors in a TextPress
    installation occour it's a good idea to dump this page and attach it to
    a bug report mail.
    """
    from threading import activeCount
    from jinja.defaults import DEFAULT_NAMESPACE, DEFAULT_FILTERS

    thread_count = activeCount()
    version_info = get_version_info()
    multithreaded = thread_count > 1 and req.environ['wsgi.multithread']

    return render_admin_response('admin/about.html', 'about.system',
        apis=[{
            'name':         name,
            'blog_id':      blog_id,
            'preferred':    preferred,
            'endpoint':     endpoint
        } for name, (blog_id, preferred, endpoint) in req.app.apis.iteritems()],
        endpoints=[{
            'name':         rule.endpoint,
            'rule':         unicode(rule)
        } for rule in sorted(req.app.url_map._rules, key=lambda x: x.endpoint)],
        servicepoints=sorted(req.app._services.keys()),
        configuration=[{
            'key':          key,
            'default':      default,
            'value':        req.app.cfg[key]
        } for key, (_, default) in req.app.cfg.config_vars.iteritems()],
        hosting_env={
            'persistent':       not req.environ['wsgi.run_once'],
            'multithreaded':    multithreaded,
            'thread_count':     thread_count,
            'multiprocess':     req.environ['wsgi.multiprocess'],
            'wsgi_version':     '.'.join(map(str, req.environ['wsgi.version']))
        },
        plugins=sorted(req.app.plugins.values(), key=lambda x: x.name),
        textpress_version='.'.join(map(str, version_info[0:3])),
        textpress_tag=version_info[3],
        textpress_hg_node=version_info[4],
        textpress_hg_checkout=version_info[4] is not None,
        template_globals=[name for name, obj in
                          sorted(req.app.template_env.globals.items())
                          if name not in DEFAULT_NAMESPACE],
        template_filters=[name for name, obj in
                          sorted(req.app.template_env.filters.items())
                          if name not in DEFAULT_FILTERS],
        can_build_eventmap=can_build_eventmap,
        instance_path=req.app.instance_folder,
        database_uri=str(req.app.database_engine.url)
    )


@require_role(ROLE_AUTHOR)
def do_eventmap(req):
    """
    The GUI version of the `textpress-management.py eventmap` command.
    Traverses the sourcecode for emit_event calls using the python2.5
    ast compiler.  Because of that it raises an page not found exception
    for python2.4.
    """
    if not can_build_eventmap:
        abort(404)
    return render_admin_response('admin/eventmap.html', 'about.eventmap',
        get_map=lambda: sorted(build_eventmap(req.app).items()),
        # walking the tree can take some time, so better use stream
        # processing for this template. that's also the reason why
        # the building process is triggered from inside the template.
        # stream rendering however is buggy in wsgiref :-/
        _stream=True
    )


@require_role(ROLE_AUTHOR)
def do_about_textpress(req):
    """
    Just show the textpress license and some other legal stuff.
    """
    return render_admin_response('admin/about_textpress.html',
                                 'about.textpress')


@require_role(ROLE_AUTHOR)
def do_change_password(req):
    """
    Allow the current user to change his password.
    """
    errors = []
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('cancel'):
            redirect('admin/index')
        old_password = req.form.get('old_password')
        if not old_password:
            errors.append(_('You have to enter your old password.'))
        if not req.user.check_password(old_password):
            errors.append(_('Your old password is wrong.'))
        new_password = req.form.get('new_password')
        if not new_password:
            errors.append(_('Your new password cannot be empty.'))
        check_password = req.form.get('check_password')
        if new_password != check_password:
            errors.append(_('The passwords do not match.'))
        if not errors:
            req.user.set_password(new_password)
            db.save(req.user)
            db.flush()
            flash(_('Password changed successfully.'), 'configure')
            redirect('admin/index')

    # just flash the first error, that's enough for the user
    if errors:
        flash(errors[0], 'error')

    return render_admin_response('admin/change_password.html',
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


def do_login(req):
    """Show a login page."""
    if req.user.is_somebody:
        simple_redirect('admin/index')
    error = None
    username = ''
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        username = req.form.get('username')
        password = req.form.get('password', '')
        if username:
            user = User.objects.get_by(username=username)
            if user is None:
                error = _('User %s does not exist.') % escape(username)
            elif user.check_password(password):
                req.login(user)
                redirect('admin/index')
            else:
                error = _('Incorrect password.')
        else:
            error = _('You have to enter a username.')

    return render_response('admin/login.html', error=error,
                           username=username,
                           logged_out=req.values.get('logout') == 'yes',
                           hidden_redirect_field=redirect)


def do_logout(req):
    """Just logout and redirect to the login screen."""
    req.logout()
    IntelligentRedirect()('admin/login', logout='yes')
