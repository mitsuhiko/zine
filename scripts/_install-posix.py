# -*- coding: utf-8 -*-
"""
    POSIX Installation
    ~~~~~~~~~~~~~~~~~~

    This script is invoked by the makefile to install Zine on a POSIX system.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
import shutil
from subprocess import call as run


join = os.path.join


PACKAGES = '_dynamic _ext importers utils views websetup docs'.split()
SCRIPTS = 'create-apache-config server shell'.split()
DESTDIR = os.environ.get('DESTDIR')

if DESTDIR is not None:
    DESTDIR = os.path.abspath(DESTDIR)


def silent(f, *args):
    try:
        return f(*args)
    except:
        pass


def rel_path(path, start):
    start_list = os.path.abspath(start).split(os.path.sep)
    path_list = os.path.abspath(path).split(os.path.sep)
    offset = len(os.path.commonprefix([start_list, path_list]))
    parts = [os.path.pardir] * (len(start_list) - offset) + path_list[offset:]
    if not parts:
        return os.path.curdir
    return join(*parts)


def rel_symlink(src, dst):
    os.symlink(rel_path(src, os.path.dirname(dst)), dst)


def copy_folder(src, dst, recurse=True, skip=(), delete_if_exists=False):
    if delete_if_exists and os.path.exists(dst):
        shutil.rmtree(dst)
    silent(os.makedirs, dst)
    for localname in os.listdir(src):
        if localname in skip:
            continue
        filename = join(src, localname)
        if os.path.isfile(filename):
            shutil.copy2(filename, dst)
        elif recurse:
            dst_folder = join(dst, localname)
            shutil.copytree(filename, dst_folder)


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
                    lines[idx] = 'ZINE_LIB = %r\n' % strip_destdir(lib_dir)
                    break
        finally:
            f.close()
        f = file(join(destination, filename), 'w')
        try:
            f.write(''.join(lines))
        finally:
            f.close()


def copy_core_translations(src_dir, lib_dir, share_dir):
    copy_folder(src_dir, lib_dir, recurse=False, delete_if_exists=True)
    if os.path.exists(share_dir):
        shutil.rmtree(share_dir)
    os.makedirs(share_dir)
    for language in os.listdir(src_dir):
        lang_src = join(src_dir, language, 'messages.mo')
        if not os.path.isfile(lang_src):
            continue
        lang_share_dir = join(share_dir, language, 'LC_MESSAGES')
        silent(os.makedirs, lang_share_dir)
        shutil.copy2(lang_src, join(lang_share_dir, 'zine.mo'))


def copy_plugins(src_dir, lib_dir, share_dir):
    for path in lib_dir, join(share_dir, 'plugins'):
        if os.path.exists(path):
            shutil.rmtree(path)
    for plugin in os.listdir(src_dir):
        plugin_src_dir = join(src_dir, plugin)
        plugin_lib_dir = join(lib_dir, plugin)

        # plugin code
        copy_folder(plugin_src_dir, plugin_lib_dir,
                    skip=frozenset(('shared', 'templates')))

        # plugin web data and templates
        for folder, new_folder in ('shared', 'htdocs'), \
                                  ('templates', 'templates'):
            src_folder = join(plugin_src_dir, folder)
            if os.path.exists(src_folder):
                dst_folder = join(share_dir, new_folder, plugin)
                copy_folder(src_folder, dst_folder, delete_if_exists=True)
                lib_folder = join(plugin_lib_dir, folder)
                rel_symlink(dst_folder, lib_folder)


def copy_scripts(source, destination, lib_dir):
    silent(os.makedirs, destination)
    f = file(join(source, '_init_zine.py'))
    try:
        contents = f.read().replace('ZINE_LIB = None',
                                    'ZINE_LIB = %r' % strip_destdir(lib_dir))
    finally:
        f.close()
    f = file(join(destination, '_init_zine.py'), 'w')
    try:
        f.write(contents)
    finally:
        f.close()
    for script in SCRIPTS:
        shutil.copy2(join(source, script), destination)


def strip_destdir(path):
    if DESTDIR is None or not path.startswith(DESTDIR):
        return path
    return path[len(DESTDIR):]


def main(prefix):
    if DESTDIR is not None:
        dest_dir = join(DESTDIR, prefix.lstrip('/'))
    else:
        dest_dir = prefix

    python = sys.executable
    source = os.path.abspath('.')
    zine_source = join(source, 'zine')
    lib_dir = join(dest_dir, 'lib', 'zine')
    share_dir = join(dest_dir, 'share', 'zine')

    print 'Installing to ' + dest_dir
    print 'Using ' + python

    # create some folders for us
    silent(os.makedirs, join(lib_dir, 'zine'))
    silent(os.makedirs, share_dir)

    # copy the packages and modules into the zine package
    copy_folder(zine_source, join(lib_dir, 'zine'),
                recurse=False, delete_if_exists=True)
    for package in PACKAGES:
        copy_folder(join(zine_source, package),
                    join(lib_dir, 'zine', package))

    # old zine installations had the translations at a different
    # location.  Delete them if we find them there.
    old_translations = join(share_dir, 'i18n')
    if os.path.isdir(old_translations):
        os.rmtree(old_translations)

    # copy the core translations
    copy_core_translations(join(zine_source, 'i18n'),
                           join(lib_dir, 'zine', 'i18n'),
                           join(dest_dir, 'share', 'locale'))

    # copy the plugins over
    copy_plugins(join(zine_source, 'plugins'),
                 join(lib_dir, 'plugins'),
                 share_dir)

    # compile all files
    run([sys.executable, '-O', '-mcompileall', '-qf',
         join(lib_dir, 'zine'), join(lib_dir, 'plugins')])

    # templates and shared data
    copy_folder(join(zine_source, 'shared'),
                join(share_dir, 'htdocs', 'core'), delete_if_exists=True)
    copy_folder(join(zine_source, 'templates'),
                join(share_dir, 'templates', 'core'), delete_if_exists=True)

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
