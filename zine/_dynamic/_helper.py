# -*- coding: utf-8 -*-
"""
    zine._dynamic._helper
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Helper file. Does the auto updating of dynamic files.

    :copyright: 2007 by Armin Ronacher.
    :license: BSD
"""
import os
import sys
import re


docstring_re = re.compile(r'^"""$.*?^"""$(?sm)')


def selfupdate(data):
    """
    Call this from a global frame with a source string that will become
    the new source code for this module. The docstring and "__main__"
    code is extracted and reinserted first.
    """
    filename = os.path.realpath(sys._getframe(1).f_globals['__file__'])

    f = file(filename)
    try:
        old_data = f.read()
    finally:
        f.close()

    start_pos = docstring_re.search(old_data).end()
    end_pos = old_data.index('if __name__ == \'__main__\':', start_pos)

    header = old_data[:start_pos]
    code = old_data[end_pos:]
    new_code = '%s\n\n%s\n\n%s' % (header, data, code)

    f = file(filename, 'w')
    try:
        f.write(new_code)
    finally:
        f.close()
