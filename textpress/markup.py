# -*- coding: utf-8 -*-
"""
    textpress.markup
    ~~~~~~~~~~~~~~~~

    This module implements a simple text formatting markup used for post
    comments. It does not allow HTML but some simple formattings like
    **bold**, ``code`` etc.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import cgi
import re
from textpress.utils import is_valid_url


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

simple_formattings = {
    'strong_begin':                 '<strong>',
    'strong_end':                   '</strong>',
    'emphasized_begin':             '<em>',
    'emphasized_end':               '</em>',
    'quote_begin':                  '<blockquote>',
    'quote_end':                    '</blockquote>'
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


class MarkupParser(object):
    """This class tokenizes and translates the output to HTML."""

    def __init__(self, text):
        self.text = text

    def tokenize(self):
        text = '\n'.join(self.text.splitlines())
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
                        yield 'text', ''.join(text_buffer)
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

    def stream_to_html(self):
        """Tokenize a text and return a generator that yields HTML parts."""
        paragraph = []
        result = []

        def new_paragraph():
            result.append(paragraph[:])
            del paragraph[:]

        for token, data in self.tokenize():
            if token in simple_formattings:
                paragraph.append(simple_formattings[token])
            elif token in ('text', 'escaped_code', 'code'):
                if data:
                    data = cgi.escape(data)
                    if token in ('escaped_code', 'code'):
                        data = '<code>%s</code>' % data
                    paragraph.append(data)
            elif token == 'link':
                if ' ' in data:
                    href, caption = data.split(' ', 1)
                else:
                    href = caption = data
                if is_valid_url(href):
                    paragraph.append('<a href="%s" rel="nofollow">%s</a>' %
                                     (cgi.escape(href), cgi.escape(caption)))
                else:
                    paragraph.append(data)
            elif token == 'code_block':
                result.append(cgi.escape(data))
                new_paragraph()
            elif token == 'paragraph':
                new_paragraph()
            elif token == 'newline':
                paragraph.append('<br>')

        if paragraph:
            result.append(paragraph)
        for item in result:
            if isinstance(item, list):
                if item:
                    yield '<p>%s</p>' % ''.join(item)
            else:
                yield item

    def to_html(self):
        """Convert the passed text to HTML."""
        return ''.join(self.stream_to_html())
