# -*- coding: utf-8 -*-
"""
    zine.utils.admin
    ~~~~~~~~~~~~~~~~

    This module implements various functions used by the admin interface.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import os
from time import time
from itertools import islice
from datetime import datetime

from werkzeug import url_quote

from zine.privileges import ENTER_ADMIN_PANEL, require_privilege
from zine.utils import local, load_json
from zine.utils.net import open_url
from zine.i18n import _


def flash(msg, type='info'):
    """Add a message to the message flash buffer.

    The default message type is "info", other possible values are
    "add", "remove", "error", "ok" and "configure". The message type affects
    the icon and visual appearance.

    The flashes messages appear only in the admin interface!
    """
    assert type in \
        ('info', 'add', 'remove', 'error', 'ok', 'configure', 'warning')
    if type == 'error':
        msg = (u'<strong>%s:</strong> ' % _('Error')) + msg
    if type == 'warning':
        msg = (u'<strong>%s:</strong> ' % _('Warning')) + msg
    
    local.request.session.setdefault('admin/flashed_messages', []).\
            append((type, msg))


def require_admin_privilege(expr=None):
    """Works like `require_privilege` but checks if the rule for
    `ENTER_ADMIN_PANEL` exists as well.
    """
    if expr:
        expr = ENTER_ADMIN_PANEL & expr
    return require_privilege(expr)


def load_zine_reddit():
    """Load the zine reddit."""
    reddit_url = 'http://www.reddit.com'
    reddit_zine_url = reddit_url + '/r/zine'

    response = open_url(reddit_zine_url + '.json')
    try:
        data = load_json(response.data)
    finally:
        response.close()

    result = []
    for item in islice(data['data']['children'], 20):
        d = item['data']
        if not d['url'].startswith("http"):
            d['url'] = reddit_url + d['url']
        result.append({
            'author':       d['author'],
            'created':      datetime.utcfromtimestamp(d['created']),
            'score':        d['score'],
            'title':        d['title'],
            'comments':     d['num_comments'],
            'url':          d['url'],
            'domain':       d['domain'],
            'author_url':   reddit_url + '/user/%s/' %
                            url_quote(d['author']),
            'comment_url':  '%s/comments/%s' % (reddit_zine_url, d['id'])
        })
    return result
