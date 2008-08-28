# -*- coding: utf-8 -*-
"""
    zine.importers.blogger
    ~~~~~~~~~~~~~~~~~~~~~~

    Implements an importer for Blogger.com using the GData blogger API.

    Uses Google's gdata library which is available under Apache license.

    Download: http://code.google.com/p/gdata-python-client/
    Quick guide: http://code.google.com/apis/blogger/developers_guide_python.html

    The process of performing the actions required is well documented
    elsewhere (eg above), but is well worth mentioning for completeness and so
    that anyone hacking on the importer can hit the ground running.

    The process is divided into three broad sections:

        1. Authentication
        2. Data retrieval
        3. Data dumping

    The zine importer framework takes over once the dump is "enqueued"

    Authentication
    --------------

    The importer uses Google's gdata API, and that has a few choices for
    authentication. Generally, the safest method for a web application is the
    proxy authentication method (versus client login methods).

    The proxy auth provides a google-hosted URL which can be visited to log
    in, and which will redirect back to the page of choice, with an appended
    query parameter called "token".

    The value of this parameter is an authentication token that is valid for a
    single use. This single-use token can be upgraded to a session token using
    the client API. Once upgraded to a session token, it can be stored and
    reused by the client.

    This token is stored in the configuration system.

    Data Retrieval
    --------------

    This essentially uses the GData API to retrieve information about the
    following:

        * Blogs
        * Authors
        * Posts
        * Comments
        * Categories (called labels in Zine)

    The blogger client uses atom feeds to retrieve the data. Each component
    can be accessed by a unique feed.

    For a list of blogs:

        GET /feeds/default/blogs

    For a list of posts for a blog:

        GET /feeds/<blog_id>/posts/default

    For a list of comments for a post:

        GET /feeds/<blog_id>/<post_id>/comments/full

    In each case, the blog_id and post_id parameters are calculated as the
    last component in the self link of an entry. There is no nicer way.

    Data Dumping
    ------------

    This is the process by which the blogger data is dumped into the Zine
    import system. Essentially it involves creating a zine.importers.Blog
    instance with the necessary data. Instances of zine.importers.Post,
    testpress.importers.Author, zine.importers.Comment and
    zine.importers.Label are created.

    Construction of these objects is a simple matter of passing the correct
    data into the constructors.

    Once the blog object is created, it is enqueued into the import system
    (which then allows the user to select which posts/authors/metadata they
    would like imported. At this point Zine takes over.


    :copyright: Copyright 2008 by Ali Afshar, Armin Ronacher.
    :license: GNU GPL.
"""
from datetime import datetime

# Do a conditional import on this
try:
    from gdata import service
except ImportError:
    service = None

from zine.application import redirect, url_for
from zine.importers import Importer, Blog, Label, Author, Post, Comment
from zine.api import _
from zine.utils.admin import flash
from zine.utils.dates import parse_iso8601


GDATA_DOWNLOAD_URL = 'http://code.google.com/p/gdata-python-client/'
GDATA_DOWNLOAD_LINK = ('<a href="%s">%s</a>' % (GDATA_DOWNLOAD_URL,
                                                 GDATA_DOWNLOAD_URL))


def _create_blogger_service():
    blogger_service = service.GDataService()
    blogger_service.source = 'Zine_BloggerImporter-1.0'
    blogger_service.service = 'blogger'
    blogger_service.server = 'www.blogger.com'
    return blogger_service


def get_blog_selflink(entry):
    """Get the link object to the atom entry."""
    self_link = entry.GetSelfLink()
    return self_link


def get_blog_id_from_selflink(self_link):
    """Get the ID from a link object"""
    # This is how they do it in the example, there seems no nice way
    if self_link:
        id = self_link.href.split('/')[-1]
    else:
        id = None
    return id


def get_blog_id(entry):
    """Get the id of an entry."""
    return get_blog_id_from_selflink(get_blog_selflink(entry))


def get_auth_sub_url(blogger_service):
    """
    Create an authsub URL.

    The link points somewhere that will redirect us back to the next parameter
    """
    next = url_for('import/blogger', _external=True)
    return blogger_service.GenerateAuthSubURL(
        next=next, scope='http://www.blogger.com/feeds', secure=False,
        session=True)


def get_user_blogs(blogger_service):
    """Return a list of blogs for the logged in blogger_service."""
    query = service.Query()
    query.feed = '/feeds/default/blogs'
    feed = blogger_service.Get(query.ToUri())
    return feed.entry


def get_posts_feed(blogger_service, blog_id):
    """Get the feed of posts for a blog."""
    q = service.Query()
    q.feed = '/feeds/' + blog_id + '/posts/default'
    q.max_results = 10000000
    feed = blogger_service.Get(q.ToUri())
    return feed


def get_published_posts(feed):
    """Get a list of posts that are not drafts."""
    return [p for p in feed.entry if not is_post_draft(p)]


def get_comments(blogger_service, blog_id, post_id):
    """Get the feed of comments for a particular post in a particular blog."""
    url = '/feeds/%s/%s/comments/default' % (blog_id, post_id)
    q = service.Query()
    q.feed = url
    q.max_results = 100000
    f = blogger_service.Get(q.ToUri())
    return f


