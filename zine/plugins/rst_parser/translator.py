# -*- coding: utf-8 -*-
"""
    zine.plugins.rst_parser.translator
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Translates a docutils node tree into a ZEML tree.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import copy
import re

from zine.parsers import parse_html
from zine.utils.zeml import RootElement, Element, MarkupErrorElement

from docutils import nodes
from docutils.nodes import NodeVisitor, SkipNode


class ZemlTranslator(NodeVisitor):

    words_and_spaces = re.compile(r'\S+| +|\n')

    def __init__(self, document):
        NodeVisitor.__init__(self, document)
        self.root = RootElement()
        self.curnode = self.root
        self.context = []
        self.compact_simple = None
        self.compact_field_list = None
        self.compact_p = 1
        self.initial_header_level = 2
        self.section_level = 0

    def begin_node(self, node, tagname, **more_attributes):
        zeml_node = Element(tagname)
        attributes = zeml_node.attributes
        for name, value in more_attributes.iteritems():
            attributes[name.lower()] = value
        if node is not None:
            classes = node.get('classes', [])
            if 'class' in attributes:
                classes.append(attributes['class'])
            if classes:
                attributes['class'] = ' '.join(classes)
            if node.has_key('ids') and node['ids']:
                # support only one ID
                attributes['id'] = node['ids'][0]
        zeml_node.parent = self.curnode
        self.curnode.children.append(zeml_node)
        self.curnode = zeml_node

    def end_node(self):
        self.curnode = self.curnode.parent

    def add_text(self, text):
        if not self.curnode.children:
            self.curnode.text += text
        else:
            self.curnode.children[-1].tail += text

    def unknown_visit(self, node):
        return

    def unknown_departure(self, node):
        return

    trivial_nodes = {
        'strong': ('strong', {}),
        'abbreviation': ('abbr', {}),
        'acronym': ('acronym', {}),
        'address': ('pre', {'class': 'address'}),
        'block_quote': ('blockquote', {}),
        'caption': ('p', {'class': 'caption'}),
        'compound': ('div', {'class': 'compound'}),
        'emphasis': ('em', {}),
        'field': ('tr', {}),
        'field_body': ('td', {}),
        'inline': ('span', {}),
        'line_block': ('div', {'class': 'line-block'}),
        'intro': ('intro', {}),
        'transition': ('hr', {'class': 'docutils'}),
        'superscript': ('sup', {}),
        'doctest': ('pre', {'class': 'doctest-block'}),
        'rubric': ('p', {'class': 'rubric'}),
        'title_reference': ('cite', {}),
        'legend': ('div', {'class': 'legend'}),
        'line_block': ('div', {'class': 'line-block'}),
        'literal_block': ('pre', {'class': 'literal-block'}),
        'definition_list': ('dl', {'class': 'docutils'}),
    }

    def dispatch_visit(self, node):
        # don't call visitor methods for trivial nodes
        node_name = node.__class__.__name__
        if node_name == 'Text':
            self.add_text(node.astext())
            raise SkipNode
        tagname, atts = self.trivial_nodes.get(node_name, (None, None))
        if tagname:
            self.begin_node(node, tagname, **atts)
        else:
            getattr(self, 'visit_' + node_name, self.unknown_visit)(node)

    def dispatch_departure(self, node):
        node_name = node.__class__.__name__
        tagname, _ = self.trivial_nodes.get(node_name, (None, None))
        if tagname:
            self.end_node()
        else:
            getattr(self, 'depart_' + node_name, self.unknown_departure)(node)

    def visit_zeml(self, node):
        node = copy.deepcopy(node['zeml'])
        node.parent = self.curnode
        self.curnode.children.append(node)
        raise SkipNode

    def visit_citation_reference(self, node):
        self.begin_node(node, 'a', CLASS='citation-reference', href='#'+node['refid'])
        self.add_text('[')
    def depart_citation_reference(self, node):
        self.add_text(']')
        self.end_node()

    def set_class_on_child(self, node, class_, index=0):
        """
        Set class `class_` on the visible child no. index of `node`.
        Do nothing if node has fewer children than `index`.
        """
        children = [n for n in node if not isinstance(n, nodes.Invisible)]
        try:
            child = children[index]
        except IndexError:
            return
        child['classes'].append(class_)

    def set_first_last(self, node):
        self.set_class_on_child(node, 'first', 0)
        self.set_class_on_child(node, 'last', -1)

    def add_node(self, name, text='', **attributes):
        self.begin_node(None, name, **attributes)
        self.add_text(text)
        self.end_node()

    def visit_definition(self, node):
        self.end_node()
        self.begin_node(node, 'dd')
        self.set_first_last(node)

    def depart_definition(self, node):
        self.end_node()

    def visit_definition_list_item(self, node):
        pass

    def depart_definition_list_item(self, node):
        pass

    def visit_term(self, node):
        self.begin_node(node, 'dt')

    def depart_term(self, node):
        """
        Leave the end tag to `self.visit_definition()`, in case there's a
        classifier.
        """
        pass

    def should_be_compact_paragraph(self, node):
        """
        Determine if the <p> tags around paragraph ``node`` can be omitted.
        """
        return False

    def visit_paragraph(self, node):
        if self.should_be_compact_paragraph(node):
            self.context.append(False)
        else:
            self.begin_node(node, 'p')
            self.context.append(True)

    def depart_paragraph(self, node):
        if self.context.pop():
            self.end_node()

    def visit_raw(self, node):
        if 'html' in node.get('format', '').split():
            # not just using a HTMLElement so that the elements in here
            # can be sanitized in comments
            newnode = parse_html(node.astext())
            for child in newnode.children:
                child.parent = self.curnode
                self.curnode.children.append(child)
        raise SkipNode

    def visit_classifier(self, node):
        self.add_node('span', ' : ', CLASS="classifier-delimiter")
        self.begin_node(node, 'span', CLASS='classifier')

    def depart_classifier(self, node):
        self.end_node()

    def visit_admonition(self, node):
        self.begin_node(node, 'div')
        self.set_first_last(node)

    def depart_admonition(self, node=None):
        self.end_node()

    def visit_attribution(self, node):
        self.begin_node(node, 'p', u'\u2013', CLASS='attribution')

    def depart_attribution(self, node):
        self.end_node()

    def is_compactable(self, node):
        return False

    def visit_bullet_list(self, node):
        atts = {}
        old_compact_simple = self.compact_simple
        self.context.append((self.compact_simple, self.compact_p))
        self.compact_p = None
        self.compact_simple = self.is_compactable(node)
        if self.compact_simple and not old_compact_simple:
            atts['class'] = 'simple'
        self.begin_node(node, 'ul', **atts)

    def depart_bullet_list(self, node):
        self.compact_simple, self.compact_p = self.context.pop()
        self.end_node()

    def visit_decoration(self, node):
        pass

    def depart_decoration(self, node):
        pass

    def visit_enumerated_list(self, node):
        """
        The 'start' attribute does not conform to HTML 4.01's strict.dtd, but
        CSS1 doesn't help. CSS2 isn't widely enough supported yet to be
        usable.
        """
        atts = {}
        if node.has_key('start'):
            atts['start'] = node['start']
        if node.has_key('enumtype'):
            atts['class'] = node['enumtype']
        # @@@ To do: prefix, suffix. How? Change prefix/suffix to a
        # single "format" attribute? Use CSS2?
        old_compact_simple = self.compact_simple
        self.context.append((self.compact_simple, self.compact_p))
        self.compact_p = None
        self.compact_simple = self.is_compactable(node)
        if self.compact_simple and not old_compact_simple:
            atts['class'] = (atts.get('class', '') + ' simple').strip()
        self.begin_node(node, 'ol', **atts)

    def depart_enumerated_list(self, node):
        self.compact_simple, self.compact_p = self.context.pop()
        self.end_node()

    def visit_figure(self, node):
        atts = {'class': 'figure'}
        if node.get('width'):
            atts['style'] = 'width: %s' % node['width']
        if node.get('align'):
            atts['class'] += " align-" + node['align']
        self.begin_node(node, 'div', **atts)

    def depart_figure(self, node):
        self.end_node()

    def visit_footnote(self, node):
        self.begin_node(node, 'table', CLASS='docutils footnote',
                                       frame="void", rules="none")
        self.begin_node(None, 'colgroup')
        self.add_node('col', CLASS='label')
        self.add_node('col')
        self.end_node()
        self.begin_node(None, 'tbody', valign="top")
        self.begin_node(None, 'tr')
        self.footnote_backrefs(node)

    def footnote_backrefs(self, node):
        backrefs = node['backrefs']
        backlinks = []
        if backrefs:
            if len(backrefs) == 1:
                link = "#%s" % backrefs[0]
                tags = [{'class': "fn-backref", 'href': link}]
                self.context.append(tags)
            else:
                for i, backref in enumerate(backrefs):
                    i += 1
                    link = "#%s" % backref
                    backlinks.append(({'class': "fn-backref", 'href': link}, i))
                self.context.append(backlinks)
        else:
            self.context.append(None)
        # If the node does not only consist of a label.
        if len(node) > 1:
            # If there are preceding backlinks, we do not set class
            # 'first', because we need to retain the top-margin.
            if not backlinks:
                node[1]['classes'].append('first')
            node[-1]['classes'].append('last')

    def depart_footnote(self, node):
        # </td></tr></tbody></table>
        self.end_node()
        self.end_node()
        self.end_node()
        self.end_node()

    def visit_footnote_reference(self, node):
        href = '#' + node['refid']
        suffix = '['
        self.context.append(']')
        self.begin_node(node, 'a',
                        CLASS='footnote-reference', href=href)
        self.add_text(suffix)

    def depart_footnote_reference(self, node):
        self.add_text(self.context.pop())
        self.end_node()

    def visit_generated(self, node):
        pass

    def depart_generated(self, node):
        pass

    def visit_label(self, node):
        # Context added in footnote_backrefs.
        links = self.context.pop()
        self.begin_node(node, 'td', CLASS='label')
        if links is None:
            self.context.append(0)
        elif len(links) == 1:
            attrs = links[0]
            self.context.append(1)
            self.begin_node(None, 'a', **attrs)
        else:
            self.context.append(links)
        self.add_text('[')

    def depart_label(self, node):
        # Context added in footnote_backrefs.
        links = self.context.pop()
        self.add_text(']')
        if links == 1:
            self.end_node()
        self.end_node()
        self.begin_node(None, 'td')
        if links not in (0, 1):
            self.begin_node(None, 'em')
            self.add_text('(')
            for attrs, i in links:
                self.begin_node(None, 'a', **attrs)
                self.add_text(str(i))
                self.end_node()
                if i != len(links):
                    self.add_text(', ')
            self.add_text(')')
            self.end_node()

    def visit_target(self, node):
        if not (node.has_key('refuri') or node.has_key('refid')
                or node.has_key('refname')):
            self.begin_node(node, 'span', CLASS='target')
            self.context.append(True)
        else:
            self.context.append(False)

    def depart_target(self, node):
        if self.context.pop():
            self.end_node()

    def visit_image(self, node):
        atts = {}
        atts['src'] = node['uri']
        if node.has_key('width'):
            atts['width'] = node['width']
        if node.has_key('height'):
            atts['height'] = node['height']
        if node.has_key('scale'):
            for att_name in 'width', 'height':
                if att_name in atts:
                    match = re.match(r'([0-9.]+)(\S*)$', atts[att_name])
                    assert match
                    atts[att_name] = '%s%s' % (
                        float(match.group(1)) * (float(node['scale']) / 100),
                        match.group(2))
        style = []
        for att_name in 'width', 'height':
            if att_name in atts:
                if re.match(r'^[0-9.]+$', atts[att_name]):
                    # Interpret unitless values as pixels.
                    atts[att_name] += 'px'
                style.append('%s: %s;' % (att_name, atts[att_name]))
                del atts[att_name]
        if style:
            atts['style'] = ' '.join(style)
        atts['alt'] = node.get('alt', atts['src'])
        if (isinstance(node.parent, nodes.TextElement) or
            (isinstance(node.parent, nodes.reference) and
             not isinstance(node.parent.parent, nodes.TextElement))):
            # Inline context or surrounded by <a>...</a>.
            suffix = ''
        else:
            suffix = '\n'
        if node.has_key('classes') and 'align-center' in node['classes']:
            node['align'] = 'center'

        div_wrapper = False
        if node.has_key('align'):
            if node['align'] == 'center':
                # "align" attribute is set in surrounding "div" element.
                div_wrapper = True
                self.begin_node(node, 'div', align="center",
                                CLASS="align-center")
                suffix = ''
            else:
                # "align" attribute is set in "img" element.
                atts['align'] = node['align']
            atts['class'] = 'align-%s' % node['align']
        self.context.append(div_wrapper)
        if div_wrapper:
            node = None
        self.begin_node(node, 'img', **atts)
        if suffix:
            self.add_text(suffix)
        self.end_node()

    def depart_image(self, node):
        if self.context.pop():
            self.end_node()

    def visit_reference(self, node):
        atts = {'class': 'reference'}
        if node.has_key('refuri'):
            atts['href'] = node['refuri']
            atts['class'] += ' external'
        else:
            assert node.has_key('refid'), \
                   'References must have "refuri" or "refid" attribute.'
            atts['href'] = '#' + node['refid']
            atts['class'] += ' internal'
        if not isinstance(node.parent, nodes.TextElement):
            assert len(node) == 1 and isinstance(node[0], nodes.image)
            atts['class'] += ' image-reference'
        self.begin_node(node, 'a', **atts)

    def depart_reference(self, node):
        self.end_node()

    def visit_section(self, node):
        self.section_level += 1
        self.begin_node(node, 'div', CLASS='section')

    def depart_section(self, node):
        self.section_level -= 1
        self.end_node()

    def visit_sidebar(self, node):
        self.begin_node(node, 'div', CLASS='sidebar')
        self.set_first_last(node)
        self.in_sidebar = 1

    def depart_sidebar(self, node):
        self.end_node()
        self.in_sidebar = None

    def visit_title(self, node):
        """Only 6 section levels are supported by HTML."""
        check_id = 0
        if isinstance(node.parent, nodes.topic):
            self.begin_node(node, 'p', CLASS='topic-title first')
        elif isinstance(node.parent, nodes.sidebar):
            self.begin_node(node, 'p', CLASS='sidebar-title')
        elif isinstance(node.parent, nodes.Admonition):
            self.begin_node(node, 'p', CLASS='admonition-title')
        elif isinstance(node.parent, nodes.table):
            self.begin_node(node, 'caption')
        elif isinstance(node.parent, nodes.document):
            self.begin_node(node, 'h1', CLASS='title')
        else:
            assert isinstance(node.parent, nodes.section)
            h_level = self.section_level + self.initial_header_level - 1
            atts = {}
            if (len(node.parent) >= 2 and
                isinstance(node.parent[1], nodes.subtitle)):
                atts['CLASS'] = 'with-subtitle'
            self.begin_node(node, 'h%s' % h_level, **atts)
            # We don't do back-reference link for title

    def depart_title(self, node):
        self.end_node()

    def visit_topic(self, node):
        self.begin_node(node, 'div', CLASS='topic')
        self.topic_classes = node['classes']

    def depart_topic(self, node):
        self.end_node()
        self.topic_classes = []

    def visit_line(self, node):
        self.begin_node(node, 'div', CLASS='line')
        if not len(node):
            self.add_node('br')

    def depart_line(self, node):
        self.end_node()

    def visit_list_item(self, node):
        self.begin_node(node, 'li')
        if len(node):
            node[0]['classes'].append('first')

    def depart_list_item(self, node):
        self.end_node()

    def visit_literal(self, node):
        """Process text to prevent tokens from wrapping."""
        self.begin_node(node, 'tt', CLASS='docutils literal')
        text = node.astext()
        for token in self.words_and_spaces.findall(text):
            if token.strip():
                # Protect text like "--an-option" from bad line wrapping:
                self.add_node('span', token, CLASS="pre")
            elif token in ('\n', ' '):
                # Allow breaks at whitespace:
                self.add_text(token)
            else:
                # Protect runs of multiple spaces; the last space can wrap:
                # XXXX what to do about this for zeml???
                self.add_text('&nbsp;' * (len(token) - 1) + ' ')
        self.end_node()
        # Content already processed:
        raise nodes.SkipNode

    def visit_subtitle(self, node):
        close_two = False
        if isinstance(node.parent, nodes.sidebar):
            self.begin_node(node, 'p', CLASS='sidebar-subtitle')
        elif isinstance(node.parent, nodes.document):
            self.begin_node(node, 'h2', CLASS='subtitle')
        elif isinstance(node.parent, nodes.section):
            tag = 'h%s' % (self.section_level + self.initial_header_level - 1)
            self.begin_node(node, 'h2', CLASS='section-subtitle')
            self.begin_node(None, 'span', '', CLASS='section-subtitle')
            close_two = True

        self.context.append(close_two)

    def depart_subtitle(self, node):
        self.end_node()
        if self.context.pop():
            self.end_node()

    def visit_system_message(self, node):
        line = ''
        if node.hasattr('line'):
            line = ', line %s' % node['line']
        
        #  The text should be handled as a paragraph but we handle it here using MarkupErrorElement
        text = node[0][0].astext()
        message = 'System Message: %s/%s %s, %s\n' % (node['type'], node['level'], line, text)
        
        zeml_node = MarkupErrorElement(message)
        zeml_node.parent = self.curnode
        self.curnode.children.append(zeml_node)
        self.curnode = zeml_node
        
        self.end_node()
        raise nodes.SkipNode


