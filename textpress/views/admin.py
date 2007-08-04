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
from textpress.api import *
from textpress.models import User, Post, Tag, Comment, ROLE_ADMIN, \
     ROLE_EDITOR, ROLE_AUTHOR, ROLE_SUBSCRIBER, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED, get_post_list
from textpress.utils import parse_datetime, format_datetime, \
     is_valid_email, is_valid_url


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
                ('overview', url_for('admin/options'), _('Overview')),
                ('configuration', url_for('admin/configuration'),
                 _('Configuration Editor'))
            ])
        ]

    for result in emit_event('collect-admin-navigation-links'):
        navigation_bar.extend(result or ())

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
    post=None

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
        new_post=new_post,
        post=post,
        post_status_choices=[
            (STATUS_PUBLISHED, _('Published')),
            (STATUS_DRAFT, _('Draft')),
            (STATUS_PRIVATE, _('Private'))
        ]
    )


@require_role(ROLE_AUTHOR)
def do_delete_post(req, post_id):
    post = Post.get(post_id)
    if post is None:
        redirect(url_for('admin/show_posts'))

    if req.method == 'POST':
        if req.form.get('cancel'):
            redirect(url_for('admin/edit_post', post_id=post.post_id))
        elif req.form.get('confirm'):
            post.delete()
            db.flush()
            redirect(url_for('admin/show_posts'))

    return render_admin_response('admin/delete_post.html', post=post)


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
    errors = []

    comment = Comment.get(comment_id)
    if comment is None:
        abort(404)
    form = {
        'author':       comment.author,
        'email':        comment.email,
        'www':          comment.www,
        'body':         comment.body,
        'pub_date':     format_datetime(comment.pub_date),
        'blocked':      comment.blocked
    }

    if req.method == 'POST':
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

    if req.method == 'POST':
        if req.form.get('cancel'):
            redirect(url_for('admin/edit_comment', comment_id=comment.comment_id))
        elif req.form.get('confirm'):
            comment.delete()
            db.flush()
            redirect(url_for('admin/show_comments'))

    return render_admin_response('admin/delete_comment.html', comment=comment)


@require_role(ROLE_AUTHOR)
def do_show_tags(req):
    return render_admin_response('admin/show_tags.html', tags=Tag.select())


@require_role(ROLE_AUTHOR)
def do_edit_tag(req, tag_id=None):
    """Edit a tag."""
    errors = []
    form = dict.fromkeys(['slug', 'name', 'description'], u'')
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
        form=form
    )


@require_role(ROLE_AUTHOR)
def do_delete_tag(req, tag_id):
    tag = Tag.get(tag_id)
    if tag is None:
        redirect(url_for('admin/show_tags'))

    if req.method == 'POST':
        if req.form.get('cancel'):
            redirect(url_for('admin/edit_tag', tag_id=tag.tag_id))
        elif req.form.get('confirm'):
            tag.delete()
            db.flush()
            redirect(url_for('admin/show_tags'))

    return render_admin_response('admin/delete_tag.html', tag=tag)


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
        ]
    )


@require_role(ROLE_ADMIN)
def do_delete_user(req, user_id):
    user = User.get(user_id)
    if user is None:
        redirect(url_for('admin/show_users'))

    if req.method == 'POST':
        if req.form.get('cancel'):
            redirect(url_for('admin/edit_user', user_id=user.user_id))
        elif req.form.get('confirm'):
            user.delete()
            db.flush()
            redirect(url_for('admin/show_users'))

    return render_admin_response('admin/delete_user.html', user=user)


@require_role(ROLE_ADMIN)
def do_options(req):
    redirect(url_for('admin/configuration'))


@require_role(ROLE_ADMIN)
def do_configuration(req):
    if req.method == 'POST':
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
        editor_enabled=req.session.get('configuration_editor_enabled', False)
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
