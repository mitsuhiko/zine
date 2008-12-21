# -*- coding: utf-8 -*-
"""
    zine.zxa
    ~~~~~~~~

    Zine eXtended Atom.  This module sounds like it has a ridiculous
    implementation but that's actually intention.  The main reason is that
    because this file can (and does) become incredible big for bigger blogs
    and elementtree does not really support what we try to achieve here we
    somewhat hack around the limitation by using a separate element tree for
    each item and wrap it in hand written XML.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD
"""
from cPickle import dumps
from datetime import datetime
from itertools import chain

import zine
from lxml import etree
from zine.api import *
from zine.models import Post, User
from zine.utils import build_tag_uri
from zine.utils.dates import format_iso8601
from zine.utils.xml import escape, XML_NS
from zine.utils.zeml import dump_parser_data


ATOM_NS = 'http://www.w3.org/2005/Atom'
ZINE_NS = 'http://zine.pocoo.org/'
ZINE_TAG_URI = ZINE_NS + '#tag-scheme'
ZINE_CATEGORY_URI = ZINE_NS + '#category-scheme'

XML_PREAMBLE = u'''\
<?xml version="1.0" encoding="utf-8"?>
<!--

    This is a Zine eXtended Atom file.  It is a superset of the Atom
    specification so every Atom-enabled application should be able to use at
    least the Atom subset of the exported data.  You can use this file to
    import your blog data in other blog software.

    Developer Notice
    ~~~~~~~~~~~~~~~~

    Because we saw horrible export formats (wordpress' wxr *cough*) we want
    to avoid problems with this file right away.  If you are an application
    developer that wants to use this file to import blog posts you have to
    to the following:

    -   parse the file with a proper XML parser.  And proper means shout
        on syntax and encoding errors.
    -   handle namespaces!  The prefixes might and will change, so use the
        goddamn full qualified names with the namespaces when parsing.

    User Notice
    ~~~~~~~~~~~

    This file contains a dump of your blog but probably exluding some details
    if plugins did not provide ways to export the information.  It's not
    intended as blog backup nor as preferred solution to migrate from one
    machine to another.  The main purpose of this file is being a portable
    file that can be read by other blog software if you want to switch to
    something else.

-->
<feed xmlns="%(atom_ns)s" xmlns:zine="%(zine_ns)s" xml:lang="%(language)s">\
<title>%(title)s</title>\
<subtitle>%(subtitle)s</subtitle>\
<id>%(id)s</id>\
<generator uri="http://zine.pocoo.org/"\
 version="%(version)s">ZineXA Export</generator>\
<link href="%(blog_url)s"/>\
<updated>%(updated)s</updated>'''
XML_EPILOG = '</feed>'


NAMESPACES = {None: ATOM_NS, 'zine': ZINE_NS}


def export(app):
    """Dump all the application data into an ZXA response."""
    return Response(Writer(app)._generate(), mimetype='application/atom+xml')


class _ElementHelper(object):

    def __init__(self, ns):
        self._ns = ns

    def __getattr__(self, tag):
        return '{%s}%s' % (self._ns, tag)

    def __call__(self, tag, attrib=None, parent=None, **extra):
        tag = getattr(self, tag)
        text = extra.pop('text', None)
        if attrib is None:
            attrib = {}
        attrib.update(extra)
        if parent is not None:
            rv = etree.SubElement(parent, tag, attrib, nsmap=NAMESPACES)
        else:
            rv = etree.Element(tag, attrib, nsmap=NAMESPACES)
        if text is not None:
            rv.text = text
        return rv


class Participant(object):

    def __init__(self, writer):
        self.app = writer.app
        etree = writer.etree
        self.writer = writer

    def before_dump(self):
        pass

    def dump_data(self):
        pass

    def process_post(self, node, post):
        pass

    def process_user(self, node, user):
        pass


