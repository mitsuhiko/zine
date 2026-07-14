# -*- coding: utf-8 -*-
"""
    zine.utils.admin
    ~~~~~~~~~~~~~~~~

    This module implements various functions used by the admin interface.

    :copyright: (c) 2010 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from itertools import islice

from zine._compat import url_quote

from zine.privileges import ENTER_ADMIN_PANEL, require_privilege
from zine.utils import local, load_json
from zine.utils.net import NetException, open_url
from zine.utils.dates import utcfromtimestamp
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
    else:
        expr = ENTER_ADMIN_PANEL
    return require_privilege(expr)


def load_zine_reddit():
    """Load the Zine subreddit without breaking the admin dashboard."""
    reddit_url = 'https://www.reddit.com'
    reddit_zine_url = reddit_url + '/r/zine'
    try:
        response = open_url(
            reddit_zine_url + '.json?raw_json=1',
            headers={
                'Accept': 'application/json',
                'User-Agent': 'Zine/0.2 (+https://github.com/mitsuhiko/zine)',
            },
        )
    except NetException:
        return []

    try:
        if response.status_code != 200:
            return []
        try:
            data = load_json(response.data)
            children = data['data']['children']
        except (KeyError, TypeError, ValueError):
            return []
    finally:
        response.close()

    result = []
    for item in islice(children, 20):
        try:
            data = item['data']
            author = data['author']
            url = data['url']
            if not url.startswith(('http://', 'https://')):
                url = reddit_url + url
            permalink = data.get('permalink')
            if permalink:
                comment_url = reddit_url + permalink
            else:
                comment_url = '%s/comments/%s' % (
                    reddit_zine_url, data['id']
                )
            created = data.get('created_utc')
            if created is None:
                created = data['created']
            result.append({
                'author': author,
                'created': utcfromtimestamp(created),
                'score': data['score'],
                'title': data['title'],
                'comments': data['num_comments'],
                'url': url,
                'domain': data['domain'],
                'author_url': reddit_url + '/user/%s/' % url_quote(author),
                'comment_url': comment_url,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return result
