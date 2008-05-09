# -*- coding: utf-8 -*-
"""
    textpress.plugins.notification
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    When a new comment is posted to a blog entry, a mail will be sent to
    the author of the corresponding post.

    :copyright: 2007-2008 by Rafael Weber, Pedro Algarvio.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.models import User, ROLE_AUTHOR
from textpress.utils import send_email, format_datetime, is_valid_email

SIGNATURE = '''
-- Mail delivered from your TextPress blog.
To stop mailing when new comments are posted, just disable the
"notification" plugin.
'''


def notify(request, comment):
    if not request.user.username == comment.author:
        #! Only notify if logged in user is not the same as the post's author
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
        if is_valid_email(to_addr):
            send_email(subject, msg, to_addr)


def moderate_comments_notify(request, comment):
    #! Notification to Admins/Managers about unmoderated comments
    unmoderated_comments = comment.objects.get_unmoderated_count()
    if unmoderated_comments:
        subject = _('Unmoderated Comments')
        msg = _('There are %d comments awaiting moderation.\n'
                'You can review them on:\n  %s\n%s' % (
            unmoderated_comments,
            url_for('admin/show_comments', _external=True),
            SIGNATURE))
        users = User.objects.filter(User.role >= ROLE_AUTHOR).all()
        to_addrs = [user.email for user in users if is_valid_email(user.email)]
        send_email(subject, msg, to_addrs)


def setup(app, plugin):
    app.connect_event('after-comment-saved', notify)
    app.connect_event('after-comment-saved', moderate_comments_notify)
