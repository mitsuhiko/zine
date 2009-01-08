# -*- coding: utf-8 -*-
"""
    zine.plugins.akismet_spam_filter
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Do spam checking via Akismet of comments.

    :copyright: (c) 2009 by the Zine Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from os.path import dirname, join
from urllib import urlopen

from werkzeug import escape, url_encode

import zine
from zine.api import *
from zine.widgets import Widget
from zine.views.admin import flash, render_admin_response
from zine.models import COMMENT_BLOCKED_SPAM, COMMENT_MODERATED, Comment
from zine.privileges import BLOG_ADMIN, MODERATE_COMMENTS, require_privilege
from zine.utils.validators import ValidationError, check
from zine.utils.http import redirect_to
from zine.utils import forms


USER_AGENT = 'Zine/%s | Akismet/2.0' % zine.__version__
AKISMET_URL_BASE = 'rest.akismet.com'
AKISMET_VERSION = '1.1'
SHARED = join(dirname(__file__), 'shared')
TEMPLATES = join(dirname(__file__), 'templates')
BLOCKED_MSG = _('blocked by akismet')


#: because we need the information about verified keys quite often
#: we store verified keys here.
_verified_keys = set()


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
        f = urlopen(url, url_encode(data))
    except:
        return
    try:
        return f.read().strip()
    finally:
        f.close()


def is_valid_key(message=None, memorize=False):
    """A validator that validates keys."""
    if message is None:
        message = _('The key is invalid.')

    def validate(form, apikey):
        blog_url = get_application().cfg['blog_url']
        cachekey = (apikey, blog_url)
        if cachekey in _verified_keys:
            return

        data = {'key': apikey, 'blog': blog_url}
        resp = send_request(apikey, False, data, 'verify-key')
        if resp is None:
            raise ValidationError(_('Could not verify key because of a '
                                    'server to server connection error.'))
        elif resp != 'valid':
            raise ValidationError(message)
        if memorize:
            _verified_keys.add(cachekey)
    return validate


def get_akismet_key():
    """Return the akismet key for the current application or
    `None` if there is no key or the key is invalid.
    """
    app = get_application()
    key = app.cfg['akismet_spam_filter/apikey']
    if key and check(is_valid_key, key, memorize=True):
        return key

class ConfigurationForm(forms.Form):
    """The configuration form."""
    api_key = forms.TextField(validators=[is_valid_key()])


def build_akismet_data(req, comment):
    """build the akismet data dictionary"""
    apikey = get_akismet_key()
    if apikey is None:
        return None, None

    data = {
        'key':                  apikey,
        'blog':                 get_application().cfg['blog_url'],
        'user_ip':              comment.submitter_ip,
        'user_agent':           USER_AGENT,
        'permalink':            url_for(comment.post), # post's permanent link
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
    return apikey, data


def do_spamcheck(req, comment):
    """Do spamchecking for all new comments."""
    # something blocked the comment already. no need to check for spam then.
    if comment.blocked:
        return

    apikey, data = build_akismet_data(req, comment)
    if not (data or apikey):
        return

    resp = send_request(apikey, True, data, 'comment-check')
    if resp == 'true':
        comment.status = COMMENT_BLOCKED_SPAM
        comment.blocked_msg = BLOCKED_MSG


def do_submit_spam(comment):
    """Contribute to akismet; submit spam."""
    print 'on do_submit_spam'
    # comment is spam, don't submit it to akismet again
    if comment.blocked:
        return

    apikey, data = build_akismet_data(get_request(), comment)
    if not (data or apikey):
        return

    send_request(apikey, True, data, 'submit-spam')
    # Blocking flags will be issued by the form calling this
    flash(_("Comment by %s reported to Akismet") % comment.author)


def do_submit_ham(comment):
    """Contribute to akismet; submit ham."""
    # comment is not spam, don't submit it to akismet
    if not comment.blocked:
        return

    apikey, data = build_akismet_data(get_request(), comment)
    if not (data or apikey):
        return

    send_request(apikey, True, data, 'submit-ham')
    flash(_("Comment by %s reported to Akismet") % comment.author)


def add_akismet_links(req, navigation_bar):
    """Add a button for akismet to the comments page."""
    if req.user.has_privilege(BLOG_ADMIN) or \
                                    req.user.has_privilege(MODERATE_COMMENTS):
        for link_id, url, title, children in navigation_bar:
            if link_id == 'options':
                if req.user.has_privilege(BLOG_ADMIN):
                    children.insert(-3, ('akismet_spam_filter',
                                         url_for('akismet_spam_filter/config'),
                                         _('Akismet')))
            elif link_id == 'comments':
                if req.user.has_privilege(MODERATE_COMMENTS):
                    children.append(('akismet_spam_filter',
                                     url_for('akismet_spam_filter/stats'),
                                     _('Akismet Statistics')))


@require_privilege(BLOG_ADMIN)
def show_akismet_config(req):
    """Show the akismet control panel."""
    form = ConfigurationForm(initial=dict(
        api_key=req.app.cfg['akismet_spam_filter/apikey']
    ))

    if req.method == 'POST' and form.validate(req.form):
        if form.has_changed:
            req.app.cfg.change_single('akismet_spam_filter/apikey',
                                      form['api_key'])
            if form['api_key']:
                flash(_('Akismet has been successfully enabled.'), 'ok')
            else:
                flash(_('Akismet disabled.'), 'ok')
        return redirect_to('akismet_spam_filter/config')
    return render_admin_response('admin/akismet_spam_filter.html',
                                 'options.akismet_spam_filter',
                                 form=form.as_widget())

@require_privilege(MODERATE_COMMENTS)
def show_akismet_stats(req):
    """Show the akismet control panel."""
    api_key = req.app.cfg['akismet_spam_filter/apikey']
    blog_url = 'wikinotification.ufsoft.org' #req.app.cfg['zine/blog_url']

    if req.app.cfg['maintenance_mode']:
        js_file = 'jquery.uicore.plus.tabs.js'
    else:
        js_file = 'jquery.uicore.plus.tabs.packed.js'
    add_script(url_for('akismet/shared', filename=js_file))

    return render_admin_response('admin/akismet_spam_filter_stats.html',
                                 'comments.akismet_spam_filter',
                                 api_key=api_key, blog_url=blog_url)


class AkismetBlockedCommentsCounterWidget(Widget):
    NAME = 'get_akismet_blocked_comments'
    TEMPLATE = 'akismet_widget.html'

    def __init__(self, show_title=False, title=_('Akismet Blocked Comments')):
        self.show_title = show_title
        self.title = title
        self.spam_comments = Comment.objects.filter(
            Comment.blocked_msg == BLOCKED_MSG).count()

    @staticmethod
    def get_display_name():
        return _('Comments Blocked by Akismet')


def setup(app, plugin):
    app.add_config_var('akismet_spam_filter/apikey',
                       forms.TextField(default=u''))
    app.add_url_rule('/options/akismet', prefix='admin',
                     endpoint='akismet_spam_filter/config',
                     view=show_akismet_config)
    app.add_url_rule('/comments/stats', prefix='admin',
                     endpoint='akismet_spam_filter/stats',
                     view=show_akismet_stats)
    app.connect_event('before-comment-saved', do_spamcheck)
    app.connect_event('before-comment-mark-spam', do_submit_spam)
    app.connect_event('before-comment-mark-ham', do_submit_ham)
    app.connect_event('modify-admin-navigation-bar', add_akismet_links)
    app.add_template_searchpath(TEMPLATES)
    app.add_shared_exports('akismet', SHARED)
    app.add_widget(AkismetBlockedCommentsCounterWidget)
