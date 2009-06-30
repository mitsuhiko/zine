# -*- coding: utf-8 -*-
"""
    zine.plugins.rst_parser.translator
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Translates a docutils node tree into a ZEML tree.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import copy

from zine.utils.zeml import RootElement, Element, HTMLElement, DynamicElement

from docutils import nodes
from docutils.nodes import NodeVisitor, SkipNode


class ZemlTranslator(NodeVisitor):
    def __init__(self, document):
        NodeVisitor.__init__(self, document)
        self.root = RootElement()
        self.curnode = self.root
        self.context = []
        self.compact_simple = None
        self.compact_field_list = None
        self.compact_p = 1

    def begin_node(self, node, tagname, **more_attributes):
        zeml_node = Element(tagname)
        attributes = zeml_node.attributes
        for name, value in more_attributes.iteritems():
            attributes[name.lower()] = value
        classes = node.get('classes', [])
        if 'class' in attributes:
            classes.append(attributes['class'])
        if classes:
            attributes['class'] = ' '.join(classes)
        if 'ids' in node:
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
        'definition_list': ('dl', {}),
        'enumerated_list': ('ol', {}),
        'field': ('tr', {}),
        'field_body': ('td', {}),
        'inline': ('span', {}),
        'line_block': ('div', {'class': 'line-block'}),
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

    def visit_definition_list_item(self, node):
        pass
    def depart_definition_list_item(self, node):
        pass

    def should_be_compact_paragraph(self, node):
        """
        Determine if the <p> tags around paragraph ``node`` can be omitted.
        """
        if (isinstance(node.parent, nodes.document) or
            isinstance(node.parent, nodes.compound)):
            # Never compact paragraphs in document or compound.
            return False
        for key, value in node.attlist():
            if (node.is_not_default(key) and
                not (key == 'classes' and value in
                     ([], ['first'], ['last'], ['first', 'last']))):
                # Attribute which needs to survive.
                return False
        first = isinstance(node.parent[0], nodes.label) # skip label
        for child in node.parent.children[first:]:
            # only first paragraph can be compact
            if isinstance(child, nodes.Invisible):
                continue
            if child is node:
                break
            return False
        parent_length = len([n for n in node.parent if not isinstance(
            n, (nodes.Invisible, nodes.label))])
        if (self.compact_simple
            or self.compact_field_list
            or self.compact_p and parent_length == 1):
            return True
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
            newnode = HTMLElement(node.astext())
            newnode.parent = self.curnode
            self.curnode.children.append(newnode)
        raise SkipNode
