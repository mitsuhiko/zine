# -*- coding: utf-8 -*-
"""
    zine.utils.io
    ~~~~~~~~~~~~~

    Various helper utilities for input/output.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""


def tail(f, n, offset=None):
    """Reads a n lines from f with an offset of offset lines.  The return
    value is a tuple in the form ``(lines, has_more)`` where `has_more` is
    an indicator that is `True` if there are more lines in the file.
    """
    to_read = n + (offset or 0)
    lines = f.read().splitlines()
    return (
        lines[-to_read:offset and -offset or None],
        len(lines) > to_read,
    )
