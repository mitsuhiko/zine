# -*- coding: utf-8 -*-
"""
    textpress.plugins.file_uploads
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Allows to upload files into a web visible folder.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
import re
from os import listdir, makedirs, remove
from os.path import dirname, join, exists, getsize, sep as pathsep
from shutil import copyfileobj
from time import asctime, gmtime, time
from mimetypes import guess_type
from fnmatch import fnmatch
from weakref import WeakKeyDictionary
from textpress.api import *
from textpress.utils import CSRFProtector, IntelligentRedirect, \
     make_hidden_fields, escape, dump_json
from textpress.models import ROLE_AUTHOR, ROLE_ADMIN
from textpress.views.admin import render_admin_response, flash
from textpress.utils import StreamReporter


TEMPLATES = join(dirname(__file__), 'templates')
SHARED = join(dirname(__file__), 'shared')


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
    return join(app.instance_folder, app.cfg['file_uploads/upload_folder'])


def get_filename(s):
    return pathsep.join(x for x in [get_upload_folder()] + s.split('/')
                        if x not in ('.', '..'))


def list_files():
    folder = get_upload_folder()
    if not exists(folder):
        return []
    return [{
        'filename':     file,
        'size':         getsize(join(folder, file)),
        'mimetype':     guess_mimetype(file)
    } for file in sorted(listdir(folder))]


def add_links(req, navigation_bar):
    items =  [
        ('browse', url_for('file_uploads/browse'), _('Browse')),
        ('upload', url_for('file_uploads/upload'), _('Upload'))
    ]
    if req.user.role >= ROLE_ADMIN:
        items.append(('config', url_for('file_uploads/config'),
                      _('Configure')))

    for pos, (link_id, url, title, children) in enumerate(navigation_bar):
        if link_id == 'posts':
            navigation_bar.insert(pos + 1, ('file_uploads',
                url_for('file_uploads/browse'), _('Uploads'), items))
            break


@require_role(ROLE_AUTHOR)
def upload_file(req):
    csrf_protector = CSRFProtector()
    reporter = StreamReporter()
    add_script(url_for('file_uploads/shared', filename='uploads.js'))
    add_link('stylesheet', url_for('file_uploads/shared', filename='style.css'),
             'text/css')
    add_header_snippet(
        '<script type="text/javascript">'
            '$TRANSPORT_ID = %s'
        '</script>' % escape(dump_json(reporter.transport_id))
    )

    if req.method == 'POST':
        csrf_protector.assert_safe()

        f = req.files['file']
        folder = get_upload_folder()
        if not exists(folder):
            try:
                makedirs(folder)
            except (OSError, IOError):
                flash(_('Could not create upload target folder %s.') %
                      escape(folder), 'error')
                redirect(url_for('file_uploads/upload'))

        filename = req.form.get('filename') or f.filename
        dst_filename = join(folder, filename)

        if not f:
            flash(_('No file uploaded.'))
        elif pathsep in filename:
            flash(_('Invalid filename requested.'))
        elif exists(dst_filename) and not req.form.get('overwrite'):
            flash(_('A file with the filename %s exists already.') % (
                u'<a href="%s">%s</a>' % (
                    escape(url_for('file_uploads/get_file',
                                   filename=filename)),
                    escape(filename)
                )))
        else:
            dst = file(dst_filename, 'wb')
            try:
                copyfileobj(f, dst)
            finally:
                dst.close()
            flash(_('File %s uploaded successfully.') % (
                  u'<a href="%s">%s</a>' % (
                      escape(url_for('file_uploads/get_file',
                                     filename=filename)),
                      escape(filename))))
        redirect(url_for('file_uploads/upload'))

    return render_admin_response('admin/file_uploads/upload.html',
                                 'file_uploads.upload',
        csrf_protector=csrf_protector,
        reporter=reporter
    )


@require_role(ROLE_AUTHOR)
def browse_uploads(req):
    return render_admin_response('admin/file_uploads/browse.html',
                                 'file_uploads.browse',
        files=list_files()
    )


@require_role(ROLE_ADMIN)
def configure(req):
    csrf_protector = CSRFProtector()
    form = {
        'upload_dest':  req.app.cfg['file_uploads/upload_folder'],
        'mimetypes':    u'\n'.join(req.app.cfg['file_uploads/mimetypes'].
                                   split(';'))
    }
    if req.method == 'POST':
        csrf_protector.assert_safe()
        upload_dest = form['upload_dest'] = req.form.get('upload_dest', '')
        if upload_dest != req.app.cfg['file_uploads/upload_folder']:
            req.app.cfg['file_uploads/upload_folder'] = upload_dest
            flash(_('Upload folder changed successfully.'))
        mimetypes = form['mimetypes'] = req.form.get('mimetypes', '')
        mimetypes = ';'.join(mimetypes.splitlines())
        if mimetypes != req.app.cfg['file_uploads/mimetypes']:
            req.app.cfg['file_uploads/mimetypes'] = mimetypes
            if req.app in _mimetype_cache:
                del _mimetype_cache[req.app][:]
            flash(_('Upload mimetype mapping altered successfully.'))
        redirect(url_for('file_uploads/config'))

    return render_admin_response('admin/file_uploads/config.html',
                                 'file_uploads.config',
        form=form,
        csrf_protector=csrf_protector
    )


def get_file(req, filename):
    filename = get_filename(filename)
    if not exists(filename):
        abort(404)
    guessed_type = guess_mimetype(filename)
    fp = file(filename, 'rb')
    def stream():
        try:
            while True:
                chunk = fp.read(1024 * 512)
                if not chunk:
                    break
                yield chunk
        finally:
            fp.close()
    resp = Response(stream(), mimetype=guessed_type or 'text/plain')
    resp.headers['Cache-Control'] = 'public'
    resp.headers['Expires'] = asctime(gmtime(time() + 3600))
    return resp


@require_role(ROLE_AUTHOR)
def delete_file(req, filename):
    fs_filename = get_filename(filename)
    if not exists(fs_filename):
        abort(404)

    csrf_protector = CSRFProtector()
    redirect = IntelligentRedirect()

    if req.method == 'POST':
        csrf_protector.assert_safe()
        if req.form.get('confirm'):
            try:
                remove(fs_filename)
            except (OSError, IOError):
                flash(_('Could not delete file %s.') %
                      escape(filename), 'error')
            else:
                flash(_('File %s deleted successfully.') %
                      escape(filename), 'remove')
        redirect('file_uploads/browse')

    return render_admin_response('admin/file_uploads/delete.html',
                                 'file_uploads.browse',
        hidden_form_data=make_hidden_fields(csrf_protector, redirect),
        filename=filename
    )


def setup(app, plugin):
    app.add_config_var('file_uploads/upload_folder', unicode, 'uploads')
    app.add_config_var('file_uploads/mimetypes', unicode,
                       '*.plugin:application/x-textpress-plugin')
    app.connect_event('modify-admin-navigation-bar', add_links)
    app.add_url_rule('/admin/uploads/', endpoint='file_uploads/browse'),
    app.add_url_rule('/admin/uploads/new', endpoint='file_uploads/upload')
    app.add_url_rule('/admin/uploads/config', endpoint='file_uploads/config')
    app.add_url_rule('/_uploads/<filename>', endpoint='file_uploads/get_file')
    app.add_url_rule('/_uploads/<filename>/delete',
                     endpoint='file_uploads/delete')
    app.add_view('file_uploads/browse', browse_uploads)
    app.add_view('file_uploads/upload', upload_file)
    app.add_view('file_uploads/config', configure)
    app.add_view('file_uploads/get_file', get_file)
    app.add_view('file_uploads/delete', delete_file)
    app.add_template_searchpath(TEMPLATES)
    app.add_shared_exports('file_uploads', SHARED)
