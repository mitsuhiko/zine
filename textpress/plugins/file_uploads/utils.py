# -*- coding: utf-8 -*-
"""
    textpress.plugins.file_uploads.utils
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Various utilitites for the file upload plugin (thumbnailer etc)

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
import re
from os import path, listdir, makedirs
from fnmatch import fnmatch
from subprocess import Popen, PIPE
from shutil import copyfileobj
from mimetypes import guess_type
from textpress.api import *


_im_version_re = re.compile(r'^version:\s+imagemagick\s+([\d.]+)(?i)')


def guess_mimetype(s):
    app = get_application()
    for item in app.cfg['file_uploads/mimetypes'].split(';'):
        if ':' in item:
            pattern, mimetype = item.split(':', 1)
            if fnmatch(s, pattern):
                return mimetype
    return guess_type(s)[0] or 'text/plain'


def get_upload_folder():
    app = get_application()
    return path.join(app.instance_folder,
                     app.cfg['file_uploads/upload_folder'])


def touch_upload_folder():
    folder = get_upload_folder()
    if path.exists(folder):
        return True
    try:
        makedirs(folder)
    except (IOError, OSError), e:
        return False


def get_filename(s):
    return path.sep.join(x for x in [get_upload_folder()] + s.split('/')
                         if x not in ('.', '..'))


def file_exists(filename):
    return path.exists(path.join(get_upload_folder(), filename))


def list_files():
    folder = get_upload_folder()
    if not path.exists(folder):
        return []
    return [{
        'filename':     file,
        'size':         path.getsize(path.join(folder, file)),
        'mimetype':     guess_mimetype(file)
    } for file in sorted(listdir(folder))]


def list_images():
    return [x for x in list_files() if x['mimetype'].startswith('image/')]


def upload_file(stream, filename):
    """Upload a stream as upload with a given filename."""
    folder = get_upload_folder()
    dst = file(path.join(folder, filename), 'wb')
    try:
        if isinstance(stream, str):
            dst.write(stream)
        else:
            copyfileobj(stream, dst)
    finally:
        dst.close()


def create_thumbnail(stream, width, height=None, method='normal',
                     quality=90, enhance=True):
    """
    Create a thumbnail. The source must be a stream, the return value will be
    a bytestring. Allowed methods:

    - `normal`      normal thumbnail. width and height are maximum values. If
                    That is, the image is expanded or contracted to fit the
                    width and height value while maintaining the aspect ratio
                    of the image.
    - `force`       Like normal but enforces the width and height. This will
                    most likely result in wrong aspect ratios.

    If the height is not given only the width matters for `normal` and force,
    but the width is used for the height in the `adaptive` method.

    The thumbnail will be a jpeg file with the quality provided.
    """
    if method not in ('normal', 'force'):
        raise ValueError('unknown method %r' % method)

    args = ['-thumbnail', '%sx%s%s' % (
        width,
        height is not None and str(height) or '',
        method == 'force' and '!' or ''
    )]

    if enhance:
        args = ['-enhance'] + args + ['-adaptive-sharpen', '1']
    args = ['-'] + args + ['-quality', str(quality), 'jpeg:-']

    im = open_im(*args)
    copyfileobj(stream, im.stdin)
    im.stdin.close()
    try:
        return im.stdout.read()
    finally:
        im.stdout.close()
        im.stderr.close()
        im.wait()


def get_im_path():
    app = get_application()
    return app.cfg['file_uploads/im_path']


def get_im_executable():
    return path.join(get_im_path(), 'convert')


def open_im(*args):
    return Popen([get_im_executable()] + list(args),
                 stdout=PIPE, stdin=PIPE, stderr=PIPE)


def get_im_version():
    """
    Get the installed im version or None if there is no
    compatible im version installed.
    """
    try:
        im = open_im('-version')
    except OSError:
        return None
    im.stdin.close()
    im.stderr.close()
    m = _im_version_re.search(im.stdout.read())
    im.stdout.close()
    im.wait()
    return m and m.group(1) or None
