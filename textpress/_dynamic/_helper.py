# -*- coding: utf-8 -*-
"""
    textpress._dynamic._helper
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Helper file. Does the auto updating of dynamic files.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import os
import sys
import re


docstring_re = re.compile(r'^"""$.*?^"""$(?sm)')


def selfupdate(data):
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
