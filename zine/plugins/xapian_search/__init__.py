# -*- coding: utf-8 -*-
"""
    zine.plugins.xapian_search
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides a full featured and fast search for Textpress using
    xapian as backend.

    The query can include wildcards (*), +/- indicators and operators like
    `AND`, `OR`, `AND NOT` or `NEAR`, as well as phrases ("this is a phrase").
    Additionally you can search for specific which kind of terms you want
    to look in, using one of the following prefixes: `tag:<tagname>`,
    `author:<username>` or `title:<title>`. Please consider reading the xapian
    documentation on queries for a full documentation.

    :copyright: 2008 by Christoph Hack.
    :license: GNU GPL.
"""
import xapian
from os.path import join, dirname
from time import mktime, strptime
from datetime import datetime
from zine.api import *
from zine.views.admin import render_admin_response
from zine.utils.admin import flash
from zine.utils.xxx import CSRFProtector
from zine.widgets import Widget
from zine.models import Post, ROLE_ADMIN

# TODO: add a indexing script for all posts

SEARCH_FLAGS = reduce(lambda a, b: a | b, [getattr(xapian.QueryParser, f) \
    for f in ('FLAG_PHRASE', 'FLAG_BOOLEAN', 'FLAG_LOVEHATE', 'FLAG_WILDCARD',
        'FLAG_SPELLING_CORRECTION')])

TEMPLATE_FILES = join(dirname(__file__), 'templates')


class QuickSearchWidget(Widget):
    """A simple widget with only one search box."""
    NAME = 'get_quicksearch'
    TEMPLATE = 'widgets/quicksearch.html'


class PostAuthDecider(xapian.MatchDecider):
    """Decides which posts should be visible by checking the ACL."""

    def __init__(self, user):
        self.user = user
        xapian.MatchDecider.__init__(self)

    def __call__(self, doc):
        # this function can be called for a extremely huge number of
        # documents, so we are going to use ducks here, instead of
        # querying the database every time
        duck = type('post_duck', (Post,), {
           'pub_date': datetime.fromtimestamp(float(doc.get_value(2))),
           'status': int(doc.get_value(3)),
           'author_id': int(doc.get_value(4)),
        })
        return Post.can_access.im_func(duck, user=self.user)


def configure(request):
    """This callback is called from the admin panel to configure the
    xapian database and the search behaviors."""
    cfg = request.app.cfg
    csrf_protector = CSRFProtector()
    if request.method == 'POST':
        csrf_protector.assert_safe()
        if 'save' in request.form:
            flash(_('Search settings changed successfully.'), 'configure')
            cfg.change_single('xapian_search/database_path',
                              request.form['database_path'])
            cfg.change_single('xapian_search/stem_lang',
                              request.form['stem_lang'])
        return redirect(url_for('admin/options'))
    return render_admin_response('admin/configure_xapian_search.html',
                                 'options.xapian_search',
                                 database_path=cfg['xapian_search/database_path'],
                                 stem_lang=cfg['xapian_search/stem_lang'],
                                 csrf_protector=csrf_protector)


def add_configure_link(request, navigation_bar):
    """This function adds a Search entry to the navigation bar of the
    administration menu."""
    if request.user.role < ROLE_ADMIN:
        return
    for link_id, url, title, children in navigation_bar:
        if link_id == 'options':
            children.insert(-3, ('xapian_search', url_for('xapian_search/config'),
                                 _('Search')))


def _get_database_path():
    """Return the path to the database."""
    app = get_application()
    return join(app.instance_folder, app.cfg['xapian_search/database_path'])


def _get_writable_db():
    """Open the database for writing."""
    cfg = get_application().cfg
    if not cfg['xapian_search/database_path']:
        return
    try:
        db = xapian.WritableDatabase(_get_database_path(),
                                     xapian.DB_CREATE_OR_OPEN)
        return db
    except xapian.DatabaseCreateError, e:
        flash(_(u'Search index update failed. Please check the path in ' \
                'the settings menu.'), type='error')