def get_post_author(entry):
    """Return a tuple of name, email for the entry"""
    author = entry.author[0] # Is a list, and I think we just want the first
    if author.email is None:
        email = None
    else:
        email = author.email.text
    return author.name.text, email


def is_post_draft(entry):
    """Is a post a draft"""
    return entry.control and entry.control.draft


class BlogDumper(object):
    """
    Something to dump a blogger blog into the dump format. And store the state
    during the procedure.
    """
    def __init__(self, blogger_service, blog_id):
        self.blogger_service = blogger_service
        self.blog_id = blog_id
        self.authors = {}
        self.labels = {}
        self.comments = {}

    def create_dumpable_blog(self, callback):
        yield '<dl>'
        yield '<dt>Fetching list of blogs</dt>'
        feed = get_posts_feed(self.blogger_service, self.blog_id)
        yield '<dd>Done</dd>'
        posts = []
        published = get_published_posts(feed)
        nposts = len(published)
        yield '<dt>Fetching individual posts: (total %s)</dt>' % nposts
        yield '<dd id="fetchperc"></dd>'
        for i, e in enumerate(published):
            yield ('<script>$("#fetchperc").html("%s/%s")</script>'
                % (i + 1, nposts))
            post = self.create_dumpable_post(e)
            posts.append(post)
        yield '<script>$("#fetchperc").html("Done")</script>'
        yield '<dt>Writing complete blog</dt>'

        b = Blog(
            title = feed.title.text,
            link=feed.GetSelfLink().href,
            description = feed.title.text,
            posts = posts,
            authors=self.authors.values(),
            labels = self.labels.values(),
        )
        callback(b)
        yield '<dd>Done</dd>'

    def create_dumpable_post(self, entry):
        author = self.create_dumpable_author(entry)
        labels = self.create_dumpable_labels(entry)
        post_id = get_blog_id(entry)
        comments = self.create_dumpable_comments(entry)

        if entry.summary:
            summary = entry.summary.text.decode('utf-8')
        else:
            summary = None

        return Post(
            None,
            entry.title.text.decode('utf-8'),
            entry.GetSelfLink().href,
            parse_iso8601(entry.published.text),
            author,
            summary,
            entry.content.text.decode('utf-8'),
            labels,
            comments,
        )

    def create_dumpable_author(self, entry):
        name, email = get_post_author(entry)
        author = self.authors.get((name, email))
        if author is None:
            author = self.authors[(name, email)] = Author(len(self.authors) + 1,
                                                          name, email)
        return author

    def create_dumpable_labels(self, entry):
        post_labels = []
        for cat in entry.category:
            name = cat.term
            label = self.labels.get(name)
            if label is None:
                label = self.labels[name] = Label(name, name)
            post_labels.append(label)
        return post_labels

    def create_dumpable_comments(self, entry):
        post_id = get_blog_id(entry)
        comments_feed = get_comments(self.blogger_service, self.blog_id, post_id)
        comments = []
        for comment in comments_feed.entry:
            body = comment.content.text.decode('utf-8')
            c = Comment(
                comment.author[0].name.text,
                None,
                None,
                None,
                pub_date=parse_iso8601(comment.published.text),
                body=body,
            )
            comments.append(c)
        return comments


class BloggerImporter(Importer):
    """An importer for blogger.com blogs"""

    name = 'blogger'
    title = 'Blogger'

    def configure(self, request):
        if service is None:
            # gdata is not installed, show an error and refuse to do anything
            flash(_('GData python client library is not installed, '
                  'and is required for functioning of the Blogger importer.'
                  '<p>Please visit: %(download_link)s</p>') %
                    {'download_link': GDATA_DOWNLOAD_LINK},
                  type='error')
            return redirect(url_for('admin/import'))

        auth_token = self.app.cfg['blogger_auth_token']
        blogger_service = _create_blogger_service()

        if not auth_token:
            temp_auth_token = request.args.get('token')
            if temp_auth_token is not None:
                # We just got the reply back from google
                blogger_service.auth_token = temp_auth_token
                blogger_service.UpgradeToSessionToken()
                self.app.cfg.change_single('blogger_auth_token',
                                           blogger_service.auth_token)
                return redirect(url_for('import/blogger'))
            # We should display the "log in to google"
            proxy_auth_url=get_auth_sub_url(blogger_service)
            return self.render_admin_page('admin/import_blogger.html',
                proxy_auth_url=proxy_auth_url,
                has_auth=False,
            )

        # We are logged in and can decide what to do:
        # 1. Show the list of blogs
        # 2. Receive the post request and act
        # 3. log out of google
        blogger_service.auth_token = auth_token
        if request.method == 'GET':
            blogs=get_user_blogs(blogger_service)
            return self.render_admin_page('admin/import_blogger.html',
                available_blogs=blogs,
                has_auth=True,
                get_blog_id=get_blog_id,
            )
        if u'logout' in request.form:
            # Log out of google
            blogger_service.RevokeAuthSubToken()
            self.app.cfg.change_single('blogger_auth_token', '')
            return redirect(url_for('import/blogger'))
        else:
            # Perform the import
            blog_id = request.form.get('blog_id')
            blog_dumper = BlogDumper(blogger_service, blog_id)
            live_log = blog_dumper.create_dumpable_blog(self.enqueue_dump)
            return self.render_admin_page(
                'admin/blogger_perform_import.html',
                live_log=live_log,
                _stream=True,
            )
