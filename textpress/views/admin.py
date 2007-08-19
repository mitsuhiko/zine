# -*- coding: utf-8 -*-
"""
    textpress.views.admin
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements the admin views. The admin interface is only
    available for admins, editors and authors but not for subscribers. For
    subscribers a simplified account management system exists at /account.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime
from weakref import WeakKeyDictionary
from textpress.api import *
from textpress.models import User, Post, Tag, Comment, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED, get_post_list
from textpress.utils import parse_datetime, format_datetime, \
     is_valid_email, is_valid_url, get_version_info, can_build_eventmap, \
     build_eventmap, CSRFProtector, TIMEZONES


def render_admin_response(template_name, **values):
    """
    Works pretty much like the normal `render_response` function but
    it emits some events to collect navigation items and injects that
    into the template context.
    """
    req = get_request()
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

    if req.user.role == ROLE_ADMIN:
        navigation_bar += [
            ('users', url_for('admin/show_users'), _('Users'), [
                ('overview', url_for('admin/show_users'), _('Overview')),
                ('edit', url_for('admin/new_user'), _('Edit User'))
            ]),
            ('options', url_for('admin/options'), _('Options'), [
                ('basic', url_for('admin/basic_options'), _('Basic')),
                ('theme', url_for('admin/theme'), _('Theme')),
                ('plugins', url_for('admin/plugins'), _('Plugins')),
                ('configuration', url_for('admin/configuration'),
                 _('Configuration Editor'))
            ])
        ]

    about_items = [
        ('system', url_for('admin/about'), _('System')),
        ('textpress', url_for('admin/about_textpress'), _('TextPress'))
    ]
    if can_build_eventmap:
        about_items.insert(1, ('eventmap', url_for('admin/eventmap'),
                               _('Event Map')))
    navigation_bar.append(('about', url_for('admin/about'), _('About'),
                          about_items))

    # allow plugins to modify the navigation bar
    emit_event('modify-admin-navigation-bar', navigation_bar, buffered=True)

    values['admin'] = {
        'navigation':   [{
            'id':       id,
            'url':      url,
            'title':    title,
            'children': [{
                'id':       id,
                'url':      url,
                'title':    title
            } for id, url, title in children or ()]
        } for id, url, title, children in navigation_bar]
    }

    emit_event('before-admin-response-rendered', req, values, buffered=True)
    return render_response(template_name, **values)


@require_role(ROLE_AUTHOR)
def do_index(req):
    return render_admin_response('admin/index.html')


@require_role(ROLE_AUTHOR)
def do_show_posts(req):
    return render_admin_response('admin/show_posts.html', **get_post_list())


@require_role(ROLE_AUTHOR)
def do_edit_post(req, post_id=None):
    tags = []
    errors = []
    form = {}
    post = None
    csrf_protector = CSRFProtector(req)

    # edit existing post
    if post_id is not None:
        new_post = False
        post = Post.get(post_id)
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
            author=post.author.username
        )
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
            pub_date='now',
            slug='',
            author=req.user.username
        )

    # handle incoming data and create/update the post
    if req.method == 'POST':
        # make sure we don't have an CSRF attack
        csrf_protector.assert_safe()

        # handle cancel
        if req.form.get('cancel'):
            redirect(url_for('admin/show_posts'))

        # handle delete, redirect to confirmation page
        if req.form.get('delete') and post_id is not None:
            redirect(url_for('admin/delete_post', post_id=post_id))

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
        try:
            pub_date = parse_datetime(req.form.get('pub_date') or 'now')
        except ValueError:
            errors.append(_('Invalid publication date.'))

        username = req.form.get('author')
        if not username:
            author = req.user
            username = author.username
        else:
            author = User.get_by(username=username)
            if author is None:
                errors.append(_('Unknown author "%s".') % username)
        form['author'] = author
        form['slug'] = slug = req.form.get('slug') or None
        form['tags'] = []
        tags = []
        for tag in req.form.getlist('tags'):
            t = Tag.get_by(slug=tag)
            if t is not None:
                tags.append(t)
                form['tags'].append(tag)
            else:
                errors.append(_('Unknown tag "%s".') % tag)

        # if someone adds a tag we don't save the post but just add
        # a tag to the list and assign it to the post list.
        add_tag = req.form.get('add_tag')
        if add_tag:
            form['tags'].append(Tag.get_or_create(add_tag).slug)
            db.flush()
            del errors[:]

        # if there is no need tag and there are no errors we save the post
        elif not errors:
            if new_post:
                post = Post(title, author.user_id, body, intro, slug, pub_date)
            else:
                post.title = title
                post.author_id = author.user_id
                post.raw_body = body
                post.raw_intro = intro
                post.slug = slug
                post.pub_date = pub_date
            post.tags[:] = tags
            post.comments_enabled = form['comments_enabled']
            post.pings_enabled = form['pings_enabled']
            post.status = post_status
            post.last_update = max(datetime.utcnow(), pub_date)
            db.flush()

            # show new post editor or the same again
            if req.form.get('save_and_new'):
                if new_post:
                    url = url_for('admin/new_post', created=post.post_id)
                else:
                    url = url_for('admin/new_post')
            else:
                url = url_for('admin/edit_post', post_id=post.post_id)
            redirect(url)

    # if there is a "created" parameter, show post details
    created = req.args.get('created')
    if created:
        created = Post.get(created)

    return render_admin_response('admin/edit_post.html',
        errors=errors,
        new_post=new_post,
        form=form,
        tags=Tag.select(),
        created=created,
        post=post,
        post_status_choices=[
            (STATUS_PUBLISHED, _('Published')),
            (STATUS_DRAFT, _('Draft')),
            (STATUS_PRIVATE, _('Private'))
        ],
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_delete_post(req, post_id):
    post = Post.get(post_id)
    if post is None:
        redirect(url_for('admin/show_posts'))
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        # make sure the request is safe
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect(url_for('admin/edit_post', post_id=post.post_id))
        elif req.form.get('confirm'):
            post.delete()
            db.flush()
            redirect(url_for('admin/show_posts'))

    return render_admin_response('admin/delete_post.html',
        post=post,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_show_comments(req, post_id=None):
    post = None
    if post_id is None:
        comments = Comment.select()
    else:
        post = Post.get(post_id)
        if post is None:
            abort(404)
        comments = Comment.select(Comment.c.post_id == post_id)
    return render_admin_response('admin/show_comments.html',
        post=post,
        comments=comments
    )


@require_role(ROLE_AUTHOR)
def do_edit_comment(req, comment_id):
    """Edit a comment."""
    comment = Comment.get(comment_id)
    if comment is None:
        abort(404)

    errors = []
    form = {
        'author':       comment.author,
        'email':        comment.email,
        'www':          comment.www,
        'body':         comment.body,
        'pub_date':     format_datetime(comment.pub_date),
        'blocked':      comment.blocked
    }
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        # make sure there is not csrf attack
        csrf_protector.assert_safe()

        # cancel
        if req.form.get('cancel'):
            redirect(url_for('admin/show_comments'))

        # delete
        if req.form.get('delete'):
            redirect(url_for('admin/delete_comment', comment_id=comment_id))

        form['author'] = author = req.form.get('author')
        if not author:
            errors.append(_('You have to give the comment an author.'))
        form['email'] = email = req.form.get('email')
        if not email or not is_valid_email(email):
            errors.append(_('You have to provide a valid mail address for the author.'))
        form['www'] = www = req.form.get('www')
        form['body'] = body = req.form.get('body')
        if not body:
            errors.append(_('Need a text for this comment.'))
        if www and not is_valid_url(www):
            errors.append(_('You have to ommitt the url or provide a valid one.'))
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
            comment.body = body
            comment.blocked = blocked
            if not blocked:
                comment.blocked_msg = ''
            elif not comment.blocked_msg:
                comment.blocked_msg = _('blocked by user')
            comment.save()
            db.flush()
            redirect(url_for('admin/show_comments'))

    return render_admin_response('admin/edit_comment.html',
        comment=comment,
        form=form,
        errors=errors
    )


@require_role(ROLE_AUTHOR)
def do_delete_comment(req, comment_id):
    comment = Comment.get(comment_id)
    if comment is None:
        redirect(url_for('admin/show_comments'))
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        # make sure there is no CSRF attack
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect(url_for('admin/edit_comment', comment_id=comment.comment_id))
        elif req.form.get('confirm'):
            comment.delete()
            db.flush()
            redirect(url_for('admin/show_comments'))

    return render_admin_response('admin/delete_comment.html',
        comment=comment,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_show_tags(req):
    return render_admin_response('admin/show_tags.html', tags=Tag.select())


@require_role(ROLE_AUTHOR)
def do_edit_tag(req, tag_id=None):
    """Edit a tag."""
    errors = []
    form = dict.fromkeys(['slug', 'name', 'description'], u'')
    csrf_protector = CSRFProtector(req)
    new_tag = True

    if tag_id is not None:
        tag = Tag.get(tag_id)
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
        # make sure the request is from a user not an attacker
        csrf_protector.assert_safe()

        # cancel
        if req.form.get('cancel'):
            redirect(url_for('admin/show_tags'))

        # delete
        if req.form.get('delete'):
            redirect(url_for('admin/delete_tag', tag_id=tag.tag_id))

        form['slug'] = slug = req.form.get('slug')
        form['name'] = name = req.form.get('name')
        form['description'] = description = req.form.get('description')

        if not name:
            errors.append(_('You have to give the tag a name.'))
        elif old_slug != slug and Tag.get_by(slug=slug) is not None:
            errors.append(_('The slug "%s" is not unique.') % slug)

        if not errors:
            if new_tag:
                Tag(name, description, slug or None)
            else:
                if tag.slug is not None:
                    tag.slug = slug
                tag.name = name
                tag.description = description
            db.flush()
            redirect(url_for('admin/show_tags'))

    return render_admin_response('admin/edit_tag.html',
        errors=errors,
        form=form,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_delete_tag(req, tag_id):
    tag = Tag.get(tag_id)
    if tag is None:
        redirect(url_for('admin/show_tags'))
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        # check for possible CSRF attacks
        csrf_protector.assert_safe()

        if req.form.get('cancel'):
            redirect(url_for('admin/edit_tag', tag_id=tag.tag_id))
        elif req.form.get('confirm'):
            tag.delete()
            db.flush()
            redirect(url_for('admin/show_tags'))

    return render_admin_response('admin/delete_tag.html',
        tag=tag,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_show_users(req):
    return render_admin_response('admin/show_users.html',
        users=User.get_all_but_nobody()
    )


@require_role(ROLE_ADMIN)
def do_edit_user(req, user_id=None):
    user = None
    errors = []
    form = dict.fromkeys(['username', 'first_name', 'last_name',
                          'display_name', 'description', 'email'], u'')
    form['role'] = ROLE_AUTHOR
    csrf_protector = CSRFProtector(req)

    if user_id is not None:
        user = User.get(user_id)
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
            redirect(url_for('admin/show_users'))
        elif req.form.get('delete') and user:
            redirect(url_for('admin/delete_user', user_id=user.user_id))

        username = form['username'] = req.form.get('username')
        if not username:
            errors.append(_('Username is required.'))
        elif new_user and User.get_by(username=username) is not None:
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
            db.flush()
            if req.form.get('save_and_new'):
                redirect(url_for('admin/new_user'))
            else:
                redirect(url_for('admin/edit_user', user_id=user.user_id))

    if not new_user:
        display_names = [
            ('$first $last', u'%s %s' % (user.first_name, user.last_name)),
            ('$last $first', u'%s %s' % (user.last_name, user.first_name)),
            ('$nick', user.username),
            ('$first', user.first_name),
            ('$last', user.last_name),
            ('$first "$nick" $last', u'%s "%s" %s' % (
                user.first_name,
                user.username,
                user.last_name
            ))
        ]
    else:
        display_names = None

    return render_admin_response('admin/edit_user.html',
        new_user=user is None,
        user=user,
        form=form,
        errors=errors,
        display_names=display_names,
        roles=[
            (ROLE_ADMIN, _('Administrator')),
            (ROLE_EDITOR, _('Editor')),
            (ROLE_AUTHOR, _('Author')),
            (ROLE_SUBSCRIBER, _('Subscriber'))
        ],
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_delete_user(req, user_id):
    user = User.get(user_id)
    if user is None:
        redirect(url_for('admin/show_users'))
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('cancel'):
            redirect(url_for('admin/edit_user', user_id=user.user_id))
        elif req.form.get('confirm'):
            user.delete()
            db.flush()
            redirect(url_for('admin/show_users'))

    return render_admin_response('admin/delete_user.html',
        user=user,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_options(req):
    redirect(url_for('admin/basic_options'))


@require_role(ROLE_ADMIN)
def do_basic_options(req):
    cfg = req.app.cfg
    form = {
        'blog_title':           cfg['blog_title'],
        'blog_tagline':         cfg['blog_tagline'],
        'timezone':             cfg['timezone'],
        'datetime_format':      cfg['datetime_format'],
        'date_format':          cfg['date_format'],
        'sid_cookie_name':      cfg['sid_cookie_name'],
        'comments_enabled':     cfg['comments_enabled'],
        'pings_enabled':        cfg['pings_enabled'],
        'posts_per_page':       cfg['posts_per_page'],
        'use_flat_comments':    cfg['use_flat_comments']
    }
    errors = []
    csrf_protector = CSRFProtector(req)

    if req.method == 'POST':
        csrf_protector.assert_safe()
        form['blog_title'] = blog_title = req.form.get('blog_title')
        if not blog_title:
            errors.append(_('You have to provide a blog title'))
        form['blog_tagline'] = blog_tagline = req.form.get('blog_tagline')
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
        form['posts_per_page'] = req.form.get('posts_per_page', '')
        try:
            posts_per_page = int(form['posts_per_page'])
            if posts_per_page < 1:
                errors.append(_('Posts per page must be at least 1'))
        except ValueError:
            errors.append(_('Posts per page must be a valid integer'))
        form['use_flat_comments'] = use_flat_comments = \
            req.form.get('use_flat_comments') == 'yes'
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
            if posts_per_page != cfg['posts_per_page']:
                cfg['posts_per_page'] = posts_per_page
            if use_flat_comments != cfg['use_flat_comments']:
                cfg['use_flat_comments'] = use_flat_comments

    return render_admin_response('admin/basic_options.html',
        form=form,
        errors=errors,
        timezones=TIMEZONES,
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_theme(req):
    csrf_protector = CSRFProtector(req)
    new_theme = req.args.get('select')
    if new_theme in req.app.themes:
        csrf_protector.assert_safe()
        req.app.cfg['theme'] = new_theme
        redirect(url_for('admin/theme'))

    current = req.app.cfg['theme']
    return render_admin_response('admin/theme.html',
        themes=[{
            'uid':          theme.name,
            'name':         theme.detail_name,
            'author':       theme.metadata.get('author'),
            'description':  theme.metadata.get('summary'),
            'has_preview':  theme.has_preview,
            'preview_url':  theme.preview_url,
            'current':      name == current
        } for name, theme in sorted(req.app.themes.items())],
        csrf_protector=csrf_protector
    )


@require_role(ROLE_ADMIN)
def do_plugins(req):
    changes = _outstanding_plugin_changes.setdefault(req.app, set())
    old_changes = list(changes)
    csrf_protector = CSRFProtector(req)
    if req.method == 'POST':
        csrf_protector.assert_safe()
        for name, plugin in req.app.plugins.iteritems():
            active = req.form.get(name) == 'yes'
            if active and not plugin.active:
                plugin.activate()
            elif not active and plugin.active:
                plugin.deactivate()
            else:
                continue
            changes.add(name)
    return render_admin_response('admin/plugins.html',
        plugins=sorted(req.app.plugins.values(), key=lambda x: x.name),
        outstanding_changes=old_changes,
        csrf_protector=csrf_protector
    )

#: helper variable for `do_plugins`. In persistent environments this
#: weak dictionary holds plugin changes for the applications so that
#: the user is informed about outstanding changes that take effect
#: once the application is restarted.
_outstanding_plugin_changes = WeakKeyDictionary()


@require_role(ROLE_ADMIN)
def do_configuration(req):
    csrf_protector = CSRFProtector(req)
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
        redirect(url_for('admin/configuration'))

    return render_admin_response('admin/configuration.html',
        categories=req.app.cfg.get_detail_list(),
        editor_enabled=req.session.get('configuration_editor_enabled', False),
        csrf_protector=csrf_protector
    )


@require_role(ROLE_AUTHOR)
def do_about(req):
    from threading import activeCount
    from jinja.defaults import DEFAULT_NAMESPACE, DEFAULT_FILTERS

    thread_count = activeCount()
    version_info = get_version_info()
    multithreaded = thread_count > 1 and req.environ['wsgi.multithread']

    return render_admin_response('admin/about.html',
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
    if not can_build_eventmap:
        abort(404)
    return render_admin_response('admin/eventmap.html',
        get_map=lambda: sorted(build_eventmap(req.app).items()),
        # walking the tree can take some time, so better use stream
        # processing for this template. that's also the reason why
        # the building process is triggered from inside the template.
        # stream rendering however is buggy in wsgiref :-/
        _stream=True
    )


@require_role(ROLE_AUTHOR)
def do_about_textpress(req):
    return render_admin_response('admin/about_textpress.html')


@require_role(ROLE_AUTHOR)
def do_change_password(req):
    errors = []
    csrf_protector = CSRFProtector(req)
    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('cancel'):
            redirect(url_for('admin/index'))
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
            req.user.save()
            db.flush()
            redirect(url_for('admin/index'))
    return render_admin_response('admin/change_password.html',
        errors=errors,
        csrf_protector=csrf_protector
    )


def do_login(req):
    """Show a login page."""
    error = None
    username = ''

    if req.method == 'POST':
        username = req.form.get('username')
        password = req.form.get('password', '')
        if username:
            user = User.get_by(username=username)
            if user is None:
                error = _('User %s does not exist.') % username
            elif user.check_password(password):
                req.login(user)
                next = req.values.get('next')
                if next is None:
                    next = url_for('admin/index')
                redirect(next)
            else:
                error = _('Incorrect password.')
        else:
            error = _('You have to enter a username.')

    return render_admin_response('admin/login.html', error=error,
                                 username=username,
                                 logged_out=req.values.get('logout') == 'yes')


def do_logout(req):
    req.logout()
    redirect(url_for('admin/login', logout='yes'))
