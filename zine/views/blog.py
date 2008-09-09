# -*- coding: utf-8 -*-
"""
    zine.views.blog
    ~~~~~~~~~~~~~~~

    This module implements all the views (some people call that controller)
    for the core module.

    :copyright: 2007-2008 by Armin Ronacher, Pedro Algarvio, Christopher Grebs,
                             Ali Afshar.
    :license: GNU GPL.
"""
from os.path import exists
from time import asctime, gmtime, time
from datetime import date

from zine import cache, pingback
from zine.i18n import _
from zine.application import add_link, url_for, render_response
from zine.models import Post, Tag, User, Comment, Page, ROLE_AUTHOR, \
    COMMENT_UNMODERATED
from zine.utils import dump_json, build_tag_uri, ClosingIterator
from zine.utils.uploads import get_filename, guess_mimetype
from zine.utils.validators import is_valid_email, is_valid_url, check
from zine.utils.xml import generate_rsd, dump_xml, AtomFeed
from zine.utils.http import redirect_to
from werkzeug.exceptions import NotFound, Forbidden


@cache.response(vary=('user',))
def do_index(request, page=1):
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
    data = Post.objects.get_list(page=page)
    if data.pop('probably_404'):
        raise NotFound()

    add_link('alternate', url_for('blog/atom_feed'), 'application/atom+xml',
             _('Recent Posts Feed'))
    return render_response('index.html', **data)


def do_archive(request, year=None, month=None, day=None, page=1):
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
    if not year:
        return render_response('archive.html', month_list=True,
                               **Post.objects.get_archive_summary())
    data = Post.objects.get_list(year, month, day, page=page)
    if data.pop('probably_404'):
        raise NotFound()

    feed_parameters = {}
    for name, value in [('year', year), ('month', month), ('day', day)]:
        if value is not None:
            feed_parameters[name] = value
    add_link('alternate', url_for('blog/atom_feed', **feed_parameters),
             'application/atom+xml', _('Recent Posts Feed'))
    return render_response('archive.html', year=year, month=month, day=day,
                           date=date(year, month or 1, day or 1),
                           month_list=False, **data)


def do_show_tag(request, slug, page=1):
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
    tag = Tag.objects.filter_by(slug=slug).first()
    if not tag:
        raise NotFound()

    data = Post.objects.get_list(tag=slug, page=page)
    if data.pop('probably_404'):
        raise NotFound()

    add_link('alternate', url_for('blog/atom_feed', tag=slug),
             'application/atom+xml', _('All posts tagged %s') % tag.name)
    return render_response('show_tag.html', tag=tag, **data)


def do_show_tag_cloud(request):
    """
    Show all posts tagged with a given tag slug.

    Available template variables:

        `tagcloud`:
            list of tag summaries that contain the size of the cloud
            item, the name of the tag and it's slug

    :Template name: ``tag_cloud.html``
    :URL endpoint: ``blog/tag_cloud``
    """
    return render_response('tag_cloud.html',
                           tag_cloud=Tag.objects.get_cloud())


def do_show_author(request, username, page=1):
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
    user = User.objects.filter((User.username == username) &
                               (User.role >= ROLE_AUTHOR)).first()
    if user is None:
        raise NotFound()
    data = Post.objects.get_list(author=user, page=page, per_page=30)
    if data.pop('probably_404'):
        raise NotFound()

    add_link('alternate', url_for('blog/atom_feed', author=username),
             'application/atom+xml', _('All posts written by %s') %
             user.display_name)

    return render_response('show_author.html', user=user, **data)


def do_authors(request):
    """
    Show a list of authors.

    Available template variables:

        `authors`:
            list of author objects to display.

    :Template name: ``authors.html``
    :URL endpoint: ``blog/authors``
    """
    return render_response('authors.html', authors=User.objects.authors().all())