class Writer(object):

    def __init__(self, app):
        self.app = app
        self.atom = _ElementHelper(ATOM_NS)
        self.z = _ElementHelper(ZINE_NS)
        self._dependencies = {}
        self.users = {}
        self.participants = [x(self) for x in
                             emit_event('get-zxa-participants') if x]

    def _generate(self):
        now = datetime.utcnow()
        posts = iter(Post.query.order_by(Post.last_update.desc()))
        try:
            first_post = posts.next()
            last_update = first_post.last_update
            posts = chain((first_post,), posts)
        except StopIteration:
            first_post = None
            last_update = now

        feed_id = build_tag_uri(self.app, last_update, 'zxa_export', 'full')
        yield (XML_PREAMBLE % {
            'version':      escape(zine.__version__),
            'title':        escape(self.app.cfg['blog_title']),
            'subtitle':     escape(self.app.cfg['blog_tagline']),
            'atom_ns':      ATOM_NS,
            'zine_ns':      ZINE_NS,
            'id':           escape(feed_id),
            'blog_url':     escape(self.app.cfg['blog_url']),
            'updated':      format_iso8601(last_update),
            'language':     self.app.cfg['language']
        }).encode('utf-8')

        def dump_node(node):
            return etree.tostring(node, encoding='utf-8')

        for participant in self.participants:
            participant.setup()

        # dump configuration
        cfg = self.z('configuration')
        for key, value in self.app.cfg.export():
            self.z('item', key=key, text=value, parent=cfg)
        yield dump_node(cfg)

        # allow plugins to dump trees
        for participant in self.participants:
            rv = participant.dump_data()
            if rv is not None:
                yield dump_node(rv)

        # look up all the users and add them as dependencies if they
        # have written a comment or created a post.
        for user in User.query.all():
            if user.posts.count() > 0 or user.comments.count() > 0:
                self._register_user(user)

        # dump all the posts
        for post in posts:
            yield dump_node(self._dump_post(post))

        # if we have dependencies (very likely) dump them now
        if self._dependencies:
            yield '<zine:dependencies>'
            for node in self._dependencies.itervalues():
                yield dump_node(node)
            yield '</zine:dependencies>'

        yield XML_EPILOG.encode('utf-8')

    def new_dependency(self, tag):
        id = '%x' % (len(self._dependencies) + 1)
        node = etree.Element(tag, {'dependency': id}, nsmap=NAMESPACES)
        self._dependencies[id] = node
        return node

    def _register_user(self, user):
        rv = self.new_dependency(self.z.user)
        self.z('username', text=user.username, parent=rv)
        self.z('email', text=user.email, parent=rv)
        self.z('pw_hash', text=user.pw_hash.encode('base64'), parent=rv)
        self.z('display_name', text=user._display_name, parent=rv)
        self.z('real_name', text=user.real_name, parent=rv)
        self.z('description', text=user.description, parent=rv)
        self.z('is_author', text=user.is_author and 'yes' or 'no', parent=rv)
        self.z('extra', text=dumps(user.extra).encode('base64'))
        for participant in self.participants:
            participant.process_user(rv, user)
        privileges = self.z('privileges', parent=rv)
        for privilege in user.own_privileges:
            self.z('privilege', text=privilege.name, parent=privileges)
        self.users[user.id] = rv

    def _dump_post(self, post):
        url = url_for(post, _external=True)
        entry = self.atom('entry', {'{%s}base' % XML_NS: url})
        self.atom('title', text=post.title, type='text', parent=entry)
        self.atom('id', text=post.uid, parent=entry)
        self.atom('updated', text=format_iso8601(post.last_update),
                  parent=entry)
        self.atom('published', text=format_iso8601(post.pub_date),
                  parent=entry)
        self.atom('link', href=url, parent=entry)

        author = self.atom('author', parent=entry)
        author.attrib[self.z.dependency] = self.users[post.author.id] \
                                                .attrib['dependency']
        self.atom('name', text=post.author.display_name, parent=author)
        self.atom('email', text=post.author.email, parent=author)

        self.z('slug', text=post.slug, parent=entry)
        self.z('comments_enabled', text=post.comments_enabled
               and 'yes' or 'no', parent=entry)
        self.z('pings_enabled', text=post.pings_enabled
               and 'yes' or 'no', parent=entry)
        self.z('status', text=str(post.status), parent=entry)
        self.z('content_type', text=str(post.content_type))

        self.atom('content', type='text', text=post.text, parent=entry)
        self.atom('content', type='html', text=post.body.to_html(), parent=entry)
        if post.intro:
            self.atom('summary', type='html', text=post.intro.to_html(),
                      parent=entry)

        for category in post.categories:
            attrib = dict(term=category.slug, scheme=ZINE_CATEGORY_URI)
            if category.slug != category.name:
                attrib['label'] = category.name
            element = self.atom('category', attrib=attrib, parent=entry)
            if category.description:
                self.zine.description(category.description, parent=element)

        for tag in post.tags:
            attrib = dict(term=tag.slug, scheme=ZINE_TAG_URI)
            if tag.slug != tag.name:
                attrib['label'] = tag.name
            self.atom('tag', attrib=attrib, parent=entry)

        self.z('data', text=dump_parser_data(post.parser_data).encode('base64'),
               parent=entry)

        for c in post.comments:
            comment = self.z('comment', parent=entry)
            comment.attrib['id'] = str(c.id)
            author = self.z('author', parent=comment)
            self.z('name', text=c.author, parent=author)
            self.z('email', text=c.email, parent=author)
            self.z('uri', text=c.www, parent=author)
            if c.user is not None:
                author.attrib['dependency'] = self.users[c.user.id] \
                                                  .attrib[self.z.dependency]
            self.z('published', text=format_iso8601(c.pub_date),
                   parent=comment)
            self.z('blocked', text=c.blocked and 'yes' or 'no',
                   parent=comment)
            self.z('is_pingback', text=c.is_pingback and 'yes' or 'no',
                   parent=comment)
            self.z('status', text=str(c.status), parent=comment),
            self.z('blocked_msg', text=str(c.blocked_msg or ''),
                   parent=comment)
            self.z('parent', text=c.parent_id is not None and str(c.parent_id)
                   or '', parent=comment)
            self.z('submitter_ip', text=c.submitter_ip, parent=comment)
            self.z('content', type='html', text=c.body.to_html(),
                   parent=comment)
            self.z('content', type='text', text=c.text, parent=comment)
            self.z('data', text=dump_parser_data(c.parser_data).encode('base64'),
                   parent=comment)

        for participant in self.participants:
            participant.process_post(entry, post)
        return entry
