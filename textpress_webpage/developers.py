# -*- coding: utf-8 -*-
"""
    textpress.plugins.textpress_webpage.developers
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The developer central stuff.

    :copyright: Copyright 2007 by Armin Ronacher
    :license: GNU GPL.
"""
from textpress.api import *
from textpress.utils import is_valid_email
from textpress.plugins.textpress_webpage.models import Developer


def do_register(req):
    errors = []
    form = {'email': ''}
    developer = None

    email = req.args.get('email')
    activation_key = req.args.get('key')
    if email and activation_key:
        developer = Developer.get_by(email=email)
        if developer is not None:
            if developer.activation_key == activation_key:
                developer.activation_key = ''
                db.flush()
                error = False
            else:
                error = True
            return render_response('textpress_webpage/activate_developer.html',
                                   developer=developer)

    if req.method == 'POST':
        email = form['email'] = req.form.get('email', '')
        if not is_valid_email(email):
            errors.append('You have to provide a valid e-mail address.')
        elif req.form.get('email2') != email:
            errors.append('The two e-mail addresses don\'t match.')
        developer = Developer.get_by(email=email)
        if developer is not None:
            errors.append('This e-mail address is already in use.')
        password = req.form.get('password')
        if not password:
            errors.append('You have to enter a password.')
        elif req.form.get('password2') != password:
            errors.append('The two passwords don\'t match.')
        if not errors:
            developer = Developer(email, password)
            db.flush()
            developer.send_activation_mail()
    return render_response('textpress_webpage/register_developer.html',
        form=form,
        errors=errors,
        developer_created=developer
    )
