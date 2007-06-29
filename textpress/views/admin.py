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
from textpress.models import User, Post, Tag, ROLE_AUTHOR, STATUS_PRIVATE, \
     STATUS_DRAFT, STATUS_PUBLISHED, get_post_list
from textpress.utils import parse_datetime, format_datetime


def render_admin_response(template_name, **values):
    """
    Works pretty much like the normal `render_response` function but
    it emits some events to collect navigation items and injects that
    into the template context.
    """
    navigation_bar = [
        ('dashboard', url_for('admin/index'), _('Dashboard'), []),
        ('posts', url_for('admin/show_posts'), _('Posts'), [
            ('overview', url_for('admin/show_posts'), _('Overview')),
            ('write', url_for('admin/new_post'), _('Write Post'))
        ]),
        ('tags', url_for('admin/show_tags'), _('Tags'), [
            ('overview', url_for('admin/show_tags'), _('Overview')),
            ('edit', url_for('admin/new_tag'), _('Edit Tag'))
        ]),
        ('users', url_for('admin/show_users'), _('Users'), [
            ('overview', url_for('admin/show_users'), _('Users')),
            ('edit', url_for('admin/new_user'), _('Edit User'))
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


def do_show_tags(req):
    return render_admin_response('admin/show_tags.html', tags=Tag.select())


def do_edit_tag(req, tag_id=None):
    """Edit a tag."""
    errors = []
    form = {'slug': '', 'name': '', 'description': ''}
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


def do_show_users(req):
    return render_admin_response('admin/show_users.html', users=User.select())


def do_edit_user(req, user_id=None):
    pass


def do_delete_user(req, user_id):
    pass


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
