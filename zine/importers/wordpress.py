# -*- coding: utf-8 -*-
"""
    zine.importers.wordpress
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Implements an importer for WordPress extended RSS feeds.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD
"""
import re
import urllib
from time import strptime
from datetime import datetime
from lxml import etree
from zine.forms import WordPressImportForm
from zine.importers import Importer, Blog, Tag, Category, Author, Post, Comment
from zine.i18n import lazy_gettext, _
from zine.utils import log
from zine.utils.validators import is_valid_url
from zine.utils.admin import flash
from zine.utils.xml import Namespace, html_entities, escape
from zine.utils.http import redirect_to
from zine.models import COMMENT_UNMODERATED, COMMENT_MODERATED, \
     STATUS_DRAFT, STATUS_PUBLISHED

CONTENT = Namespace('http://purl.org/rss/1.0/modules/content/')
DC_METADATA = Namespace('http://purl.org/dc/elements/1.1/')
WORDPRESS = Namespace('http://wordpress.org/export/1.0/')


_xml_decl_re = re.compile(r'<\?xml.*?\?>(?s)')
_meta_value_re = re.compile(r'(<wp:postmeta>.*?<wp:meta_value>)(.*?)'
                            r'(</wp:meta_value>.*?</wp:postmeta>)(?s)')
_comment_re = re.compile(r'(<wp:comment>.*?<wp:comment_content>)(.*?)'
                         r'(</wp:comment_content>.*?</wp:comment>)(?s)')


def parse_broken_wxr(fd):
    """This method reads from a file descriptor and parses a WXR file as
    created by current WordPress versions.  This method also injects a
    custom DTD to not bark on HTML entities and fixes some problems with
    regular expressions before parsing.  It's not my fault, wordpress is
    that crazy :-/
    """
    # fix one: add inline doctype that defines the HTML entities so that
    # the parser doesn't bark on them, wordpress adds such entities to some
    # sections from time to time
    inline_doctype = '<!DOCTYPE wordpress [ %s ]>' % ' '.join(
        '<!ENTITY %s "&#%d;">' % (name, codepoint)
        for name, codepoint in html_entities.iteritems()
    )

    # fix two: wordpress 2.6 uses "excerpt:encoded" where excerpt is an
    # undeclared namespace.  What they did makes no sense whatsoever but
    # who cares.  We're not treating that element anyways but the XML
    # parser freaks out.  To fix that problem we're wrapping the whole
    # thing in another root element
    extra = '<wxrfix xmlns:excerpt="ignore:me">'

    code = fd.read()
    xml_decl = _xml_decl_re.search(code)
    if xml_decl is not None:
        code = code[:xml_decl.end()] + inline_doctype + extra + \
               code[xml_decl.end():]
    else:
        code = inline_doctype + extra + code

    # fix three: find comment sections and escape them.  Especially trackbacks
    # tent to break the XML structure.  same applies to wp:meta_value stuff.
    # this is especially necessary for older wordpress dumps, 2.7 fixes some
    # of these problems.
    def escape_if_good_idea(match):
        before, content, after = match.groups()
        if not content.lstrip().startswith('<![CDATA['):
            content = escape(content)
        return before + content + after
    code = _meta_value_re.sub(escape_if_good_idea, code)
    code = _comment_re.sub(escape_if_good_idea, code)
    code += '</wxrfix>'

    return etree.fromstring(code).find('rss').find('channel')


def parse_wordpress_date(value):
    """Parse a wordpress date or return `None` if not possible."""
    try:
        return datetime(*strptime(value, '%Y-%m-%d %H:%M:%S')[:7])
    except:
        pass


def parse_feed(fd):
    """Parse an extended WordPress RSS feed into a structure the general
    importer system can handle.  The return value is a `Blog` object.
    """
    tree = parse_broken_wxr(fd)

    authors = {}
    def get_author(name):
        if name:
            author = authors.get(name)
            if author is None:
                author = authors[name] = Author(name, None, id=len(authors) + 1)
            return author

    tags = {}
    for item in tree.findall(WORDPRESS.tag):
        tag = Tag(item.findtext(WORDPRESS.tag_slug),
                  item.findtext(WORDPRESS.tag_name))
        tags[tag.name] = tag

    categories = {}
    for item in tree.findall(WORDPRESS.category):
        category = Category(item.findtext(WORDPRESS.category_nicename),
                            item.findtext(WORDPRESS.cat_name))
        categories[category.name] = category

    posts = []

    for item in tree.findall('item'):
        status = {
            'draft':            STATUS_DRAFT
        }.get(item.findtext(WORDPRESS.status), STATUS_PUBLISHED)
        post_name = item.findtext(WORDPRESS.post_name)
        pub_date = parse_wordpress_date(item.findtext(WORDPRESS.post_date_gmt))
        slug = None

        if pub_date is None or post_name is None:
            status = STATUS_DRAFT
        if status == STATUS_PUBLISHED:
            slug = pub_date.strftime('%Y/%m/%d/') + post_name

        post = Post(
            slug,
            item.findtext('title'),
            item.findtext('link'),
            pub_date,
            get_author(item.findtext(DC_METADATA.creator)),
            item.findtext('description'),
            item.findtext(CONTENT.encoded),
            [tags[x.text] for x in item.findall('tag')
             if x.text in tags],
            [categories[x.text] for x in item.findall('category')
             if x.text in categories],
            [Comment(
                x.findtext(WORDPRESS.comment_author),
                x.findtext(WORDPRESS.comment_content),
                x.findtext(WORDPRESS.comment_author_email),
                x.findtext(WORDPRESS.comment_author_url),
                None,
                x.findtext(WORDPRESS.comment_author_ip),
                parse_wordpress_date(x.findtext(WORDPRESS.comment_date_gmt)),
                'html',
                x.findtext(WORDPRESS.comment_type) in ('pingback',
                                                       'traceback'),
                (COMMENT_UNMODERATED, COMMENT_MODERATED)
                    [x.findtext(WORDPRESS.comment_approved) == '1']
            ) for x in item.findall(WORDPRESS.comment)
              if x.findtext(WORDPRESS.comment_approved) != 'spam'],
            item.findtext('comment_status') != 'closed',
            item.findtext('ping_status') != 'closed',
            parser='html'
        )
        posts.append(post)

    return Blog(
        tree.findtext('title'),
        tree.findtext('link'),
        tree.findtext('description') or '',
        tree.findtext('language') or 'en',
        tags.values(),
        categories.values(),
        posts,
        authors.values()
    )


class WordPressImporter(Importer):
    name = 'wordpress'
    title = 'WordPress'

    def configure(self, request):
        form = WordPressImportForm()

        if request.method == 'POST' and form.validate(request.form):
            dump = request.files.get('dump')
            if not form.data['download_url']:
                try:
                    dump = urllib.urlopen(form.data['download_url'])
                except Exception, e:
                    error = _(u'Error downloading from URL: %s') % e
            elif not dump:
                return redirect_to('import/wordpress')

            try:
                blog = parse_feed(dump)
            except Exception, e:
                log.exception(_(u'Error parsing uploaded file'))
                flash(_(u'Error parsing uploaded file: %s') % e, 'error')
            else:
                self.enqueue_dump(blog)
                flash(_(u'Added imported items to queue.'))
                return redirect_to('admin/import')

        return self.render_admin_page('admin/import_wordpress.html',
                                      form=form.as_widget())
