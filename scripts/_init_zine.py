# -*- coding: utf-8 -*-
"""
    _init_zine
    ~~~~~~~~~~

    Helper to locate zine and the instance folder.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD
"""
from os.path import abspath, join, dirname, pardir, isfile
import sys


# make sure we load the correct zine
sys.path.insert(0, abspath(join(dirname(__file__), pardir)))


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
