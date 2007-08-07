# -*- coding: utf-8 -*-
"""
    textpress.views.blog
    ~~~~~~~~~~~~~~~~~~~~

    This module implements all the views (some people call that controller)
    for the core module.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.models import Post, Tag, User, Comment, get_post_list, \
     get_tag_cloud, ROLE_AUTHOR
from textpress.utils import is_valid_email, is_valid_url, generate_rsd, \
     dump_json
from textpress.feedbuilder import AtomFeed


def do_index(req, page=1):
    """
    Render the most recent posts.

    Available template variables:

        `posts`:
            a list of post objects we want to display

        `pagination`:
            a pagination object to render a pagination

    :Template name: ``index.html``
    :URL endpoint: ``blog/index``
    """
    data = get_post_list(page=page)
    if data.pop('probably_404'):
        abort(404)

    add_link('alternate', url_for('blog/atom_feed'), 'application/atom+xml',
             _('Recent Posts Feed'))
    return render_response('index.html', **data)


def do_archive(req, year=None, month=None, day=None, page=1):
    """
    Render the monthly archives.

    Available template variables:

        `posts`:
            a list of post objects we want to display

        `pagination`:
            a pagination object to render a pagination

        `year` / `month` / `day`:
            integers or None, useful to entitle the page.

    :Template name: ``archive.html``
    :URL endpoint: ``blog/archive``
    """
    data = get_post_list(year, month, day, page)
    if data.pop('probably_404'):
        abort(404)

    feed_parameters = {}
    for name, value in [('year', year), ('month', month), ('day', day)]:
        if value is not None:
            feed_parameters[name] = value
    add_link('alternate', url_for('blog/atom_feed', **feed_parameters),
             'application/atom+xml', _('Recent Posts Feed'))
    return render_response('archive.html', year=year, month=month, day=day,
                           **data)


def do_show_tag(req, slug, page=1):
    """
    Show all posts tagged with a given tag slug.

    Available template variables:

        `posts`:
            a list of post objects we want to display

        `pagination`:
            a pagination object to render a pagination

        `tag`
            the tag object for this page.

    :Template name: ``show_tag.html``
    :URL endpoint: ``blog/show_tag``
    """
    tag = Tag.get_by(slug=slug)
    data = get_post_list(tag=slug, page=page)
    if data.pop('probably_404'):
        abort(404)

    add_link('alternate', url_for('blog/atom_feed', tag=slug),
             'application/atom+xml', _('All posts tagged %s') % tag.name)
    return render_response('show_tag.html', tag=tag, **data)


def do_show_tag_cloud(req):
    """
    Show all posts tagged with a given tag slug.

    Available template variables:

        `tagcloud`:
            list of tag summaries that contain the size of the cloud
            item, the name of the tag and it's slug

    :Template name: ``tag_cloud.html``
    :URL endpoint: ``blog/tag_cloud``
    """
    return render_response('tag_cloud.html', tag_cloud=get_tag_cloud())


def do_show_author(req, username, page=1):
    """
    Show the user profile of an author / editor or administrator.

    Available template variables:

        `posts`:
            a list of post objects this author wrote and are
            visible on this page.

        `pagination`:
            a pagination object to render a pagination

        `user`
            The user object for this author

    :Template name: ``show_author.html``
    :URL endpoint: ``blog/show_author``
    """
    user = User.selectfirst((User.c.username == username) &
                            (User.c.role >= ROLE_AUTHOR))
    if user is None:
        abort(404)
    data = get_post_list(author=user)
    if data.pop('probably_404'):
        abort(404)

    add_link('alternate', url_for('blog/atom_feed', author=username),
             'application/atom+xml', _('All posts written by %s') %
             user.display_name)

    return render_response('show_author.html', user=user, **data)


def do_authors(req):
    """
    Show a list of authors.

    Available template variables:

        `authors`:
            list of author objects to display.

    :Template name: ``authors.html``
    :URL endpoint: ``blog/authors``
    """
    return render_response('authors.html', authors=User.get_authors())


def do_show_post(req, year, month, day, slug):
    """
    Show as post and give users the possibility to comment to this
    story if comments are enabled.

    Available template variables:

        `post`:
            The post object we display.

        `form`:
            A dict of form values (name, email, www and body)

        `errors`:
            List of error messages that occurred while posting the
            comment. If empty the form was not submitted or everyhing
            worked well.

    Events emitted:

        `before-comment-created`:
            this event is sent with the form as event data. Can return
            a list of error messages to prevent the user from posting
            that comment.

        `before-comment-saved`:
            executed right before the comment is saved to the database.
            The event data is set to the comment. This is usually used
            to block the comment (setting the blocked and blocked_msg
            attributes) so that administrators have to approve them.

        `after-comment-saved`:
            executed right after comment was saved to the database. Can be
            used to send mail notifications and stuff like that.

    :Template name: ``show_post.html``
    :URL endpoint: ``blog/show_post``
    """
    post = Post.by_timestamp_and_slug(year, month, day, slug)
    if post is None:
        abort(404)
    elif not post.can_access():
        abort(403)

    # handle comment posting
    errors = []
    form = {'name': '', 'email': '', 'www': '', 'body': '', 'parent': ''}
    if req.method == 'POST' and post.comments_enabled:
        form['name'] = name = req.form.get('name')
        if not name:
            errors.append(_('You have to enter your name.'))
        form['email'] = email = req.form.get('email')
        if not (email and is_valid_email(email)):
            errors.append(_('You have to enter a valid mail address.'))
        form['www'] = www = req.form.get('www')
        if www and not is_valid_url(www):
            errors.append(_('You have to enter a valid URL or omit the field.'))
        form['body'] = body = req.form.get('body')
        if not body or len(body) < 10:
            errors.append(_('Your comment is too short.'))
        elif len(body) > 6000:
            errors.append(_('Your comment is too long.'))
        form['parent'] = parent = req.form.get('parent')
        if parent:
            parent = Comment.get(parent)
        else:
            parent = None

        # allow plugins to do additional comment validation
        data = {'form': form, 'request': req}
        for result in emit_event('before-comment-created', data):
            errors.extend(result or ())

        # if we don't have errors let's save it and emit an
        # `before-comment-saved` event so that plugins can do
        # block comments so that administrators have to approve it
        if not errors:
            ip = req.environ.get('REMOTE_ADDR') or '0.0.0.0'
            comment = Comment(post, name, email, www, body, parent, submitter_ip=ip)
            data = {'comment': comment, 'request': req}
            emit_event('before-comment-saved', data)
            db.flush()
            emit_event('after-comment-saved', data)
            redirect(url_for(post))

    return render_response('show_post.html',
        post=post,
        form=form,
        errors=errors
    )


def do_service_rsd(req):
    """
    Serves and RSD definition (really simple discovery) so that blog frontends
    can query the apis that are available.

    :URL endpoint: ``blog/service_rsd``
    """
    return Response(generate_rsd(req.app), mimetype='application/xml')


def do_json_service(req, identifier):
    """
    Handle a JSON service request.
    """
    handler = req.app._services.get(identifier)
    if handler is None:
        abort(404)
    return Response(dump_json(handler(req)), mimetype='text/javascript')


def do_atom_feed(req, author=None, year=None, month=None, day=None,
                      tag=None, post_slug=None):
    """
    Renders an atom feed requested.

    :URL endpoint: ``blog/atom_feed``
    """
    if post_slug is not None:
        return Response('Not implemented', mimetype='text/plain')

    blog_link = url_for('blog/index', _external=True)
    postlist = get_post_list(year, month, day, tag, author)
    feed = AtomFeed(_('Posts'), _('give me a description'), blog_link)

    for post in postlist['posts']:
        feed.add_item(post.title, post.author.display_name, url_for(post,
                      _external=True), post.body, post.pub_date)

    return feed.generate_response()