def index_post(post):
    """
    Add or update a post to the search index.
    """
    cfg = get_application().cfg
    db = _get_writable_db()
    if not db:
        return
    doc = xapian.Document()
    tg = xapian.TermGenerator()
    tg.set_database(db)
    tg.set_document(doc)
    tg.set_flags(tg.FLAG_SPELLING)
    if cfg['xapian_search/stem_lang']:
        try:
            stemmer = xapian.Stem(cfg['xapian_search/stem_lang'])
            tg.set_stemmer(stemmer)
        except xapian.InvalidArgumentError:
            flash(_(u'Invalid stemming language. Stemming is disabled. '\
                    'Please check your settings.'), type='error')
    tg.index_text(post.title, 5)
    tg.index_text(post.title, 5, 'T')
    tg.index_text(unicode(post.intro))
    tg.index_text(unicode(post.body))
    for tag in post.tags:
        doc.add_term(u'C%s' % tag.slug)
        tg.index_text(tag.name, 2, 'C')
    tg.index_text(post.author.display_name)
    doc.add_term(u'U%s' % post.author.username.lower())
    tg.index_text(post.author.display_name, 1, 'U')
    doc.add_value(0, 'post')
    doc.add_value(1, str(post.post_id))
    doc.add_value(2, str(mktime(post.pub_date.timetuple())))
    doc.add_value(3, str(post.status))
    doc.add_value(4, str(post.author_id))
    doc.add_term('P%d' % post.post_id)
    doc.add_term('Qpost')
    db.replace_document('P%d' % post.post_id, doc)


def delete_post(post):
    """Removes a post from the search index."""
    db = _get_writable_db()
    if not db:
        return
    db.delete_document('P%d' % post.post_id)


def search(request):
    """Query the database and display the results."""
    query = request.values.get('query', '').strip()
    if not query:
        return redirect(url_for('blog/index'))
    cfg = request.app.cfg
    try:
        db = xapian.Database(_get_database_path())
    except xapian.DatabaseOpeningError:
        # if the search database doesn't exist just display an empty
        # result page
        return render_response('search_results.html', posts=[],
                               query=query, pagination=None)
    enq = xapian.Enquire(db)
    qp = xapian.QueryParser()
    qp.set_database(db)
    if cfg['xapian_search/stem_lang']:
        try:
            stemmer = xapian.Stem(cfg['xapian_search/stem_lang'])
            qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
            qp.set_stemmer(stemmer)
        except xapian.InvalidArgumentError:
            pass
    qp.set_default_op(xapian.Query.OP_AND)
    qp.add_prefix('tag', 'C')
    qp.add_prefix('title', 'T')
    qp.add_prefix('author', 'U')
    try:
        qry = qp.parse_query(query, SEARCH_FLAGS)
    except xapian.QueryParserError:
        qry = xapian.Query()
    enq.set_query(qry)
    posts = []
    page = 1
    # TODO: add pagination
    mdecider = PostAuthDecider(request.user)
    for match in enq.get_mset(0, 10, None, mdecider):
        post = Post.query.get(match.get_document().get_value(1))
        if post:
            posts.append(post)
    data = {
        'spelling_correction': qp.get_corrected_query_string(),
        'query': query,
        'posts': posts,
        'pagination': None
    }
    return render_response('search_results.html', **data)


def setup(app, plugin):
    """Register the plugin in zine."""
    app.add_template_searchpath(TEMPLATE_FILES)
    app.add_widget(QuickSearchWidget)
    app.add_config_var('xapian_search/database_path', unicode,
                       'search.xapdb')
    app.add_config_var('xapian_search/stem_lang', unicode, 'en')
    app.connect_event('modify-admin-navigation-bar', add_configure_link)
    app.connect_event('after-post-saved', index_post)
    app.connect_event('before-post-deleted', delete_post)
    app.add_url_rule('/search', prefix='blog', endpoint='blog/search',
                     view=search)
    app.add_url_rule('/options/xapian', prefix='admin',
                     endpoint='xapian_search/config', view=configure)
