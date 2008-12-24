# -*- coding: utf-8 -*-
"""
    POSIX Installation
    ~~~~~~~~~~~~~~~~~~

    This script is invoked by the makefile to install Zine on a POSIX system.

    :copyright: 2008 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
import shutil
from subprocess import call as run


join = os.path.join


PACKAGES = '_dynamic _ext importers utils views websetup i18n docs'.split()
SCRIPTS = 'create-apache-config server shell'.split()


def silent(f, *args):
    try:
        return f(*args)
    except:
        pass


def copy_folder(src, dst, recurse=True):
    if recurse:
        shutil.copytree(src, dst)
    else:
        for filename in os.listdir(src):
            filename = join(src, filename)
            if os.path.isfile(filename):
                shutil.copy2(filename, dst)


def copy_servers(source, destination, lib_dir, python):
    silent(os.makedirs, destination)
    for filename in os.listdir(source):
        f = file(join(source, filename))
        try:
            lines = list(f)
            if lines[0].startswith('#!'):
                lines[0] = '#!%s\n' % python
            for idx, line in enumerate(lines):
                if line.startswith('ZINE_LIB ='):
                    lines[idx] = 'ZINE_LIB = %r\n' % lib_dir
                    break
        finally:
            f.close()
        f = file(join(destination, filename), 'w')
        try:
            f.write(''.join(lines))
        finally:
            f.close()


def copy_scripts(source, destination, lib_dir):
    silent(os.makedirs, destination)
    f = file(join(source, '_init_zine.py'))
    try:
        contents = f.read().replace('ZINE_LIB = None',
                                    'ZINE_LIB = %r' % lib_dir)
    finally:
        f.close()
    f = file(join(destination, '_init_zine.py'), 'w')
    try:
        f.write(contents)
    finally:
        f.close()
    for script in SCRIPTS:
        shutil.copy2(join(source, script), destination)


def main(prefix):
    python = sys.executable
    source = os.path.abspath('.')
    zine_source = join(source, 'zine')
    lib_dir = join(prefix, 'lib', 'zine')
    share_dir = join(prefix, 'share', 'zine')

    print 'Installing to ' + prefix
    print 'Using ' + python

    # create some folders for us
    silent(os.makedirs, join(lib_dir, 'zine'))
    silent(os.makedirs, share_dir)

    # copy the packages and modules into the zine package
    copy_folder(zine_source, join(lib_dir, 'zine'),
                recurse=False)
    for package in PACKAGES:
        copy_folder(join(zine_source, package),
                    join(lib_dir, 'zine', package))

    # copy the plugins over
    copy_folder(join(zine_source, 'plugins'),
                join(lib_dir, 'plugins'))

    # compile all files
    run([sys.executable, '-O', '-mcompileall', '-qf',
         join(lib_dir, 'zine'), join(lib_dir, 'plugins')])

    # templates and shared data
    copy_folder(join(zine_source, 'shared'),
                join(share_dir, 'htdocs'))
    copy_folder(join(zine_source, 'templates'),
                join(share_dir, 'templates'))

    # copy the server files
    copy_servers(join(source, 'servers'),
                 join(share_dir, 'servers'), lib_dir, python)

    # copy the scripts
    copy_scripts(join(source, 'scripts'),
                 join(share_dir, 'scripts'), lib_dir)
    print 'All done.'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print >> sys.stderr, 'error: install script only accepts a prefix'
        sys.exit(1)
    os.chdir(os.path.join(os.path.dirname(__file__), '..'))
    main(sys.argv[1])