@cache.response(vary=('user',))
@pingback.inject_header
def do_show_post(request, year, month, day, slug):
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
            to block the comment (setting the status and blocked_msg
            attributes) so that administrators have to approve them.

        `after-comment-saved`:
            executed right after comment was saved to the database. Can be
            used to send mail notifications and stuff like that.

    This view supports pingbacks via `zine.pingback.pingback_post`

    :Template name: ``show_post.html``
    :URL endpoint: ``blog/show_post``
    """
    post = Post.objects.get_by_timestamp_and_slug(year, month, day, slug)
    if post is None:
        raise NotFound()
    elif not post.can_access():
        raise Forbidden()

    # handle comment posting
    errors = []
    form = {'name': '', 'email': '', 'www': '', 'body': '', 'parent': ''}
    if request.method == 'POST' and post.comments_enabled:
        form['name'] = author = request.form.get('name')
        if not request.user.is_somebody:
            if not author:
                errors.append(_('You have to enter your name.'))
            elif len(author) > 100:
                errors.append(_('Your name is too long.'))
            form['email'] = email = request.form.get('email')
            if not (email and check(is_valid_email, email)):
                errors.append(_('You have to enter a valid mail address.'))
            elif len(email) > 250:
                errors.append(_('Your E-Mail address is too long.'))
            form['www'] = www = request.form.get('www')
            if www and not check(is_valid_url, www):
                errors.append(_('You have to enter a valid URL or omit the field.'))
            elif len(www) > 200:
                errors.append(_('The URL is too long.'))
        else:
            author = request.user
            email = www = None
        form['body'] = body = request.form.get('body')
        if not body or len(body) < 2:
            errors.append(_('Your comment is too short.'))
        elif len(body) > 6000:
            errors.append(_('Your comment is too long.'))
        form['parent'] = parent = request.form.get('parent')
        if parent:
            parent = Comment.objects.get(parent)
        else:
            parent = None

        #! allow plugins to do additional comment validation.
        #! the return value should be an iterable with error strings that
        #! are displayed below the comment form.  If an error ends up there
        #! the post is not saved.  Do not use this for antispam, that should
        #! accept the comment and just mark it as blocked.  For that have
        #! a look at the `before-comment-saved` event.
        for result in emit_event('before-comment-created', request, form):
            errors.extend(result or ())

        # if we don't have errors let's save it and emit an
        # `before-comment-saved` event so that plugins can do
        # block comments so that administrators have to approve it
        if not errors:
            ip = request.environ.get('REMOTE_ADDR') or '0.0.0.0'
            comment = Comment(post, author, body, email, www, parent,
                              submitter_ip=ip)

            #! use this event to block comments before they are saved.  This
            #! is useful for antispam and other ways of moderation.
            emit_event('before-comment-saved', request, comment)

            # Moderate Comment?  Now that the spam check any everything
            # went through the processing we explicitly set it to
            # unmodereated if the blog configuration demands that
            if not comment.blocked and comment.requires_moderation:
                comment.status = COMMENT_UNMODERATED
                comment.blocked_msg = _('Comment waiting for approval')

            db.commit()

            #! this is sent directly after the comment was saved.  Useful if
            #! you want to send mail notifications or whatever.
            emit_event('after-comment-saved', request, comment)

            # Still allow the user to see his comment
            if comment.blocked:
                comment.make_visible_for_request(request)

            return redirect_to(post)

    add_link('alternate', post.comment_feed_url, 'application/atom+xml',
             _('Comments Feed'))

    return render_response('show_post.html',
        post=post,
        form=form,
        errors=errors
    )


def do_service_rsd(request):
    """
    Serves and RSD definition (really simple discovery) so that blog frontends
    can query the apis that are available.

    :URL endpoint: ``blog/service_rsd``
    """
    return Response(generate_rsd(request.app), mimetype='application/xml')


def do_json_service(request, identifier):
    """
    Handle a JSON service request.
    """
    handler = request.app._services.get(identifier)
    if handler is None:
        raise NotFound()

    #! if this event returns a handler it is called instead of the default
    #! handler.  Useful to intercept certain requests.
    for callback in iter_listeners('before-json-service-called'):
        rv = callback(identifier, handler)
        if rv is not None:
            handler = rv
    result = handler(request)

    #! called right after json callback returned some data with the identifier
    #! of the request method and the result object.  Note that events *have*
    #! to return an object, even if it's just changed in place, otherwise the
    #! return value will be `null` (None).
    for callback in iter_listeners('after-json-service-called'):
        result = callback(identifier, result)
    return Response(dump_json(result), mimetype='text/javascript')


def do_xml_service(request, identifier):
    """
    Handle a XML service request.
    """
    handler = request.app._services.get(identifier)
    if handler is None:
        raise NotFound()

    #! if this event returns a handler it is called instead of the default
    #! handler.  Useful to intercept certain requests.
    for callback in iter_listeners('before-xml-service-called'):
        rv = callback(identifier, handler)
        if rv is not None:
            handler = rv
    result = handler(request)

    #! called right after xml callback returned some data with the identifier
    #! of the request method and the result object.  Note that events *have*
    #! to return an object, even if it's just changed in place, otherwise the
    #! return value will be None.
    for callback in iter_listeners('after-xml-service-called'):
        rv = callback(identifier, result)
        if rv is not None:
            result = rv
    return Response(dump_xml(result), mimetype='text/xml')


@cache.response(vary=('user',))
def do_atom_feed(request, author=None, year=None, month=None, day=None,
                 tag=None, post_slug=None):
    """
    Renders an atom feed requested.

    :URL endpoint: ``blog/atom_feed``
    """
    feed = AtomFeed(request.app.cfg['blog_title'], feed_url=request.url,
                    url=request.app.cfg['blog_url'],
                    subtitle=request.app.cfg['blog_tagline'])

    # if no post slug is given we filter the posts by the cretereons
    # provided and pass them to the feed builder
    if post_slug is None:
        for post in Post.objects.get_list(year, month, day, tag, author,
                                          per_page=10, as_list=True):
            links = [link.as_dict() for link in post.links]
            feed.add(post.title, unicode(post.body), content_type='html',
                     author=post.author.display_name, links=links,
                     url=url_for(post, _external=True), id=post.uid,
                     updated=post.last_update, published=post.pub_date)

    # otherwise we create a feed for all the comments of a post.
    else:
        post = Post.objects.get_by_timestamp_and_slug(year, month, day,
                                                      post_slug)
        if post is None:
            raise NotFound()
        elif not post.can_access():
            raise Forbidden()

        comment_num = 1
        for comment in post.comments:
            if not comment.visible:
                continue
            uid = build_tag_uri(request.app, comment.pub_date, 'comment',
                                comment.comment_id)
            title = _('Comment %(num)d on %(post)s') % {
                'num':  comment_num,
                'post': post.title
            }
            author = {'name': comment.author}
            if comment.www:
                author['uri'] = comment.www
            feed.add(title, unicode(comment.body), content_type='html',
                     author=author, url=url_for(comment, _external=True),
                     id=uid, updated=comment.pub_date)
            comment_num += 1

    return feed.get_response()


def do_get_upload(req, filename):
    filename = get_filename(filename)
    if not exists(filename):
        raise NotFound()
    guessed_type = guess_mimetype(filename)
    fp = file(filename, 'rb')
    def stream():
        while True:
            chunk = fp.read(1024 * 512)
            if not chunk:
                break
            yield chunk
    resp = Response(ClosingIterator(stream(), fp.close),
                    mimetype=guessed_type or 'text/plain')
    resp.headers['Cache-Control'] = 'public'
    resp.headers['Expires'] = asctime(gmtime(time() + 3600))
    return resp


@cache.response(vary=('user',))
def handle_user_pages(req):
    """Show a user page."""
    page_key = req.path.lstrip('/')

    page = Page.objects.filter_by(key=page_key).first()
    if page is None:
        # if the page does not exist, check if a page with a trailing slash
        # exists.  If it does, redirect to that page.  This is allows users
        # to emulate folders and to get relative links working.
        if not page_key.endswith('/'):
            real_page = Page.objects.filter_by(key=page_key + '/').first()
            if real_page is not None:
                return redirect_to(real_page)
        raise NotFound()
    cfg = get_application().cfg
    return render_response(
        'page_base.html',
        page=page,
        blog_title=get_application().cfg['blog_title'],
        show_title=cfg['show_page_title'],
        show_children=cfg['show_page_children']
    )
