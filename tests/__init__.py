"""
    TextPress Test Suite
    ~~~~~~~~~~~~~~~~~~~~

    This is the TextPress test suite. It collects all modules in the textpress
    package, builds a TestSuite with their doctests and executes them.

    :copyright: 2008 by Lukas Meuser.
    :license: GNU GPL.
"""

import sys
from os import walk
from os.path import join, dirname
from unittest import TestSuite, main
from doctest import DocTestSuite

from textpress.application import make_textpress

def suite():
    """Generate the test suite."""
    instance_path = join(dirname(__file__), 'instance')
    app = make_textpress(instance_path)

    suite = TestSuite()
    for mod in find_tp_modules():
        suite.addTest(DocTestSuite(mod, extraglobs={'app': app}))
    return suite


def find_tp_modules():
    """Find all sub-modules of the textpress package."""
    modules = []
    import textpress
    base = dirname(textpress.__file__)
    start = len(dirname(base)) + 1

    for path, dirnames, filenames in walk(base):
        for filename in filenames:
            if filename.endswith('.py'):
                fullpath = join(path, filename)
                # currently there are problems with plugins because of the
                # import hook. Therefore, we skip them:
                if 'plugins' in fullpath:
                    continue

                if filename == '__init__.py':
                    stripped = fullpath[start:-12]
                else:
                    stripped = fullpath[start:-3]

                modname = stripped.replace('/', '.')
                # the fromlist must contain something, otherwise the textpress
                # package is returned, not our module
                modules.append(__import__(modname, fromlist=['']))
    return modules



if __name__ == '__main__':
    main(defaultTest='suite')
