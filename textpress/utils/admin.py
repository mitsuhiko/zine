# -*- coding: utf-8 -*-
"""
    textpress.utils.admin
    ~~~~~~~~~~~~~~~~~~~~~

    This module implements various functions used by the admin interface.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import linecache
import math
import os
import re
import unicodedata

from textpress.utils import _, local


_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|}]+')

_tagify_replacement_table = {
    u'\xdf': 'ss',
    u'\xe4': 'ae',
    u'\xe6': 'ae',
    u'\xf0': 'dh',
    u'\xf6': 'oe',
    u'\xfc': 'ue',
    u'\xfe': 'th'
}


def flash(msg, type='info'):
    """Add a message to the message flash buffer.

    The default message type is "info", other possible values are
    "add", "remove", "error", "ok" and "configure". The message type affects
    the icon and visual appearance.

    The flashes messages appear only in the admin interface!
    """
    assert type in ('info', 'add', 'remove', 'error', 'ok', 'configure')
    if type == 'error':
        msg = (u'<strong>%s:</strong> ' % _('Error')) + msg
    local.request.session.setdefault('admin/flashed_messages', []).\
            append((type, msg))


def gen_slug(text):
    """remove accents and make text lowercase."""
    result = []
    for word in _punctuation_re.split(text.lower()):
        if word:
            for search, replace in _tagify_replacement_table.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
    return u'-'.join(result)


try:
    import _ast
except ImportError:
    can_build_eventmap = False
else:
    can_build_eventmap = True


def build_eventmap(app):
    """Walk through all the builtins and plugins for an application and
    look for `emit_event` calls. This is useful for plugin developers that
    want to find possible entry points without having to dig the source or
    missing documentation. Speaking of documentation: This could help for
    that too.
    """
    if not can_build_eventmap:
        raise RuntimeError('this feature requires python 2.5')
    import textpress

    textpress_root = os.path.realpath(os.path.dirname(textpress.__file__))
    searchpath = [(textpress_root, '__builtin__')]

    for plugin in app.plugins.itervalues():
        path = os.path.realpath(plugin.path)
        if os.path.commonprefix([textpress_root, path]) != textpress_root:
            searchpath.append((plugin.path, plugin.name))

    def walk_ast(ast):
        if isinstance(ast, _ast.Call) and \
           isinstance(ast.func, _ast.Name) and \
           ast.func.id in ('emit_event', 'iter_listeners') and \
           ast.args and \
           isinstance(ast.args[0], _ast.Str):
            yield ast.args[0].s, ast.func.lineno
        for field in ast._fields or ():
            value = getattr(ast, field)
            if isinstance(value, (tuple, list)):
                for node in value:
                    if isinstance(node, _ast.AST):
                        for item in walk_ast(node):
                            yield item
            elif isinstance(value, _ast.AST):
                for item in walk_ast(value):
                    yield item

    def find_help(filename, lineno):
        help_lines = []
        lineno -= 1
        while lineno > 0:
            line = linecache.getline(filename, lineno).strip()
            if line.startswith('#!'):
                line = line[2:]
                if line and line[0] == ' ':
                    line = line[1:]
                help_lines.append(line)
            elif line:
                break
            lineno -= 1
        return '\n'.join(reversed(help_lines)).decode('utf-8')

    result = {}
    for folder, prefix in searchpath:
        offset = len(folder)
        for dirpath, dirnames, filenames in os.walk(folder):
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                filename = os.path.join(dirpath, filename)
                shortname = filename[offset:]
                ast = compile(''.join(linecache.getlines(filename)),
                              filename, 'exec', 0x400)

                for event, lineno in walk_ast(ast):
                    help = find_help(filename, lineno)
                    result.setdefault(event, []).append((prefix, shortname,
                                                         lineno, help))

    return result


class Pagination(object):
    """Pagination helper."""

    def __init__(self, endpoint, page, per_page, total, url_args=None):
        self.endpoint = endpoint
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = int(math.ceil(self.total / float(self.per_page)))
        self.url_args = url_args or {}
        self.necessary = self.pages > 1

    def generate(self, normal='<a href="%(url)s">%(page)d</a>',
                 active='<strong>%(page)d</strong>',
                 commata='<span class="commata">,\n</span>',
                 ellipsis=u'<span class="ellipsis"> …\n</span>',
                 threshold=3, prev_link=False,
                 next_link=False, gray_prev_link=True, gray_next_link=True):
        from textpress.application import url_for
        was_ellipsis = False
        result = []
        prev = None
        next = None
        small_threshold = math.ceil(threshold / 2.0)
        get_link = lambda x: url_for(self.endpoint, page=x, **self.url_args)

        for num in xrange(1, self.pages + 1):
            if num == self.page:
                was_ellipsis = False
            if num - 1 == self.page:
                next = num
            if num + 1 == self.page:
                prev = num
            if num <= small_threshold or \
               num > self.pages - small_threshold or \
               abs(self.page - num) < threshold:
                if result and result[-1] != ellipsis:
                    result.append(commata)
                link = get_link(num)
                template = num == self.page and active or normal
                result.append(template % {
                    'url':      link,
                    'page':     num
                })
            elif not was_ellipsis:
                was_ellipsis = True
                result.append(ellipsis)

        if next_link:
            if next is not None:
                result.append(u' <a href="%s">Next &raquo;</a>' %
                              get_link(next))
            elif gray_next_link:
                result.append(u' <span class="disabled">Next &raquo;</span>')
        if prev_link:
            if prev is not None:
                result.insert(0, u'<a href="%s">&laquo; Prev</a> ' %
                              get_link(prev))
            elif gray_prev_link:
                result.insert(0, u'<span class="disabled">&laquo; Prev</span> ')

        return u''.join(result)


def commit_config_change(t):
    try:
        t.commit()
        return True
    except IOError, e:
        flash(_('The configuration file could not be written.'), 'error')
        return False
