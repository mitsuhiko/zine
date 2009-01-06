# -*- coding: utf-8 -*-
"""
    zine.docs.builder
    ~~~~~~~~~~~~~~~~~~~~~~

    The documentation building system.  This is only used by the
    documentation building script.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import re
import os
import cPickle as pickle
from urlparse import urlparse

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.core import publish_parts
from docutils.writers import html4css1


_toc_re = re.compile(r'<!-- TOC -->(.*?)<!-- /TOC -->(?s)')
_toc_contents_re = re.compile(r'<ul[^>]*>(.*)</ul>(?s)')


def plugin_links_directive(name, arguments, options, content, lineno,
                           content_offset, block_text, state, state_machine):
    return [nodes.comment('', 'PLUGIN_LINKS')]
plugin_links_directive.arguments = (0, 0, 0)
plugin_links_directive.content = 1
directives.register_directive('plugin_links', plugin_links_directive)


def is_relative_uri(uri):
    if uri.startswith('/'):
        return False
    # there is no uri parser, but the url parser works mostly
    return not urlparse(uri)[0]


class Translator(html4css1.HTMLTranslator):
    pass


class DocumentationWriter(html4css1.Writer):

    def __init__(self):
        html4css1.Writer.__init__(self)
        self.translator_class = Translator


def generate_documentation(data):
    toc = '\n\n..\n TOC\n\n.. contents::\n\n..\n /TOC'
    parts = publish_parts(data + toc,
        writer=DocumentationWriter(),
        settings_overrides=dict(
            initial_header_level=2,
            field_name_limit=50
        )
    )

    toc = None
    body = parts['body']
    match = _toc_re.search(body)
    body = body[:match.start()] + body[match.end():]
    match = _toc_contents_re.search(match.group(1))
    if match is not None:
        toc = match.group(1)
        # just add the toc if there are at least two entries.
        if toc.count('</li>') < 2:
            toc = None

    return {
        'title':    parts['title'],
        'body':     body,
        'toc':      toc
    }


def walk(directory, callback=lambda filename: None):
    """Walk a directory and translate all the files in there."""
    directory = os.path.normpath(directory)
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith('.rst'):
                relname = os.path.join(dirpath, filename)[len(directory) + 1:]
                f = file(os.path.join(dirpath, filename))
                try:
                    d = generate_documentation(f.read().decode('utf-8'))
                finally:
                    f.close()
                f = file(os.path.join(dirpath, filename[:-3] + 'page'), 'wb')
                try:
                    pickle.dump(d, f, protocol=2)
                finally:
                    f.close()
                callback(relname)
