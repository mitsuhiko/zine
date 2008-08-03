# -*- coding: utf-8 -*-
"""
    _init_textpress
    ~~~~~~~~~~~~~~~

    Helper to locate textpress and the instance folder.

    :copyright: 2008 by Armin Ronacher.
    :license: GNU GPL.
"""
from os.path import abspath, join, dirname, pardir, isfile
import sys


# make sure we load the correct textpress
sys.path.insert(0, abspath(join(dirname(__file__), pardir)))


def find_instance():
    """Find the TextPress instance."""
    instance = None
    if isfile(join('instance', 'textpress.ini')):
        instance = abspath('instance')
    else:
        old_path = None
        path = abspath('.')
        while old_path != path:
            path = abspath(join(path, pardir))
            if isfile(join(path, 'textpress.ini')):
                instance = path
                break
    return instance
