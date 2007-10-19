# -*- coding: utf-8 -*-
"""
    textpress.parsers.markup
    ~~~~~~~~~~~~~~~~~~~~~~~~

    This module implements a simple text formatting markup used for post
    comments. It does not allow HTML but some simple formattings like
    **bold**, ``code`` etc.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re
from textpress.fragment import Fragment, Node, TextNode
from textpress.utils import is_valid_url
from textpress.parsers import BaseParser


inline_formatting = {
    'escaped_code': ('``',        '``'),
    'code':         ('`',         '`'),
    'strong':       ('**',        '**'),
    'emphasized':   ('*',         '*'),
    'link':         ('[[',        ']]'),
    'quote':        ('<quote>',   '</quote>'),
    'code_block':   ('<code>',    '</code>'),
    'paragraph':    (r'\n{2,}',   None),
    'newline':      (r'\\$',      None)
}

raw_formatting = set(['link', 'code', 'escaped_code', 'code_block'])

formatting_start_re = re.compile('|'.join(
    '(?P<%s>%s)' % (name, end is not None and re.escape(start) or start)
    for name, (start, end)
    in sorted(inline_formatting.items(), key=lambda x: -len(x[1][0]))
), re.S | re.M)

formatting_end_res = dict(
    (name, re.compile(re.escape(end))) for name, (start, end)
    in inline_formatting.iteritems() if end is not None
)

without_end_tag = set(name for name, (_, end) in inline_formatting.iteritems()
                      if end is None)


class CommentParser(BaseParser):
    """This class tokenizes and translates the output to HTML."""

    @staticmethod
    def get_name():
        from textpress.api import _
        return _('Emphasized Text')

    def tokenize(self, text):
        text = u'\n'.join(text.splitlines())
        last_pos = 0
        pos = 0
        end = len(text)
        stack = []
        text_buffer = []

        while pos < end:
            if stack:
                m = formatting_end_res[stack[-1]].match(text, pos)
                if m is not None:
                    if text_buffer:
                        yield 'text', u''.join(text_buffer)
                        del text_buffer[:]
                    yield stack[-1] + '_end', None
                    stack.pop()
                    pos = m.end()
                    continue

            m = formatting_start_re.match(text, pos)
            if m is not None:
                if text_buffer:
                    yield 'text', ''.join(text_buffer)
                    del text_buffer[:]

                for key, value in m.groupdict().iteritems():
                    if value is not None:
                        if key in without_end_tag:
                            yield key, None
                        else:
                            if key in raw_formatting:
                                regex = formatting_end_res[key]
                                m2 = regex.search(text, m.end())
                                if m2 is None:
                                    yield key, text[m.end():]
                                else:
                                    yield key, text[m.end():m2.start()]
                                m = m2
                            else:
                                yield key + '_begin', None
                                stack.append(key)
                        break

                if m is None:
                    break
                else:
                    pos = m.end()
                    continue

            text_buffer.append(text[pos])
            pos += 1

        yield 'text', ''.join(text_buffer)
        for token in reversed(stack):
            yield token + '_end', None

    def parse(self, input_data, reason):
        node = Node('p')
        result = Fragment()

        for token, data in self.tokenize(input_data):
            if token in ('strong_begin', 'emphasized_begin', 'quote_begin'):
                new_node = Node(token[:-6])
                node.children.append(new_node)
                node = new_node
            elif token in ('strong_end', 'emphasized_end', 'quote_end'):
                assert node.name == token[:-4]
                node = node.parent
            elif token in 'text':
                node.children.append(TextNode(data))
            elif token in ('escaped_code', 'code'):
                new_node = Node('code')
                new_node.children.append(TextNode(data))
                node.children.append(new_node)
            elif token == 'link':
                if ' ' in data:
                    href, caption = data.split(' ', 1)
                else:
                    href = caption = data
                if is_valid_url(href):
                    new_node = Node('a', {
                        'href':     href,
                        'rel':      'nofollow',
                    })
                    new_node.children.append(TextNode(caption))
                    node.children.append(new_node)
                else:
                    node.children.append(TextNode(data))
            elif token == 'code_block':
                if node:
                    result.children.append(node)
                    node = Node('p')
                new_node = Node('pre')
                new_node.children.append(TextNode(data))
                result.children.append(new_node)
            elif token == 'paragraph':
                if node:
                    result.children.append(node)
                    node = Node('p')
            elif token == 'newline':
                node.children.append(Node('br'))

        if node:
            result.children.append(node)
        return result
