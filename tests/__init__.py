# -*- coding: utf-8 -*-
"""
    Zine Test Suite
    ~~~~~~~~~~~~~~~

    This is the Zine test suite. It collects all modules in the zine
    package, builds a TestSuite with their doctests and executes them. It also
    collects the tests from the text files in this directory (which are too
    extensive to put them into the code without cluttering it up).

    Please note that coverage reporting and doctest don't play well together
    and your reports will probably miss some of the executed code. Doctest can
    be patched to remove this incompatibility, the patch is at
    http://tinyurl.com/doctest-patch

    :copyright: 2009 by Lukas Meuser.
    :license: BSD, see LICENSE for more details.
"""

import sys
import os
from os.path import join, dirname
from unittest import TestSuite, TextTestRunner
from doctest import DocTestSuite, DocFileSuite

#: the modules in this list are not tested in a full run
untested = ['zine.broken_plugins.hyphenation_en',
            'zine.broken_plugins.hyphenation_en.hyphenate',
            'zine.broken_plugins.notification']

try:
    import coverage
except ImportError:
    coverage = None


def suite(modnames=[], return_covermods=False):
    """Generate the test suite.

    The first argument is a list of modules to be tested. If it is empty (which
    it is by default), all sub-modules of the zine package are tested.
    If the second argument is True, this function returns two objects: a
    TestSuite instance and a list of the names of the tested modules. Otherwise
    (which is the default) it only returns the former. This is done so that
    this function can be used as setuptools' test_suite.
    """

    # the app object is used for two purposes:
    # 1) plugins are not usable (i.e. not testable) without an initialised app
    # 2) for functions that require an application object as argument, you can
    #    write >>> my_function(app, ...) in the tests
    # The instance directory of this object is located in the tests directory.
    #
    # setup isn't imported at module level because this way coverage
    # can track the whole zine imports
    from zine import setup
    instance_path = join(dirname(__file__), 'instance')
    app = setup(instance_path)

    if return_covermods:
        covermods = []
    suite = TestSuite()

    if modnames == []:
        modnames = find_tp_modules()
    test_files = os.listdir(dirname(__file__))
    for modname in modnames:
        if modname in untested:
            continue

        # the fromlist must contain something, otherwise the zine
        # package is returned, not our module
        try:
            mod = __import__(modname, None, None, [''])
        except ImportError:
            # some plugins can have external dependencies (e.g. creoleparser,
            # pygments) that are not installed on the machine the tests are
            # run on. Therefore, just skip those (with an error message)
            if 'plugins.' in modname:
                sys.stderr.write('could not import plugin %s\n' % modname)
                continue
            else:
                raise

        suites = [DocTestSuite(mod, extraglobs={'app': app})]
        filename = modname[10:] + '.txt'
        if filename in test_files:
            globs = {'app': app}
            globs.update(mod.__dict__)
            suites.append(DocFileSuite(filename, globs=globs))
        for i, subsuite in enumerate(suites):
            # skip modules without any tests
            if subsuite.countTestCases():
                suite.addTest(subsuite)
                if return_covermods and i == 0:
                    covermods.append(mod)
    if return_covermods:
        return suite, covermods
    else:
        return suite


def find_tp_modules():
    """Find all sub-modules of the zine package."""
    modules = []
    import zine
    base = dirname(zine.__file__)
    start = len(dirname(base))
    if base != 'zine':
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
             'zine.)\nIf no module names are given, all tests are run')
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--coverage', action='store_true', dest='coverage',
                      help='show coverage information (slow!)')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
                      default=False, help='show which tests are run')

    options, args = parser.parse_args(sys.argv[1:])
    modnames = ['zine.' + modname for modname in args]
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
        coverage.erase()
        coverage.start()
        s, covermods = suite(modnames, True)
    else:
        s = suite(modnames)
    TextTestRunner(verbosity=options.verbose + 1).run(s)
    if use_coverage:
        coverage.stop()
        print '\n\n' + '=' * 25 + ' coverage information ' + '=' * 25
        coverage.report(covermods)


if __name__ == '__main__':
    main()
