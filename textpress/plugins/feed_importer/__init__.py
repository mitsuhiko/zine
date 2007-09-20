# -*- coding: utf-8 -*-
"""
    textpress.plugins.feed_importer
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Import blogs, as feeds into TextPress.

    Currently supports RSS and ATOM, and some degree of comments importing.
    Issues such as non-full feeds have not been addressed.

    :copyright: 2007 by Ali Afshar.
    :license: GNU GPL
"""
from time import mktime
from os.path import join, dirname
from datetime import datetime

from textpress.api import *
from textpress.utils import CSRFProtector
from textpress.views.admin import render_admin_response, flash
from textpress.models import ROLE_ADMIN, Post, User, Comment
from textpress.fragment import DataNode
from textpress.views.admin import render_admin_response, flash
from textpress.database import db
from textpress._ext import beautifulsoup as bt

# Check if feedparser is installed
try:
    import feedparser
    has_feedparser = True
except ImportError:
    has_feedparser = False

#TODO: go into maintenance mode

#: Location of templates directory.
TEMPLATES = join(dirname(__file__), 'templates')

#: URL to show people when feedparser is not installed.
FEEDPARSER_URL = 'http://feedparser.org/'


def create_datetime(t):
    """
    Create a datetime from a time tuple.
    """
    # There is probably a better way to do this
    return datetime.fromtimestamp(mktime(t))


def beautify_html(html):
    """
    Use beautiful soup to make the html look nice.

    (We have it, so why not use it?)
    """
    soup = bt.BeautifulSoup(html)
    return soup.prettify()


class FeedImporter(object):
    """
    An importer of a given feed.

    This is just a bag of functions that imports a feed and comments.
    """

    def __init__(self, url):
        """
        Create and a feed importer.
        """
        self.url = url

    def import_feed(self):
        """
        Import a feed into TextPress.
        """
        db.begin()
        try:
            self._import_posts_feed()
            db.commit()
            return True
        except:
            db.rollback()
            raise
            return False

    def _import_posts_feed(self):
        """
        Import posts from a feed into the TextPress database.
        """
        d = feedparser.parse(self.url)
        for entry in d['entries']:
            title = entry.title
            last_update = create_datetime(entry.updated_parsed)
            if 'published' in entry:
                pub_date = create_datetime(entry.published_parsed)
            else:
                pub_date = last_update
            if 'summary' in entry:
                intro = entry['summary']
            else:
                intro = ''
            if 'content' in entry:
                body = beautify_html(entry.content[0].value)
            else:
                body = '<a href="%s">%s</a>' % (entry.link, title)

            p = Post(
                title=title,
                author=User.objects.get_by(email=u'aafshar@gmail.com'),
                body=body,
                intro=intro,
                pub_date=pub_date,
                last_update=last_update,
                parser='default',
            )
            db.save(p)
            comments_url = self._get_comments_feed_url(entry)
            self._import_comment_feed(p, comments_url)

    def _import_comment_feed(self, post, comment_url):
        """
        Import the feed of comments
        """
        d = feedparser.parse(comment_url)
        for entry in d['entries']:
            body = entry.content[0].value
            author = entry.author
            if 'email' in entry.author_detail:
                email = entry.author_detail.email
            else:
                email = None
            www = None
            pub_date = create_datetime(entry.published_parsed)
            c = Comment(
                post=post,
                author=author,
                email=email,
                www=www,
                body=body,
                parent=None,
                pub_date=pub_date,
                parser='default'
            )
            db.save(c)

    def _get_comments_feed_url(self, entry):
        """
        Get the comment feed url from an entry.
        """
        if 'comments' in entry:
            # This doesn't actually work in any way, since the link is an html
            # page, and pretty much useless.
            return entry.comments
        else:
            for link in entry.links:
                if (link.rel == u'replies' and
                    link.type == u'application/atom+xml'):
                    return link.href


def import_feed(url):
    """
    Import a feed.
    """
    importer = FeedImporter(url)
    return importer.import_feed()


@require_role(ROLE_ADMIN)
def show_config(req):
    """
    Request handler that provides an admin page to import a feed.
    """
    csrf_protector = CSRFProtector()

    if req.form.get('apply'):
        csrf_protector.assert_safe()
        url = req.form.get('feedurl')
        if import_feed(url):
            flash(_('Feed at %(feed_url)s imported successfully.' %
                        {'feed_url': url}),
                  'configure')
        else:
            flash(_('There was an error importing the feed.'), 'error')
        redirect(url_for('feed_importer/config'))

    return render_admin_response('admin/feed_importer.html',
                                 'options.feed_importer',
        csrf_protector=csrf_protector,
    )


def add_feed_import_link(req, navigation_bar):
    """
    Add a link for the importer on the admin panel.
    """
    if req.user.role >= ROLE_ADMIN:
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                children.insert(-2, ('feed_importer_support',
                                     url_for('feed_importer/config'),
                                     'Feed Importer'))


def show_error(req, context):
    """
    This is only connected to the admin response rendering if
    feedparser is not available.
    """
    flash(_('<strong>Feed Importing support is not active!</strong> '
            'the %(feedparser)s library is not installed.') % {
        'feedparser': u'<a href="%s">Feedparser</a>' % FEEDPARSER_URL
    }, 'error')


def setup(app, plugin):
    if has_feedparser:
        app.connect_event('modify-admin-navigation-bar', add_feed_import_link)
        app.add_url_rule('/admin/options/feed_importer',
                         endpoint='feed_importer/config')
        app.add_view('feed_importer/config', show_config)
        app.add_template_searchpath(TEMPLATES)
    else:
        app.connect_event('before-admin-response-rendered', show_error)

