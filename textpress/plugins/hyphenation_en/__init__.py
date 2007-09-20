# -*- coding: utf-8 -*-
"""
    textpress.plugins.hyphenation_en
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module automatically hyphenates english texts.  The implementation of
    the algorithm is in the "hyphenate.py" file and written by Nel Batchelder.

    The only problem?  Browsers don't support this yet.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import re
from textpress.api import *
from textpress.plugins.hyphenation_en.hyphenate import hyphenate_word

_ignored_nodes = set(['pre', 'code'])
_word_re = re.compile(r'(\w+)(?u)')


def process_doc_tree(doctree, input_data, reason):
    """
    Parse time callback function that replaces all pre blocks with a
    'syntax' attribute the highlighted sourcecode.
    """
    for node in doctree.query('#'):
        if not node.parent or node.parent.name not in _ignored_nodes:
            worditer = iter(_word_re.split(node.value))
            buf = []
            for space in worditer:
                try:
                    word = worditer.next()
                except StopIteration:
                    buf.append(space)
                else:
                    buf.extend((space, u'\u200b'.join(hyphenate_word(word))))
            node.value = u''.join(buf)


def setup(app, plugin):
    app.connect_event('process-doc-tree', process_doc_tree)
