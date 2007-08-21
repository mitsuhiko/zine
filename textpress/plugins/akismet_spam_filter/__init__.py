# -*- coding: utf-8 -*-
"""
    textpress.plugins.akismet_spam_filter
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Do spam checking via Akismet of comments.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
import textpress
from os.path import dirname, join
from textpress.api import *
from textpress.views.admin import flash, render_admin_response
from textpress.utils import escape, CSRFProtector, RequestLocal
from urllib import urlencode, urlopen

USER_AGENT = 'TextPress /%s | Akismet/1.11' % textpress.__version__
AKISMET_URL_BASE = 'rest.akismet.com'
AKISMET_VERSION = '1.1'
TEMPLATES = join(dirname(__file__), 'templates')

#: because we need the information about verified keys on every
#: admin page and after every tested comment it's a bad idea to
#: check for a valid key all the time. Once a key is approved it's
#: stored here to skip the testing.
_verified_keys = set()

#: the admin global flash message needs to know if it's on the
#: akismet configuration page to hide unneeded information
_locals = RequestLocal(on_akismet_page=bool)


class InvalidKey(ValueError):
    """Raised with a message if the key is invalid."""

    def __init__(self, message):
        self.message = message
        ValueError.__init__(self, message)


def send_request(apikey, key_root, data, endpoint):
    """Send a request to the akismet server and return the response."""
    url = 'http://%s%s/%s/%s' % (
        key_root and apikey + '.' or '',
        AKISMET_URL_BASE,
        AKISMET_VERSION,
        endpoint
    )
    try:
        f = urlopen(url, urlencode(data))
    except:
        return
    try:
        return f.read().strip()
    finally:
        f.close()


def get_verified_key():
    """
    Get the current key and blog url from the configuration, validate
    it and return it as tuple. If the key is not valid the return
    value is (None, None).
    """
    app = get_application()
    apikey = app.cfg['akismet_spam_filter/apikey'].encode('utf-8')
    if not apikey:
        raise InvalidKey(_('No Akismet key provided.'))
    blogurl = app.cfg['blog_url'].encode('utf-8')
    cachekey = (apikey, blogurl)
    if cachekey not in _verified_keys:
        data = {'key': apikey, 'blog': blogurl}
        resp = send_request(apikey, False, data, 'verify-key')
        if resp is None:
            raise InvalidKey(_('Could not verfiy key because of a '
                               'server to server connection error.'))
        elif resp != 'valid':
            raise InvalidKey(_('The key you have entered is not valid.'))
        _verified_keys.add(cachekey)
    return apikey, blogurl


def test_apikey(req, context):
    """
    If the key is invalid we better inform the admin about it.
    """
    try:
        get_verified_key()
    except InvalidKey, e:
        msg = _('<strong>Akismet is not active!</strong>')
        msg += ' ' + e.message
        if not _locals.on_akismet_page:
            msg += u' <a href="%s">%s</a>' % (
                escape(url_for('akismet_spam_filter/config')),
                _('Edit key')
            )
        flash(msg, 'error')


def do_spamcheck(req, comment):
    """Do spamchecking for all new comments."""
    # something blocked the comment already. no need to check for
    # spam then.
    if comment.blocked:
        return

    try:
        apikey, blog = get_verified_key()
    except InvalidKey:
        # if we cannot verify the key we just fail silently.
        # we don't want that the blog users sees a stupid error
        return

    data = {
        'key':                  apikey,
        'blog':                 blog,
        'user_ip':              comment.submitter_ip,
        'user_agent':           USER_AGENT,
        'comment_type':         'comment',
        'comment_author':       comment.author,
        'comment_author_email': comment.email,
        'comment_author_url':   comment.www,
        'comment_content':      comment.body
    }

    # if we have a request object for testing we can provide some
    # more information for akismet.
    if req is not None:
        data['referrer'] = req.environ.get('HTTP_REFERER', '')
        for key in 'SERVER_ADDR', 'SERVER_NAME', 'SERVER_PORT', \
                   'SERVER_SOFTWARE', 'HTTP_ACCEPT', 'REMOTE_ADDR':
            data[key] = req.environ.get(key, '')

    resp = send_request(apikey, True, data, 'comment-check')
    if resp == 'true':
        comment.blocked = True
        comment.blocked_msg = 'blocked by akismet'


def add_akismet_link(navigation_bar):
    """Add a button for akismet to the comments page."""
    for link_id, url, title, children in navigation_bar:
        if link_id == 'comments':
            children.append(('akismet_spam_filter',
                             url_for('akismet_spam_filter/config'),
                             _('Akismet Configuration')))


def show_akismet_config(req):
    """Show the akismet control panel."""
    _locals.on_akismet_page = True
    csrf_protector = CSRFProtector()

    if req.method == 'POST':
        req.app.cfg['akismet_spam_filter/apikey'] = \
            req.form.get('api_key', '')
        try:
            get_verified_key()
        except InvalidKey:
            # do nothing if the key is broken, there is already a admin
            # panel global alert box provided by `test_apikey`
            pass
        else:
            # the key is valid, show a box
            flash(_('Akismet enabled successfully. The API key provided '
                    'is valid'), 'ok')
        redirect(url_for('akismet_spam_filter/config'))
    return render_admin_response('admin/akismet_spam_filter.html',
                                 'comments.akismet_spam_filter',
        api_key=req.app.cfg['akismet_spam_filter/apikey'],
        csrf_protector=csrf_protector
    )


def setup(app, plugin):
    app.add_config_var('akismet_spam_filter/apikey', unicode, u'')
    app.add_url_rule('/admin/comments/akismet',
                     endpoint='akismet_spam_filter/config')
    app.add_view('akismet_spam_filter/config', show_akismet_config)
    app.connect_event('before-comment-saved', do_spamcheck)
    app.connect_event('before-admin-response-rendered', test_apikey)
    app.connect_event('modify-admin-navigation-bar', add_akismet_link)
    app.add_template_searchpath(TEMPLATES)
