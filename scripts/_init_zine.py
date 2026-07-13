# -*- coding: utf-8 -*-
"""
    _init_zine
    ~~~~~~~~~~

    Helper to locate zine and the instance folder.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os.path import abspath, join, dirname, pardir
import sys

# set to None first because the installation replaces this
# with the path to the installed zine library.
ZINE_LIB = None

if ZINE_LIB is None:
    ZINE_LIB = abspath(join(dirname(__file__), pardir))

# make sure we load the correct zine
sys.path.insert(0, ZINE_LIB)


def find_instance():
    """Find the nearest Zine instance."""
    from zine.cli import find_instance as locate_instance

    return locate_instance()
