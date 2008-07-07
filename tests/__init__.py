"""
    TextPress Test Suite
    ~~~~~~~~~~~~~~~~~~~~

    This is the TextPress test suite. It collects all modules in the textpress
    package, builds a TestSuite with their doctests and executes them.

    :copyright: 2008 by Lukas Meuser.
    :license: GNU GPL.
"""

import sys
import os
from os.path import join, dirname
from unittest import TestSuite, TextTestRunner
from doctest import DocTestSuite

from textpress.application import make_textpress

#: the modules in this list are not tested in a full run
untested = ['textpress.i18n.compilejs']

try:
    import coverage
except ImportError:
    coverage = None


def suite(return_covermods=False, modnames=[]):
    """Generate the test suite."""
    instance_path = join(dirname(__file__), 'instance')
    app = make_textpress(instance_path)

    if return_covermods:
        covermods = []
    suite = TestSuite()

    if modnames == []:
        modnames = find_tp_modules()
    for modname in modnames:
        if modname in untested:
            continue
        # currently there are problems with plugins because of the
        # import hook. Therefore, we skip them:
        if 'plugins' in modname:
            continue
        # the fromlist must contain something, otherwise the textpress
        # package is returned, not our module
        mod = __import__(modname, fromlist=[''])

        dts = DocTestSuite(mod, extraglobs={'app': app})
        if dts.countTestCases():
            suite.addTest(dts)
            if return_covermods:
                covermods.append(mod)
    if return_covermods:
        return suite, covermods
    else:
        return suite


def find_tp_modules():
    """Find all sub-modules of the textpress package."""
    modules = []
    import textpress
    base = dirname(textpress.__file__)
    start = len(dirname(base))
    if base != 'textpress':
        start += 1

    for path, dirnames, filenames in os.walk(base):
        for filename in filenames:
            if filename.endswith('.py'):
                fullpath = join(path, filename)
                if filename == '__init__.py':
                    stripped = fullpath[start:-12]
                else:
                    stripped = fullpath[start:-3]

                modname = stripped.replace('/', '.')
                modules.append(modname)
    return modules


def main():
    from optparse import OptionParser
    usage = ('Usage: %prog [option] [modules to be tested]\n'
             'Modules names have to be given in the form utils.mail (without '
             'textpress.)\nIf no module names are given, all tests are run')
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--coverage', action='store_true', dest='coverage',
                      help='show coverage information (slow!)')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
                      default=False, help='show which tests are run')

    options, args = parser.parse_args(sys.argv[1:])
    modnames = ['textpress.' + modname for modname in args]
    if options.coverage:
        if coverage is not None:
            use_coverage = True
        else:
            sys.stderr.write("coverage information requires Ned Batchelder's "
                             "coverage.py to be installed!\n")
            sys.exit(1)
    else:
        use_coverage = False

    if use_coverage:
        s, covermods = suite(True, modnames=modnames)
        coverage.erase()
        coverage.start()
    else:
        s = suite(modnames=modnames)
    TextTestRunner(verbosity=options.verbose + 1).run(s)
    if use_coverage:
        coverage.stop()
        print '\n\n' + '=' * 25 + ' coverage information ' + '=' * 25
        coverage.report(covermods)


if __name__ == '__main__':
    main()
