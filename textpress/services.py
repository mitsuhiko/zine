# -*- coding: utf-8 -*-
"""
    textpress.services
    ~~~~~~~~~~~~~~~~~~

    The builtin (JSON) services.

    :copyright: 2007 by Armin Ronacher.
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.models import Comment, ROLE_AUTHOR


def do_get_comment(req):
    comment_id = req.args.get('comment_id')
    if comment_id is None:
        abort(404)
    comment = Comment.get(comment_id)
    if comment is None:
        abort(404)
    if comment.blocked and req.user.role < ROLE_AUTHOR:
        abort(403)
    if comment.parent is not None:
        parent_id = comment.parent.comment_id
    else:
        parent_id = None
    email = None
    if req.user.role >= ROLE_AUTHOR:
        email = comment.email
    return {
        'id':           comment.comment_id,
        'parent':       parent_id,
        'body':         comment.body,
        'author':       comment.author,
        'email':        email,
        'pub_date':     int(comment.pub_date.strftime('%s')),
    }


all_services = {
    'get_comment':          do_get_comment
}
