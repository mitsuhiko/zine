# -*- coding: utf-8 -*-
"""
    zine.importers.feed
    ~~~~~~~~~~~~~~~~~~~

    This importer can import web feeds.  Currently it is limited to ATOM
    plus optional Zine extensions.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from lxml import etree
from zine.application import get_application
from zine.i18n import _, lazy_gettext
from zine.importers import Importer, Blog, Tag, Category, Author, Post, Comment
from zine.forms import FeedImportForm
from zine.utils import log
from zine.utils.admin import flash
from zine.utils.dates import parse_iso8601
from zine.utils.xml import Namespace, to_text
from zine.utils.http import redirect_to
from zine.zxa import ZINE_NS, ATOM_NS, XML_NS


zine = Namespace(ZINE_NS)
atom = Namespace(ATOM_NS)
xml = Namespace(XML_NS)


def _get_text_content(elements):
    """Return the text content from the best element match."""
    if not elements:
        return u''
    for element in elements:
        if element.attrib.get('type') == 'text':
            return element.text or u''
    for element in elements:
        if element.attrib.get('type') == 'html':
            return to_text(element)
    return to_text(elements[0])


def _get_html_content(elements):
    """Returns the html content from the best element match or another
    content treated as html.  This is totally against the specification
    but this importer assumes that the text representation is unprocessed
    markup language from the blog.  This is most likely a dialect of HTML
    or a lightweight markup language in which case the importer only has
    to switch the parser afterwards.
    """
    if not elements:
        return u''
    for element in elements:
        if element.attrib.get('type') == 'html':
            return element.text
    return elements[0].text


def parse_feed(fd):
    tree = etree.parse(fd).getroot()
    if tree.tag == 'rss':
        parser_clas = RSSParser
    elif tree.tag == atom.feed:
        parser_class = AtomParser
    else:
        raise FeedImportError(_('Unknown feed uploaded.'))
    parser = parser_class(tree)
    parser.parse()
    return parser.blog


class Parser(object):

    def __init__(self, tree):
        self.app = get_application()
        self.tree = tree
        self.tags = []
        self.categories = []
        self.authors = []
        self.posts = []
        self.blog = None
        self.extensions = [extension(self.app, self, tree)
                           for extension in self.app.feed_importer_extensions]

    def find_tag(self, **critereon):
        return self._find_criteron(self.tags, critereon)

    def find_category(self, **critereon):
        return self._find_criteron(self.categories, critereon)

    def find_author(self, **critereon):
        return self._find_criteron(self.authors, critereon)

    def find_post(self, **critereon):
        return self._find_criteron(self.posts, critereon)

    def _find_criteron(self, sequence, d):
        if len(d) != 1:
            raise TypeError('one critereon expected')
        key, value = d.iteritems().next()
        for item in sequence:
            if getattr(item, key, None) == value:
                return item


class RSSParser(Parser):

    def __init__(self, tree):
        raise FeedImportError(_('Importing of RSS feeds is currently '
                                'not possible.'))


class AtomParser(Parser):

    def __init__(self, tree):
        Parser.__init__(self, tree)

        # use for the category fallback handling if no extension
        # takes over the handling.
        self._categories_by_term = {}

        # and the same for authors
        self._authors_by_username = {}
        self._authors_by_email = {}

    def parse(self):
        for entry in self.tree.findall(atom.entry):
            self.posts.append(self.parse_post(entry))

        self.blog = Blog(
            self.tree.findtext(atom.title),
            self.tree.findtext(atom.link),
            self.tree.findtext(atom.subtitle),
            self.tree.attrib.get(xml.lang, u'en'),
            self.tags,
            self.categories,
            self.posts,
            self.authors
        )
        self.blog.element = self.tree
        for extension in self.extensions:
            extension.handle_root(self.blog)

    def parse_post(self, entry):
        # parse the dates first.
        updated = parse_iso8601(entry.findtext(atom.updated))
        published = entry.findtext(atom.published)
        if published is not None:
            published = parse_iso8601(published)
        else:
            published = updated

        # figure out tags and categories by invoking the
        # callbacks on the extensions first.  If no extension
        # was able to figure out what to do with it, we treat it
        # as category.
        tags, categories = self.parse_categories(entry)

        link = entry.find(atom.link)
        if link is not None:
            link = link.attrib.get('href')

        post = Post(
            None,
            _get_text_content(entry.findall(atom.title)),
            link,
            published,
            self.parse_author(entry),
            # XXX: the Post is prefixing the intro before the actual
            # content.  This is the default Zine behavior and makes sense
            # for Zine.  However nearly every blog works differently and
            # treats summary completely different from content.  We should
            # think about that.
            None,
            _get_html_content(entry.findall(atom.content)),
            tags,
            categories,
            parser='html',
            updated=updated,
            uid=entry.findtext(atom.id)
        )
        post.element = entry

        # now parse the comments for the post
        self.parse_comments(post)

        for extension in self.extensions:
            extension.postprocess_post(post)

        return post

    def parse_author(self, entry):
        """Lookup the author for the given entry."""
        def _remember_author(author):
            if author.email is not None and \
               author.email not in self._authors_by_email:
                self._authors_by_email[author.email] = author
            if author.username is not None and \
               author.username not in self._authors_by_username:
                self._authors_by_username[author.username] = author

        author = entry.find(atom.author)
        email = author.findtext(atom.email)
        username = author.findtext(atom.name)

        for extension in self.extensions:
            rv = extension.lookup_author(author, entry, username, email)
            if rv is not None:
                _remember_author(rv)
                return rv

        if email is not None and email in self._authors_by_email:
            return self._authors_by_email[email]
        if username in self._authors_by_username:
            return self._authors_by_username[username]

        print (author.getchildren(), email, username)
        author = Author(username, email)
        _remember_author(author)
        self.authors.append(author)
        return author

    def parse_categories(self, entry):
        """Is passed an <entry> element and parses all <category>
        child elements.  Returns a tuple with ``(tags, categories)``.
        """
        def _remember_category(category, element):
            term = element.attrib['term']
            if term not in self._categories_by_term:
                self._categories_by_term[term] = category

        tags = []
        categories = []

        for category in entry.findall(atom.category):
            for extension in self.extensions:
                rv = extension.tag_or_category(category)
                if rv is not None:
                    if isinstance(rv, Tag):
                        tags.append(rv)
                    else:
                        categories.append(rv)
                        _remember_category(rv, category)
                    break
            else:
                rv = self._categories_by_term.get(category.attrib['term'])
                if rv is None:
                    rv = Category(category.attrib['term'],
                                  category.attrib.get('label'))
                    _remember_category(rv, category)
                    self.categories.append(rv)
                categories.append(rv)

        return tags, categories

    def parse_comments(self, post):
        """Parse the comments for the post."""
        for extension in self.extensions:
            rv = extension.parse_comments(post)
            if rv is not None:
                post.comments.extend(rv)
                self.comments.extend(rv)


class FeedImportError(Exception):
    """Raised if the system was unable to import the feed."""

    def __init__(self, message):
        Exception.__init__(self, message.encode('utf-8'))
        self.message = message


class FeedImporter(Importer):
    name = 'feed'
    title = lazy_gettext(u'Feed Importer')

    def configure(self, request):
        form = FeedImportForm()

        if request.method == 'POST' and form.validate(request.form):
            feed = request.files.get('feed')
            if not form.data['download_url']:
                try:
                    feed = urllib.urlopen(form.data['download_url'])
                except Exception, e:
                    error = _(u'Error downloading from URL: %s') % e
            elif not feed:
                return redirect_to('import/feed')

            try:
                blog = parse_feed(feed)
            except Exception, e:
                log.exception(_(u'Error parsing uploaded file'))
                flash(_(u'Error parsing feed: %s') % e, 'error')
            else:
                self.enqueue_dump(blog)
                flash(_('Added imported items to queue.'))
                return redirect_to('admin/import')

        return self.render_admin_page('admin/import_feed.html',
                                      form=form.as_widget())


class Extension(object):
    """Extensions are instanciated for each parsing process."""

    def __init__(self, app, parser, root):
        self.app = app
        self.parser = parser
        self.root = root

    def handle_root(self, blog):
        """Called after the whole feed was parsed into a blog object."""

    def postprocess_post(self, post):
        """Postprocess the post."""

    def tag_or_category(self, element):
        """Passed a <category> element for Atom feeds.  Has to return a
        category or tag object or `None` if it's not handled by this
        extension.

        Categories and tags have to be stored in `parser.categories` or
        `parser.tags` so that the category/tag is actually unique.  The
        extension also has to look there first for matching categories.
        """

    def lookup_author(self, author, entry, username, email):
        """Lookup the author for an element.  `author` is an element
        that points to the author relevant element for the feed.
        `entry` points to the whole entry element.

        Authors have to be stored in `parser.authors` to ensure they
        are unique.  Extensions have to look there first for matching
        author objects.  If an extension does not know how to handle
        the element `None` must be returned.
        """

    def parse_comments(self, post):
        """Parse the comments for the given post.  If the extension
        could locate comments for this post it has to return a list
        of those comments, otherwise return `None`.
        """


class ZEAExtension(Extension):

    def handle_root(self, blog):
        blog.configuration.update(self._parse_config(
            blog.element.find(zine.configuration)))

    def _parse_config(self, element):
        result = {}
        if element is not None:
            for element in element.findall(zine.item):
                result[element.attrib['key']] = element.text
        return result


extensions = [ZEAExtension]
