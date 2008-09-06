# -*- coding: utf-8 -*-
"""
    zine.utils.admin
    ~~~~~~~~~~~~~~~~

    This module implements various functions used by the admin interface.

    :copyright: 2007 by Armin Ronacher, Georg Brandl.
    :license: GNU GPL.
"""
import os
import re
import unicodedata
from time import time
from itertools import islice
from datetime import datetime
from threading import Lock

from werkzeug import url_quote

from zine.utils import _, local, load_json


_punctuation_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|}]+')
_reddit_lock = Lock()
_reddit_cache = (None, 0)

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


def load_zine_reddit():
    """Load the zine reddit."""
    global _reddit_cache
    import urllib
    _reddit_lock.acquire()
    try:
        if _reddit_cache[0] is None or \
           _reddit_cache[1] < time() - 3600:
            reddit_url = 'http://www.reddit.com/r/zine'
            try:
                f = urllib.urlopen(reddit_url + '.json')
                data = load_json(f.read())
            finally:
                f.close()

            result = []
            for item in islice(data['data']['children'], 20):
                d = item['data']
                result.append({
                    'author':       d['author'],
                    'created':      datetime.utcfromtimestamp(d['created']),
                    'score':        d['score'],
                    'title':        d['title'],
                    'comments':     d['num_comments'],
                    'url':          d['url'],
                    'domain':       d['domain'],
                    'author_url':   'http://www.reddit.com/user/%s/' %
                                    url_quote(d['author']),
                    'comment_url':  '%s/comments/%s' % (reddit_url, d['id'])
                })
            _reddit_cache = (result, time())
        return _reddit_cache[0][:]
    finally:
        _reddit_lock.release()


def commit_config_change(t):
    try:
        t.commit()
        return True
    except IOError, e:
        flash(_('The configuration file could not be written.'), 'error')
        return False
