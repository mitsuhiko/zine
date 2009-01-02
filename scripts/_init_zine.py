# -*- coding: utf-8 -*-
"""
    _init_zine
    ~~~~~~~~~~

    Helper to locate zine and the instance folder.

    :copyright: (c) 2008 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os.path import abspath, join, dirname, pardir, isfile
import sys

# set to None first because the installation replaces this
# with the path to the installed zine library.
ZINE_LIB = None

if ZINE_LIB is None:
    ZINE_LIB = abspath(join(dirname(__file__), pardir))

# make sure we load the correct zine
sys.path.insert(0, ZINE_LIB)


def find_instance():
    """Find the Zine instance."""
    instance = None
    if isfile(join('instance', 'zine.ini')):
        instance = abspath('instance')
    else:
        old_path = None
        path = abspath('.')
        while old_path != path:
            path = abspath(join(path, pardir))
            if isfile(join(path, 'zine.ini')):
                instance = path
                break
            old_path = path
    return instance
