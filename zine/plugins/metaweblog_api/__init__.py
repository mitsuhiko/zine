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
from zine.models import User, Post


def authenticated(f):
    def proxy(blog_id, username, password, *args):
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            raise Fault(403, 'Bad login/pass combination.')

        # store the user on the request object so that the functions
        # inside Zine work on the request of this user.
        request = get_request()
        request.user = user
        return f(request, *args)
    proxy.__name__ = f.__name__
    return proxy


def dump_post(post):
    """Dumps a post into a structure for the MetaWeblog API."""
    text = post.body.to_html()
    if post.intro:
        text = u'<div class="intro">%s</div>%s' % (post.intro.to_html(), text)

    return dict(
        pubDate=post.pub_date,
        title=post.title,
        link=url_for(post, _external=True),
        description=text,
        author=post.author.email,
        categories=sorted(set([x.name for x in post.tags] +
                              [x.name for x in post.categories]),
                          key=lambda x: x.lower())
    )


@authenticated
def metaweblog_new_post(request, struct, publish):
    text = struct.get('text', '')
    excerpt = struct.get('post_excerpt')
    if excerpt:
        text = u'<intro>%s</intro>\n%s' % (excerpt, text)
    post = Post(struct['title'], request.user, text, parser='zeml')
    link = url_for(post, _external=True)
    db.commit()

    return dump_post(post)


@authenticated
def metaweblog_edit_post(request, struct, publish):
    pass


@authenticated
def metaweblog_get_post(request, struct, publish):
    pass


@authenticated
def metaweblog_get_recent_posts(request, number_of_posts):
    number_of_posts = min(50, number_of_posts)
    return map(dump_post, Post.query.limit(number_of_posts).all())


service = XMLRPC()
service.register_function(metaweblog_new_post, 'metaWeblog.newPost')
service.register_function(metaweblog_edit_post, 'metaWeblog.editPost')
service.register_function(metaweblog_get_post, 'metaWeblog.getPost')
service.register_function(metaweblog_get_recent_posts, 'metaWeblog.getRecentPosts')


def setup(app, plugin):
    app.add_api('MetaWeblog', True, service)
