# -*- coding: utf-8 -*-
"""
    _make-setup-virtualenv.py
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Execute this file to regenerate the `setup-virtualenv` script.

    :copyright: Copyright 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import os
from virtualenv import create_bootstrap_script


FILENAME = 'setup-virtualenv'
CODE = '''
import os
import sys
from subprocess import call

REQUIREMENTS = [
    'Werkzeug>=0.4',
    'Jinja2>=2.1',
    'SQLAlchemy==dev',
    'pytz',
    'Babel>=0.9.4',
    'lxml>=2.0'
]

# for python 2.4/2.5 we want simplejson installed too.
if sys.version_info < (2, 6):
    REQUIREMENTS.append('simplejson')

# os x has some problems with lxml, make sure the user has port installed
# so that we can compile lxml
if sys.platform == 'darwin':
    print '=' * 60
    print 'It appears that you are using OS X.  If an installation error'
    print 'occurs on installing lxml, please make sure you have port'
    print 'installed and execute the following command:'
    print
    print '    $ port install libxml2 libxslt'
    print '=' * 60

def install(home_dir, *args):
    call([os.path.join(home_dir, 'bin', 'easy_install')] + list(args))

def after_install(options, home_dir):
    site_packages = os.path.normpath(os.path.join(home_dir, 'lib', 'python%%d.%%d'
        %% sys.version_info[:2], 'site-packages'))
    for requirement in REQUIREMENTS:
        install(home_dir, requirement)
    call(['ln', '-s', %(zine_path)r, os.path.join(site_packages, 'zine')])
'''


if __name__ == '__main__':
    os.chdir(os.path.dirname(__file__) or '.')
    f = file(FILENAME, 'w')
    try:
        f.write(create_bootstrap_script(CODE % {
            'zine_path':    os.path.normpath(os.path.join('..', 'zine'))
        }))
    finally:
        f.close()
    os.chmod(FILENAME, 0755)
