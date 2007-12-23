# -*- coding: utf-8 -*-
"""
    textpress.plugins.notification
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    When a new comment is posted to a blog entry, a mail will be sent to
    the author of the corresponding post.

    :copyright: 2007 by Rafael Weber.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.utils import send_email, format_datetime

SIGNATURE = '''
-- Mail delivered from your TextPress blog.
To stop mailing when new comments are posted, just disable the
"notification" plugin.
'''

def notify(request, comment):
    to_addr = comment.post.author.email
    subject = _('New comment on your blog to "%s" by %s' % (
        comment.post.title,
        comment.author
    ))
    pub_date = format_datetime(comment.pub_date, '%d.%m %H:%M')
    msg = _('%s (%s) wrote at %s:\n\n%s\n%s' % (
        comment.author,
        comment.email,
        pub_date,
        comment.raw_body,
        SIGNATURE
    ))
    send_email(subject, msg, to_addr)

def setup(app, plugin):
    app.connect_event('after-comment-saved', notify)
