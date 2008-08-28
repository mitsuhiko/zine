# -*- coding: utf-8 -*-
"""
    zine.utils.admin
    ~~~~~~~~~~~~~~~~

    This module implements various functions used by the admin interface.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import math
import os
import re
import unicodedata

from zine.utils import _, local


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


def gen_slug(text, delim='-'):
    """remove accents and make text lowercase."""
    result = []
    for word in _punctuation_re.split(text.lower()):
        if word:
            for search, replace in _tagify_replacement_table.iteritems():
                word = word.replace(search, replace)
            word = unicodedata.normalize('NFKD', word)
            result.append(word.encode('ascii', 'ignore'))
    return unicode(delim.join(result))


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
                 threshold=3, left_threshold=2, right_threshold=1,
                 prev_link=False, next_link=False, gray_prev_link=True,
                 gray_next_link=True):
        from zine.application import url_for
        was_ellipsis = False
        result = []
        prev = None
        next = None
        get_link = lambda x: url_for(self.endpoint, page=x, **self.url_args)

        for num in xrange(1, self.pages + 1):
            if num == self.page:
                was_ellipsis = False
            if num - 1 == self.page:
                next = num
            if num + 1 == self.page:
                prev = num
            if num <= left_threshold or \
               num > self.pages - right_threshold or \
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
