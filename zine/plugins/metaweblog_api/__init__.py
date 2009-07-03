# -*- coding: utf-8 -*-
"""
    zine.plugins.metaweblog_api
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Adds support for the MetaWeblog API.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from zine.api import get_request, url_for, db
from zine.utils.xml import XMLRPC, Fault
from zine.models import User, Post, STATUS_PUBLISHED


def _login(username, password):
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        raise Fault(403, 'Bad login/pass combination.')

    # store the user on the request object so that the functions
    # inside Zine work on the request of this user.
    request = get_request()
    request.user = user
    return request

def authenticated(f):
    def proxy(some_id, username, password, *args):
        request = _login(username, password)
        return f(request, some_id, *args)
    proxy.__name__ = f.__name__
    return proxy


def dump_post(post):
    """Dumps a post into a structure for the MetaWeblog API."""
    text = post.body.to_html()
    if post.intro:
        text = u'<div class="intro">%s</div>%s' % (post.intro.to_html(), text)
    link = url_for(post, _external=True)
    return dict(
        pubDate=post.pub_date,
        dateCreated=post.pub_date,
        userid=post.user.id,
        page_id=post.id,

        title=post.title,
        link=link,
        permaLink=link,
        description=text,
        author=post.author.email,
        categories=[x.name for x in post.categories],

        postid=post.id,
        page_status=post.status == STATUS_PUBLISHED and "published" or "draft",
        excerpt=post.intro.to_html(),
        text_more=post.body.to_html(),
        mt_allow_comments=post.comments_enabled,
        mt_allow_pings=post.pings_enabled,
        wp_slug=post.slug,
        wp_password="",
        wp_author=post.body.display_name,
        wp_author_id=post.user.id,
        wp_author_display_name=post.body.display_name,
        date_created_gmt=post.pub_date,
        wp_page_template=post.extra.get('page_template'),
    )


def extract_text(struct):
    text = struct.get('description', '')
    excerpt = struct.get('post_excerpt')
    if excerpt:
        text = u'<intro>%s</intro>\n%s' % (excerpt, text)
    return text


def select_parser(app, struct):
    parser = struct.get('parser')
    if parser is None:
        return 'html'
    if parser not in app.parsers:
        raise Fault(500, 'unknown parser')
    return parser


@authenticated
def metaweblog_new_post(request, blog_id, struct, publish):
    text = extract_text(struct)
    post = Post(struct['title'], request.user, text,
                parser=select_parser(request.app, struct))
    link = url_for(post, _external=True)
    db.commit()
    return dump_post(post)


@authenticated
def metaweblog_edit_post(request, post_id, struct, publish):
    post = Post.query.get(post_id)
    if post is None:
        raise Fault(404, "No such post")
    post.parser = select_parser(request.app, struct)
    post.title = struct['title']
    post.text = extract_text(struct)
    db.commit()
    return dump_post(post)


@authenticated
def metaweblog_get_post(request, post_id):
    post = Post.query.get(post_id)
    if post is None:
        raise Fault(404, "No such post")
    if not post.can_read():
        raise Fault(403, "You don't have access to this post")
    return dump_post(post)


@authenticated
def metaweblog_get_recent_posts(request, blog_id, number_of_posts):
    number_of_posts = min(50, number_of_posts)
    # XXX: filter the ones you can't read (could this be the case?)
    return map(dump_post, Post.query.limit(number_of_posts).all())


def wp_get_users_blogs(username, password): # XXX security check missing
    request = _login(username, password)
    return [{'isAdmin': request.user.is_manager,
             'url': request.app.cfg["blog_url"],
             'blogid': 1,
             'blogName': request.app.cfg["blog_title"],
             'xmlrpc': url_for("services/WordPress", _external=True)}]


def wp_get_page(blog_id, page_id, username, password):
    request = _login(username, password)
    post = Post.query.get(page_id)
    if post is None:
        raise Fault(404, "No such post")
    if not post.can_read():
        raise Fault(403, "You don't have access to this post")
    return dump_post(post)



# MetaWeblog
service_metaweblog = XMLRPC()
service_metaweblog.register_functions([
    (metaweblog_new_post, 'metaWeblog.newPost'),
    (metaweblog_edit_post, 'metaWeblog.editPost'),
    (metaweblog_get_post, 'metaWeblog.getPost'),
    (metaweblog_get_recent_posts, 'metaWeblog.getRecentPosts'),
])


# WordPress
service_wp = XMLRPC()
service_wp.register_functions([
    (wp_get_users_blogs, 'wp.getUsersBlogs'),
    (wp_get_page, 'wp.getPage'),
])

# Missing functions from WordPress API:
#
#'wp.getPages', 'wp.newPage', 'wp.deletePage', 'wp.editPage', 'wp.getPageList'
#'wp.getAuthors', 'wp.getCategories', 'wp.getTags', 'wp.newCategory', 'wp.deleteCategory'
#'wp.suggestCategories', 'wp.uploadFile', 'wp.getCommentCount', 'wp.getPostStatusList'
#'wp.getPageStatusList', 'wp.getPageTemplates', 'wp.getOptions', 'wp.setOptions'
#'wp.getComment', 'wp.getComments', 'wp.deleteComment', 'wp.editComment'
#'wp.newComment', 'wp.getCommentStatusList'

def setup(app, plugin):
    app.add_api('MetaWeblog', False, service_metaweblog)
    app.add_api('WordPress', True, service_wp)
