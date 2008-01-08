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

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime
from textpress.api import *
from textpress.models import User, Post, Tag, Comment, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED
from textpress.database import comments, posts, post_tags, post_links
from textpress.utils import parse_datetime, format_datetime, \
     is_valid_email, is_valid_url, get_version_info, can_build_eventmap, \
     build_eventmap, make_hidden_fields, dump_json, load_json, \
     CSRFProtector, IntelligentRedirect, TIMEZONES
from textpress.widgets import WidgetManager
from textpress.pluginsystem import install_package, InstallationError
from textpress.pingback import pingback, PingbackError
from urlparse import urlparse
from werkzeug import escape
from werkzeug.exceptions import NotFound


def simple_redirect(*args, **kwargs):
    """
    A function "simple redirect" that works like the redirect function in
    the views, just that it doesn't use the `IntelligentRedirect` which
    sometimes doesn't do what we want. (like redirecting to target pages
    and not using backredirects)
    """
    return redirect(url_for(*args, **kwargs))


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
    request = get_request()

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
    if request.user.role == ROLE_ADMIN:
        navigation_bar += [
            ('users', url_for('admin/show_users'), _('Users'), [
                ('overview', url_for('admin/show_users'), _('Overview')),
                ('edit', url_for('admin/new_user'), _('Edit User'))
            ]),
            ('options', url_for('admin/options'), _('Options'), [
                ('basic', url_for('admin/basic_options'), _('Basic')),
                ('urls', url_for('admin/urls'), _('URLs')),
                ('theme', url_for('admin/theme'), _('Theme')),
                ('widgets', url_for('admin/widgets'), _('Widgets')),
                ('plugins', url_for('admin/plugins'), _('Plugins')),
                ('cache', url_for('admin/cache'), _('Cache')),
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
        flash(_('TextPress is in maintenance mode. Don\'t forget to '
                'turn it off again once you finish your changes.'))

    # check for broken plugins if we have the plugin guard enabled
    if request.app.cfg['plugin_guard']:
        for plugin in request.app.plugins.itervalues():
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
def do_show_posts(request):
    """
    Show a list of posts for post moderation.  So far the output is not
    paginated which makes it hard to manage if you have more posts.
    """
    return render_admin_response('admin/show_posts.html', 'posts.overview',
                                 drafts=Post.objects.get_drafts(),
                                 posts=Post.objects.all())


@require_role(ROLE_AUTHOR)
def do_edit_post(request, post_id=None):
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
            comments_enabled=request.app.cfg['comments_enabled'],
            pings_enabled=request.app.cfg['pings_enabled'],
            pub_date='now', # XXX: i18n
            slug='',
            author=request.user.username,
            parser=request.app.cfg['default_parser']
        )

    # tick the "ping urls from text" checkbox if either we have a
    # new post or we edit an old post and the parser is available
    form['ping_from_text'] = not post or not post.parser_missing

    # handle incoming data and create/update the post
    if request.method == 'POST':
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
            pub_date = parse_datetime(request.form.get('pub_date') or 'now')
        except ValueError:
            errors.append(_('Invalid publication date.'))

        username = request.form.get('author')
        if not username:
            author = request.user
            username = author.username
        else:
            author = User.objects.filter_by(username=username).first()
            if author is None:
                errors.append(_('Unknown author "%s".') % username)
        form['author'] = author
        form['slug'] = slug = request.form.get('slug') or None
        if slug and '/' in slug:
            errors.append(_('A slug cannot contain a slash.'))
        form['tags'] = []
        tags = []
        for tag in request.form.getlist('tags'):
            t = Tag.objects.filter_by(slug=tag).first()
            if t is not None:
                tags.append(t)
                form['tags'].append(tag)
            else:
                errors.append(_('Unknown tag "%s".') % tag)

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
            db.commit()

            html_post_detail = u'<a href="%s">%s</a>' % (
                escape(url_for(post)),
                escape(post.title)
            )

            # do automatic pingbacking if we can get all the links
            # by parsing the post, that is wanted and the post is
            # published.
            if form['ping_from_text']:
                if not post.is_published:
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
                                flash(_('Could not ping %s: %s') % (
                                    html_url,
                                    e.description
                                ), 'error')
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
                u'not installed any longer.  Because of that TextPress '
                u'doesn\'t allow modifcations on the text until you either '
                u'change the parser or reinstall/activate the plugin that '
                u'provided that parser.') % {'parser': escape(missing_parser)},
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
def do_delete_post(request, post_id):
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
        raise NotFound()
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('cancel'):
            return redirect('admin/edit_post', post_id=post.post_id)
        elif request.form.get('confirm'):
            redirect.add_invalid('admin/edit_post', post_id=post.post_id)
            db.execute(comments.delete(comments.c.post_id == post.post_id))
            db.execute(post_tags.delete(post_tags.c.post_id == post.post_id))
            db.execute(post_links.delete(post_links.c.post_id == post.post_id))
            db.delete(post)
            flash(_('The post %s was deleted successfully.') %
                  escape(post.title), 'remove')
            db.commit()
            return redirect('admin/show_posts')

    return render_admin_response('admin/delete_post.html', 'posts.write',
        post=post,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_show_comments(request, post_id=None):
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
            raise NotFound()
        comments = Comment.objects.filter(Comment.post_id == post_id).all()
    return render_admin_response('admin/show_comments.html',
                                 'comments.overview',
        post=post,
        comments=comments
    )


@require_role(ROLE_AUTHOR)
def do_edit_comment(request, comment_id):
    """
    Edit a comment.  Unlike the post edit screen it's not possible to create
    new comments from here, that has to happen from the post page.
    """
    # XXX: maybe we should give administrators the possibility to change
    # the parser associated with comments.
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
        'pub_date':     format_datetime(comment.pub_date),
        'blocked':      comment.blocked
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

        # cancel
        if request.form.get('cancel'):
            return redirect('admin/show_comments')

        # delete
        if request.form.get('delete'):
            return simple_redirect('admin/delete_comment', comment_id=comment_id)

        form['author'] = author = request.form.get('author')
        if not author:
            errors.append(_('You have to give the comment an author.'))
        form['email'] = email = request.form.get('email')
        if not email or not is_valid_email(email):
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
            errors.append(_('Unknown parser "%s".') % parser)
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
                comment.blocked_msg = _('blocked by %s') % request.user.display_name
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
                u'TextPress doesn\'t allow modifcations on the text until you '
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
def do_unblock_comment(request, comment_id):
    """
    Unblock a comment which was blocked by an antispam plugin or a user.
    Redirect rules are identical to the delete page, just that the exception
    for deleted comments is left out.
    """
    comment = Comment.objects.get(comment_id)
    if comment is None:
        return redirect(url_for('admin/show_comments'))
    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if request.method == 'POST':
        csrf_protector.assert_safe()
        if request.form.get('confirm'):
            comment.blocked = False
            comment.blocked_msg = ''
            db.commit()
            flash(_('Comment by %s unblocked successfully.') %
                  escape(comment.author), 'configure')
        return redirect('admin/show_comments')

    return render_admin_response('admin/unblock_comment.html',
                                 'comments.overview',
        comment=comment,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_show_tags(request):
    """
    Show a list of used post tag.  Tags can be used as web2.0 like tags or
    normal comments.
    """
    return render_admin_response('admin/show_tags.html', 'tags.overview',
                                 tags=Tag.objects.all())


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

    return render_admin_response('admin/edit_tag.html', 'tags.edit',
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_AUTHOR)
def do_delete_tag(request, tag_id):
    """
    Works like the other delete pages, just that it deletes tags.
    """
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
            db.execute(post_tags.delete(post_tags.c.tag_id == tag.tag_id))
            db.delete(tag)
            flash(_('Tag %s deleted successfully.') % escape(tag.name))
            db.commit()
            return redirect('admin/show_tags')

    return render_admin_response('admin/delete_tag.html', 'tags.edit',
        tag=tag,
        hidden_form_data=make_hidden_fields(csrf_protector, redirect)
    )


@require_role(ROLE_ADMIN)
def do_show_users(request):
    """Show all users in a list."""
    return render_admin_response('admin/show_users.html', 'users.overview',
        users=User.objects.all()
    )


@require_role(ROLE_ADMIN)
def do_edit_user(request, user_id=None):
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
            raise NotFound()
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
            errors.append(_('Username "%s" is taken.') % username)
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
        try:
            role = form['role'] = int(request.form.get('role', ''))
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
def do_delete_user(request, user_id):
    """
    Like all other delete screens just that it deletes a user.
    """
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
            if action == 'reassign':
                db.execute(posts.update(posts.c.author_id == user_id),
                    author_id=request.form.get('reassign_user', type=int)
                )
            elif action == 'delete':
                db.execute(posts.delete(posts.c.author_id == user_id))
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
    """
    So far just a redirect page, later it would be a good idea to have
    a page that shows all the links to configuration things in form of
    a simple table.
    """
    return simple_redirect('admin/basic_options')


@require_role(ROLE_ADMIN)
def do_basic_options(request):
    """
    The dialog for basic options such as the blog title etc.
    """
    cfg = request.app.cfg
    form = {
        'blog_title':           cfg['blog_title'],
        'blog_tagline':         cfg['blog_tagline'],
        'blog_email':           cfg['blog_email'],
        'timezone':             cfg['timezone'],
        'datetime_format':      cfg['datetime_format'],
        'date_format':          cfg['date_format'],
        'session_cookie_name':  cfg['session_cookie_name'],
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
        form['timezone'] = timezone = request.form.get('timezone')
        if timezone not in TIMEZONES:
            errors.append(_('Unknown timezone "%s"') % timezone)
        form['datetime_format'] = datetime_format = \
            request.form.get('datetime_format')
        form['date_format'] = date_format = \
            request.form.get('date_format')
        form['session_cookie_name'] = session_cookie_name = \
            request.form.get('session_cookie_name')
        form['comments_enabled'] = comments_enabled = \
            'comments_enabled' in request.form
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
        form['maintenance_mode'] = maintenance_mode = \
            'maintenance_mode' in request.form
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
            if session_cookie_name != cfg['session_cookie_name']:
                cfg['session_cookie_name'] = session_cookie_name
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
            return simple_redirect('admin/basic_options')

        for error in errors:
            flash(error, 'error')

    return render_admin_response('admin/basic_options.html', 'options.basic',
        form=form,
        timezones=sorted(TIMEZONES),
        parsers=request.app.list_parsers(),
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_ADMIN)
def do_urls(request):
    """
    A config page for URL depending settings.
    """
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
                    request.app.cfg[key] = value
                    changed = True
            if changed:
                flash(_('URL configuration changed.'), 'configure')

            # because the next request could reload the application and move
            # the admin interface we construct the URL to this page by hand.
            return redirect(form['admin_url_prefix'][1:] + '/options/urls')
        else:
            flash(errors[0], 'error')

    return render_admin_response('admin/urls.html', 'options.urls',
        form=form,
        hidden_form_data=make_hidden_fields(csrf_protector)
    )


@require_role(ROLE_ADMIN)
def do_theme(request):
    """
    Allow the user to select one of the themes that are available.
    """
    csrf_protector = CSRFProtector()
    new_theme = request.args.get('select')
    if new_theme in request.app.themes:
        csrf_protector.assert_safe()
        request.app.cfg['theme'] = new_theme
        flash(_('Theme changed successfully.'), 'configure')
        return simple_redirect('admin/theme')

    current = request.app.cfg['theme']
    return render_admin_response('admin/theme.html', 'options.theme',
        themes=[{
            'uid':          theme.name,
            'name':         theme.detail_name,
            'author':       theme.metadata.get('author'),
            'description':  theme.metadata.get('description'),
            'has_preview':  theme.has_preview,
            'preview_url':  theme.preview_url,
            'current':      name == current
        } for name, theme in sorted(request.app.themes.items())],
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_overlays(request, template=None):
    """
    Edit the theme overlays.
    """
    if not template:
        return redirect(url_for('admin/overlays', template='layout.html'))
    elif request.form.get('edit'):
        return redirect(url_for('admin/overlays',
                                template=request.form.get('template', '')))
    has_overlay=request.app.theme.overlay_exists(template)
    source = request.app.theme.get_source(template)
    if source is None:
        raise NotFound()
    elif source.endswith('\n'):
        source = source[:-1]

    if request.method == 'POST':
        if request.form.get('delete'):
            request.app.theme.remove_overlay(template)
            flash(_('Overlay %s removed.') % escape(template),
                  'remove')
        else:
            request.app.theme.set_overlay(template,
                                      request.form.get('source', ''))
            if has_overlay:
                flash(_('Updated overlay %s.') % escape(template))
            else:
                flash(_('Created overlay %s.') % escape(template),
                      'add')
        return redirect(url_for('admin/overlays', template=template))

    templates = [x for x in request.app.theme.list_templates()
                 if not x.startswith('admin/')]
    return render_admin_response('admin/overlays.html', 'options.theme',
        templates=templates,
        active_template=template,
        source=source,
        has_overlay=has_overlay
    )


@require_role(ROLE_ADMIN)
def do_widgets(request):
    """
    Configure the widgets.
    """
    manager = WidgetManager(request.app, '_widgets.html')
    if manager.manageable:
        # configure one widget
        configure = request.values.get('configure')
        if configure in request.app.widgets:
            widget = request.app.widgets[configure]
            args = widget.list_arguments(True)
            old_args = request.values.get('args')
            if old_args:
                try:
                    args.update(load_json(old_args))
                except Exception, e:
                    pass
            body = None
            args, body = widget.configure_widget(args, request)
            if args is body is None:
                args = {}
                body = ''
            return Response(dump_json({
                'body':     body,
                'args':     args
            }), mimetype='text/javascript')

        # or save all changes
        if request.method == 'POST':
            if request.values.get('revert'):
                manager.revert_to_default()
                flash(_('Removed personal widget set. Will use the '
                        'theme defaults now'))
            else:
                try:
                    widgets = load_json(request.values.get('widgets', ''))
                    if not isinstance(widgets, list):
                        raise TypeError()
                except Exception, e:
                    flash(_('invalid data submitted.'), 'error')
                else:
                    del manager.widgets[:]
                    for widget in widgets:
                        manager.widgets.append(tuple(widget))
                    manager.save()
                    flash(_('Widgets updated successfully.'))
            return redirect(url_for('admin/widgets'))

    # display all widgets in the admin panel
    all_widgets = dict((i, w.get_display_name())
                       for i, w in request.app.widgets.iteritems())

    # add all the widgets we use
    for script in 'Form.js', 'JSON.js', 'WidgetManager.js':
        add_script(url_for('core/shared', filename='js/' + script))

    return render_admin_response('admin/widgets.html', 'options.widgets',
        widgets=sorted(all_widgets, key=lambda x: x[1]),
        manageable=manager.manageable,
        default=manager.default,
        all_widgets=all_widgets,
        active_widgets=manager.widgets
    )


@require_role(ROLE_ADMIN)
def do_plugins(request):
    """
    Load and unload plugins and reload TextPress if required.
    """
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()

        if request.form.get('enable_guard'):
            request.app.cfg['plugin_guard'] = True
            flash(_('Plugin guard enabled successfully. Errors '
                    'occuring in plugins during setup are catched now.'))
        elif request.form.get('disable_guard'):
            request.app.cfg['plugin_guard'] = False
            flash(_('Plugin guard disabled successfully.'))

        for name, plugin in request.app.plugins.iteritems():
            active = 'plugin_' + name in request.form
            if active and not plugin.active:
                plugin.activate()
                flash(_('Plugin "%s" activated.') % plugin.html_display_name,
                      'configure')
            elif not active and plugin.active:
                plugin.deactivate()
                flash(_('Plugin "%s" deactivated.') %
                      plugin.html_display_name, 'configure')
            else:
                continue

        new_plugin = request.files.get('new_plugin')
        if new_plugin:
            try:
                plugin = install_package(request.app, new_plugin)
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

        return simple_redirect('admin/plugins')

    return render_admin_response('admin/plugins.html', 'options.plugins',
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name),
        csrf_protector=csrf_protector,
        guard_enabled=request.app.cfg['plugin_guard']
    )


@require_role(ROLE_ADMIN)
def do_remove_plugin(request, plugin):
    """
    Remove an inactive, instance installed plugin completely.
    """
    plugin = request.app.plugins.get(plugin)
    if plugin is None or \
       plugin.builtin_plugin or \
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
                flash(_('Could not remove the plugin %s because an '
                        'IO error occoured. Wrong permissions?') %
                      plugin.html_display_name)
            flash(_('The plugin "%s" was removed from the instance '
                    'successfully.') % escape(plugin.display_name), 'remove')
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
            if cache_system != cfg['cache_system']:
                cfg['cache_system'] = cache_system
            if cache_timeout != cfg['cache_timeout']:
                cfg['cache_timeout'] = cache_timeout
            if enable_eager_caching != cfg['enable_eager_caching']:
                cfg['enable_eager_caching'] = enable_eager_caching
            if memcached_servers != cfg['memcached_servers']:
                cfg['memcached_servers'] = memcached_servers
            if filesystem_cache_path != cfg['filesystem_cache_path']:
                cfg['filesystem_cache_path'] = filesystem_cache_path
            flash(_('Updated cache settings.'), 'configure')

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
    """
    Advanced configuration editor.  This is useful for development or if a
    plugin doesn't ship an editor for the configuration values.  Because all
    the values are not further checked it could easily be that TextPress is
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
            for key, value in request.form.iteritems():
                key = key.replace('.', '/')
                if key.endswith('__DEFAULT'):
                    key = key[:-9]
                    request.app.cfg.revert_to_default(key)
                    already_default.add(key)
                elif key in request.app.cfg and key not in already_default:
                    request.app.cfg.set_from_string(key, value)
        return simple_redirect('admin/configuration')

    # html does not allow slashes.  Convert them to dots
    categories = []
    for category in request.app.cfg.get_detail_list():
        for item in category['items']:
            item['key'] = item['key'].replace('/', '.')
        categories.append(category)

    return render_admin_response('admin/configuration.html',
                                 'options.configuration',
        categories=categories,
        editor_enabled=request.session.get('ace_on', False),
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_about(request):
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
    multithreaded = thread_count > 1 and request.is_multithread

    return render_admin_response('admin/about.html', 'about.system',
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
            'multithreaded':    multithreaded,
            'thread_count':     thread_count,
            'multiprocess':     request.is_multiprocess,
            'wsgi_version':     '.'.join(map(str, request.environ['wsgi.version']))
        },
        plugins=sorted(request.app.plugins.values(), key=lambda x: x.name),
        textpress_version='.'.join(map(str, version_info[0:3])),
        textpress_tag=version_info[3],
        textpress_hg_node=version_info[4],
        textpress_hg_checkout=version_info[4] is not None,
        template_globals=[name for name, obj in
                          sorted(request.app.template_env.globals.items())
                          if name not in DEFAULT_NAMESPACE],
        template_filters=[name for name, obj in
                          sorted(request.app.template_env.filters.items())
                          if name not in DEFAULT_FILTERS],
        can_build_eventmap=can_build_eventmap,
        instance_path=request.app.instance_folder,
        database_uri=str(request.app.database_engine.url)
    )


@require_role(ROLE_AUTHOR)
def do_eventmap(request):
    """
    The GUI version of the `textpress-management.py eventmap` command.
    Traverses the sourcecode for emit_event calls using the python2.5
    ast compiler.  Because of that it raises an page not found exception
    for python2.4.
    """
    if not can_build_eventmap:
        raise NotFound()
    return render_admin_response('admin/eventmap.html', 'about.eventmap',
        get_map=lambda: sorted(build_eventmap(request.app).items()),
        # walking the tree can take some time, so better use stream
        # processing for this template. that's also the reason why
        # the building process is triggered from inside the template.
        # stream rendering however is buggy in wsgiref :-/
        _stream=True
    )


@require_role(ROLE_AUTHOR)
def do_about_textpress(request):
    """
    Just show the textpress license and some other legal stuff.
    """
    return render_admin_response('admin/about_textpress.html',
                                 'about.textpress')


@require_role(ROLE_AUTHOR)
def do_change_password(request):
    """
    Allow the current user to change his password.
    """
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
