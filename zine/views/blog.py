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
from zine.database import db
from zine.application import add_link, url_for, render_response, emit_event, \
     iter_listeners, Response, get_application
from zine.models import Post, Category, User, Comment, ROLE_AUTHOR, \
     COMMENT_UNMODERATED
from zine.utils import dump_json, build_tag_uri, ClosingIterator, log
from zine.utils.uploads import get_filename, guess_mimetype
from zine.utils.validators import is_valid_email, is_valid_url, check
from zine.utils.xml import generate_rsd, dump_xml, AtomFeed
from zine.utils.http import redirect_to, redirect
from zine.utils.redirects import lookup_redirect
from zine.forms import NewCommentForm
from werkzeug.exceptions import NotFound, Forbidden


@cache.response(vary=('user',))
def index(req, page=1):
    """Render the most recent posts.

    Available template variables:

        `posts`:
            a list of post objects we want to display

        `pagination`:
            a pagination object to render a pagination

    :Template name: ``index.html``
    :URL endpoint: ``blog/index``
    """
    data = Post.query.published().for_index().get_list(page=page)

    add_link('alternate', url_for('blog/atom_feed'), 'application/atom+xml',
             _(u'Recent Posts Feed'))
    return render_response('index.html', **data)


def archive(req, year=None, month=None, day=None, page=1):
    """Render the monthly archives.

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
                               **Post.query.published().for_index()
                                     .get_archive_summary())

    url_args = dict(year=year, month=month, day=day)
    data = Post.query.published().for_index().date_filter(year, month, day) \
                     .get_list(page=page, endpoint='blog/archive',
                               url_args=url_args)

    add_link('alternate', url_for('blog/atom_feed', **url_args),
             'application/atom+xml', _(u'Recent Posts Feed'))

    return render_response('archive.html', year=year, month=month, day=day,
                           date=date(year, month or 1, day or 1),
                           month_list=False, **data)


def show_category(req, slug, page=1):
    """Show all posts categoryged with a given category slug.

    Available template variables:

        `posts`:
            a list of post objects we want to display

        `pagination`:
            a pagination object to render a pagination

        `category`
            the category object for this page.

    :Template name: ``show_category.html``
    :URL endpoint: ``blog/show_category``
    """
    category = Category.query.published().filter_by(slug=slug).first(True)
    data = Post.query.published().get_list(category=category, page=page,
                                           endpoint='blog/show_category',
                                           url_args=dict(slug=slug))

    add_link('alternate', url_for('blog/atom_feed', category=slug),
             'application/atom+xml', _(u'All posts categoryged %s') % category.name)
    return render_response('show_category.html', category=category, **data)


def show_author(req, username, page=1):
    """Show the user profile of an author / editor or administrator.

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
    user = User.query.filter((User.username == username) &
                             (User.role >= ROLE_AUTHOR)).first(True)
    data = Post.query.published().filter_by(author=user) \
               .get_list(page=page, per_page=30)

    add_link('alternate', url_for('blog/atom_feed', author=username),
             'application/atom+xml', _(u'All posts written by %s') %
             user.display_name)

    return render_response('show_author.html', user=user, **data)


def authors(req):
    """Show a list of authors.

    Available template variables:

        `authors`:
            list of author objects to display.

    :Template name: ``authors.html``
    :URL endpoint: ``blog/authors``
    """
    return render_response('authors.html', authors=User.query.authors().all())


@cache.response(vary=('user',))
@pingback.inject_header
def show_entry(req, post, comment_form):
    """Show as post and give users the possibility to comment to this
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

    :Template name: ``show_entry.html``
    :URL endpoint: ``blog/show_post``
    """
    response = comment_form.create_if_valid(req)
    if response is not None:
        return response

    return render_response('show_entry.html',
        entry=post,
        form=comment_form.as_widget()
    )


def show_page(req, post, comment_form):
    """Shows a post that is a page."""
    response = comment_form.create_if_valid(req)
    if response is not None:
        return response

    cfg = req.app.cfg
    return render_response(['pages/%s.html' % post.slug.strip('/'),
                            post.extra.get('page_template'), 'page.html'],
        page=post,
        form=comment_form.as_widget(),
        show_title=cfg['show_page_title']
    )


def service_rsd(req):
    """Serves and RSD definition (really simple discovery) so that blog
    frontends can query the apis that are available.

    :URL endpoint: ``blog/service_rsd``
    """
    return Response(generate_rsd(req.app), mimetype='application/xml')


