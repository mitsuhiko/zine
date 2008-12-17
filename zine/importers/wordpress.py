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
from zine.importers import Importer, Blog, Label, Author, Post, Comment
from zine.utils.admin import flash
from zine.utils.xml import _html_entities, get_etree, escape
from zine.utils.http import redirect_to
from zine.utils.xxx import CSRFProtector, StreamReporter, \
     make_hidden_fields
from zine.models import COMMENT_UNMODERATED, COMMENT_MODERATED


class _Namespace(object):
    def __init__(self, uri):
        self._uri = uri
    def __getattr__(self, name):
        return '{%s}%s' % (self._uri, name)

CONTENT = _Namespace('http://purl.org/rss/1.0/modules/content/')
DC_METADATA = _Namespace('http://purl.org/dc/elements/1.1/')
WORDPRESS = _Namespace('http://wordpress.org/export/1.0/')


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
    inline_doctype = '<!DOCTYPE wordpress [ %s ]>' % '\n'.join(
        '<!ENTITY %s "&#%d;">' % (name, codepoint)
        for name, codepoint in _html_entities.iteritems()
    )
    code = fd.read()
    xml_decl = _xml_decl_re.search(code)
    if xml_decl is not None:
        code = code[:xml_decl.end()] + inline_doctype + code[xml_decl.end():]
    else:
        code = inline_doctype + code

    # fix two: find comment sections and escape them.  Especially trackbacks
    # tent to break the XML structure.  same applies to wp:meta_value stuff.
    def escape_if_good_idea(match):
        before, content, after = match.groups()
        if not content.lstrip().startswith('<!CDATA[['):
            content = escape(content)
        return before + content + after
    code = _meta_value_re.sub(escape_if_good_idea, code)
    code = _comment_re.sub(escape_if_good_idea, code)

    return get_etree().fromstring(code).find('channel')


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
                author = authors[name] = Author(len(authors) + 1, name, None)
            return author

    labels = {}
    for item in tree.findall(WORDPRESS.category):
        label = Label(item.findtext(WORDPRESS.category_nicename),
                      item.findtext(WORDPRESS.cat_name))
        labels[label.name] = label

    return Blog(
        tree.findtext('title'),
        tree.findtext('link'),
        tree.findtext('description') or '',
        tree.findtext('language') or 'en',
        labels.values(),
        [Post(
            item.findtext(WORDPRESS.post_name),
            item.findtext('title'),
            item.findtext('link'),
            parse_wordpress_date(item.findtext(WORDPRESS.post_date_gmt)),
            get_author(item.findtext(DC_METADATA.creator)),
            item.findtext('description'),
            item.findtext(CONTENT.encoded),
            [labels[x.text] for x in item.findall('category')
             if x.text in labels],
            [Comment(
                x.findtext(WORDPRESS.comment_author),
                x.findtext(WORDPRESS.comment_author_email),
                x.findtext(WORDPRESS.comment_author_url),
                x.findtext(WORDPRESS.comment_author_ip),
                parse_wordpress_date(x.findtext(WORDPRESS.comment_date_gmt)),
                x.findtext(WORDPRESS.comment_content), 'plain',
                x.findtext(WORDPRESS.comment_type) in ('pingback',
                                                       'traceback'),
                (COMMENT_UNMODERATED, COMMENT_MODERATED)
                    [x.findtext(WORDPRESS.comment_approved) == '1']
            ) for x in item.findall(WORDPRESS.comment)
              if x.findtext(WORDPRESS.comment_approved) != 'spam'],
            item.findtext('comment_status') != 'closed',
            item.findtext('ping_status') != 'closed',
            parser='autop'
        ) for item in tree.findall('item')
          if item.findtext(WORDPRESS.status) == 'publish'],
        authors.values()
    )


class WordPressImporter(Importer):
    name = 'wordpress'
    title = 'WordPress'

    def configure(self, request):
        form = dict.fromkeys(('download_url', 'dump'))
        error = None
        csrf_protector = CSRFProtector()
        reporter = StreamReporter()

        if request.method == 'POST':
            csrf_protector.assert_safe()
            form['download_url'] = url = request.form.get('download_url')
            dump = request.files.get('dump')
            if url and dump:
                error = _('Both dump uploaded and download URL given.')
            elif url:
                try:
                    dump = urllib.urlopen(url)
                except Exception, e:
                    error = _('Error downloading from URL: %s') % e
            elif not dump:
                return redirect_to('import/wordpress')

            if error is not None:
                flash(error, 'error')
            else:
                try:
                    blog = parse_feed(dump)
                except Exception, e:
                    flash(_('Error parsing uploaded file: %s') % e, 'error')
                else:
                    self.enqueue_dump(blog)
                    flash('Added imported items to queue.')
                    return redirect_to('admin/import')

        return self.render_admin_page('admin/import_wordpress.html',
            form=form,
            hidden_form_data=make_hidden_fields(csrf_protector),
            reporter=reporter
        )
