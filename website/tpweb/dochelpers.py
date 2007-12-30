# -*- coding: utf-8 -*-
"""
    tpweb.dochelpers
    ~~~~~~~~~~~~~~~~

    Helper functions for the documentation.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL
"""
from os import path
from cgi import escape
from docutils import nodes
from docutils.core import publish_parts
from docutils.writers import html4css1
from docutils.transforms.parts import ContentsFilter
from werkzeug.exceptions import NotFound
from tpweb.application import ROOT, render_to_response
from tpweb.smartypants import smartypants


def show_documentation_page(request, slug):
    """Render the documentation template for a slug."""
    parts = prepare_documentation(request, slug)
    if parts is None:
        raise NotFound()
    return render_to_response(request, 'documentation/show.html', {
        'parts':    parts
    })


def get_filename(slug):
    """Get the filename for a slug."""
    return path.join(ROOT, '..', '..', 'docs', *(x for x in
                     slug.split('/') if x != '..')) + '.txt'


def create_translator(url_adapter):
    """Creates a translator that rewrites URLs."""
    class Translator(DocumentationHTMLTranslator):
        def visit_reference(self, node):
            refuri = node.get('refuri')
            if refuri and refuri.endswith('.txt'):
                url = url_adapter.build('documentation/show', {
                    'slug': refuri[:-4]
                })
                node['refuri'] = url
            html4css1.HTMLTranslator.visit_reference(self, node)
    return Translator


class DocumentationHTMLTranslator(html4css1.HTMLTranslator):
    """
    A HTML translator that uses Georg Brandls modified version of
    smartypants for non literal sections.  This is subclassed by
    the `create_translator` factory function to create a translator
    that fixes links.
    """

    def __init__(self, *args, **kwargs):
        html4css1.HTMLTranslator.__init__(self, *args, **kwargs)
        self.no_smarty = 0

    def visit_literal(self, node):
        self.no_smarty += 1
        try:
            html4css1.HTMLTranslator.visit_literal(self, node)
        finally:
            self.no_smarty -= 1

    def visit_literal_block(self, node):
        self.no_smarty += 1
        html4css1.HTMLTranslator.visit_literal_block(self, node)

    def depart_literal_block(self, node):
        try:
            html4css1.HTMLTranslator.depart_literal_block(self, node)
        finally:
            self.no_smarty -= 1

    def encode(self, text):
        text = html4css1.HTMLTranslator.encode(self, text)
        if self.no_smarty <= 0:
            text = smartypants(text)
        return text


class DocumentationWriter(html4css1.Writer):
    """
    Subclass of the default html4css1 writer that creates a table of
    contents and translates links using our url adapter using the
    translator returned by the `create_translator` factory function.
    """

    def __init__(self, request):
        html4css1.Writer.__init__(self)
        self.translator_class = create_translator(request.url_adapter)

    def translate(self):
        html4css1.Writer.translate(self)

        contents = self.build_contents(self.document)
        contents_doc = self.document.copy()
        contents_doc.children = contents
        contents_visitor = self.translator_class(contents_doc)
        contents_doc.walkabout(contents_visitor)
        self.parts['toc'] = u''.join(contents_visitor.fragment)

    def copy_and_filter(self, node):
        visitor = ContentsFilter(self.document)
        node.walkabout(visitor)
        return visitor.get_entry_text()

    def build_contents(self, node, level=0):
        level += 1
        sections = []
        i = len(node) - 1
        while i >= 0 and isinstance(node[i], nodes.section):
            sections.append(node[i])
            i -= 1
        sections.reverse()
        entries = []
        toc_id = 'toc'
        autonum = 0
        depth = 3
        backlinks = self.document.settings.toc_backlinks
        for section in sections:
            title = section[0]
            auto = title.get('auto')
            entrytext = self.copy_and_filter(title)
            reference = nodes.reference('', '', refid=section['ids'][0],
                                        *entrytext)
            ref_id = self.document.set_id(reference)
            entry = nodes.paragraph('', '', reference)
            item = nodes.list_item('', entry)
            if backlinks in ('entry', 'top') and \
               title.next_node(nodes.reference) is None:
                if backlinks == 'entry':
                    title['refid'] = ref_id
                elif backlinks == 'top':
                    title['refid'] = toc_id
            if level < depth:
                subsects = self.build_contents(section, level)
                item += subsects
            entries.append(item)
        if entries:
            contents = nodes.bullet_list('', *entries)
            if auto:
                contents['classes'].append('auto-toc')
            return contents
        return []


def prepare_documentation(request, slug):
    """Load and parse a page and return a dict with the parts."""
    filename = get_filename(slug)
    if not path.isfile(filename):
        return
    writer = DocumentationWriter(request)
    f = file(filename)
    try:
        data = f.read()
    finally:
        f.close()
    return publish_parts(data,
        writer=DocumentationWriter(request),
        settings_overrides={
            'initial_header_level': 3,
            'field_name_limit':     50
    })