def json_service(req, identifier):
    """Handle a JSON service req."""
    handler = req.app._services.get(identifier)
    if handler is None:
        raise NotFound()

    #! if this event returns a handler it is called instead of the default
    #! handler.  Useful to intercept certain requests.
    for callback in iter_listeners('before-json-service-called'):
        rv = callback(identifier, handler)
        if rv is not None:
            handler = rv
    result = handler(req)

    #! called right after json callback returned some data with the identifier
    #! of the req method and the result object.  Note that events *have*
    #! to return an object, even if it's just changed in place, otherwise the
    #! return value will be `null` (None).
    for callback in iter_listeners('after-json-service-called'):
        result = callback(identifier, result)
    return Response(dump_json(result), mimetype='text/javascript')


def xml_service(req, identifier):
    """Handle a XML service req."""
    handler = req.app._services.get(identifier)
    if handler is None:
        raise NotFound()

    #! if this event returns a handler it is called instead of the default
    #! handler.  Useful to intercept certain requests.
    for callback in iter_listeners('before-xml-service-called'):
        rv = callback(identifier, handler)
        if rv is not None:
            handler = rv
    result = handler(req)

    #! called right after xml callback returned some data with the identifier
    #! of the req method and the result object.  Note that events *have*
    #! to return an object, even if it's just changed in place, otherwise the
    #! return value will be None.
    for callback in iter_listeners('after-xml-service-called'):
        rv = callback(identifier, result)
        if rv is not None:
            result = rv
    return Response(dump_xml(result), mimetype='text/xml')


@cache.response(vary=('user',))
def atom_feed(req, author=None, year=None, month=None, day=None,
              category=None, post=None):
    """Renders an atom feed requested.

    :URL endpoint: ``blog/atom_feed``
    """
    feed = AtomFeed(req.app.cfg['blog_title'], feed_url=req.url,
                    url=req.app.cfg['blog_url'],
                    subtitle=req.app.cfg['blog_tagline'])

    # the feed only contains published items
    query = Post.query.published()

    # feed for a category
    if category is not None:
        category = Category.query.filter_by(slug=category).first(True)
        query = query.filter(Post.categories.contains(category))

    # feed for an author
    if author is not None:
        author = Category.query.filter_by(username=author).first(True)
        query = query.filter(Post.author == author)

    # feed for dates
    if year is not None:
        query = query.for_index().date_filter(year, month, day)

    # if no post slug is given we filter the posts by the cretereons
    # provided and pass them to the feed builder.  This will only return
    # a feed for posts with a content type listed in `index_content_types`
    if post is None:
        for post in query.order_by(Post.pub_date.desc()).limit(15).all():
            links = [link.as_dict() for link in post.links]
            feed.add(post.title, unicode(post.body), content_type='html',
                     author=post.author.display_name, links=links,
                     url=url_for(post, _external=True), id=post.uid,
                     updated=post.last_update, published=post.pub_date)

    # otherwise we create a feed for all the comments of a post.
    # the function is called this way by `dispatch_content_type`.
    else:
        comment_num = 1
        for comment in post.comments:
            if not comment.visible:
                continue
            uid = build_tag_uri(req.app, comment.pub_date, 'comment',
                                comment.id)
            title = _(u'Comment %(num)d on %(post)s') % {
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


def get_upload(req, filename):
    """Stream an uploaded file to the user.  XXX: put something into werkzeug
    that can do that similar to the shared data middleware and make it more
    flexible.
    """
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
def dispatch_content_type(req):
    """Show the post for a specific content type."""
    slug = req.path[1:]

    # feed for the post
    if slug.endswith('/feed.atom'):
        slug = slug[:-10]
        want_feed = True
    else:
        want_feed = False

    post = Post.query.filter_by(slug=slug).first()

    if post is None:
        # if the post does not exist, check if a post with a trailing slash
        # exists.  If it does, redirect to that post.  This is allows users
        # to emulate folders and to get relative links working.
        if not slug.endswith('/'):
            real_post = Post.query.filter_by(slug=slug + '/').first()
            if real_post is None:
                raise NotFound()
            # if we want the feed, we don't want a redirect
            elif want_feed:
                post = real_post
            else:
                return redirect_to(real_post)
        else:
            raise NotFound()

    # make sure the current user can access that page.
    if not post.can_access():
        raise Forbidden()

    # feed requested?  jump to the feed page
    if want_feed:
        return atom_feed(req, post=post)

    # create the comment form
    form = NewCommentForm(post, req.user)
    if post.comments_enabled or post.comments:
        add_link('alternate', post.comment_feed_url, 'application/atom+xml',
                 _(u'Comments Feed'))

    # now dispatch to the correct view
    handler = req.app.content_type_handlers.get(post.content_type)
    if handler is None:
        log.warn('No handler for the content type %r found.' % post.content_type)
        raise NotFound()

    return handler(req, post, form)


def handle_redirect(req):
    """Handles redirects from the redirect table."""
    new_url = lookup_redirect(req.path)
    if new_url is not None:
        return redirect(new_url, 301)
